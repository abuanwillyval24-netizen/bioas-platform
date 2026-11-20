import json
from datetime import date
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template import engines
from .models import BarangayTenant, BarangayStaffProfile, TermArchiveSnapshot, OfficialTurnoverRecord
from citizens.models import CitizenProfile, CitizenCommunityReport
from documents.models import CertificateRequest
from blotter.models import BlotterCase
from treasury.models import OfficialReceipt
from audit_analytics.models import SystemAuditLog


DEFAULT_SEATS = [
    ("SEAT-CAPTAIN", "CAPTAIN", "Office of the Punong Barangay"),
    ("SEAT-KAGAWAD-1", "COUNCILOR", "Committee on Peace & Order"),
    ("SEAT-KAGAWAD-2", "COUNCILOR", "Committee on Appropriations & Finance"),
    ("SEAT-KAGAWAD-3", "COUNCILOR", "Committee on Health & Sanitation"),
    ("SEAT-KAGAWAD-4", "COUNCILOR", "Committee on Infrastructure & Public Works"),
    ("SEAT-KAGAWAD-5", "COUNCILOR", "Committee on Education & Culture"),
    ("SEAT-KAGAWAD-6", "COUNCILOR", "Committee on Social Services & VAWC"),
    ("SEAT-KAGAWAD-7", "COUNCILOR", "Committee on Agriculture & Environment"),
    ("SEAT-SK-CHAIR", "SK_CHAIRMAN", "Sangguniang Kabataan Chairperson"),
    ("SEAT-SK-KAGAWAD-1", "SK_COUNCILOR", "SK Committee on Sports & Youth Dev"),
    ("SEAT-SK-KAGAWAD-2", "SK_COUNCILOR", "SK Committee on Education"),
    ("SEAT-SK-KAGAWAD-3", "SK_COUNCILOR", "SK Committee on Environment"),
    ("SEAT-SK-KAGAWAD-4", "SK_COUNCILOR", "SK Committee on Health & Anti-Drug"),
    ("SEAT-SK-KAGAWAD-5", "SK_COUNCILOR", "SK Committee on Livelihood"),
    ("SEAT-SK-KAGAWAD-6", "SK_COUNCILOR", "SK Committee on Gender & Inclusion"),
    ("SEAT-SK-KAGAWAD-7", "SK_COUNCILOR", "SK Committee on Budget & Audit"),
    ("SEAT-SECRETARY", "SECRETARY", "Office of the Barangay Secretary"),
    ("SEAT-ASST-SECRETARY", "ASST_SECRETARY", "Assistant Secretariat Desk"),
    ("SEAT-TREASURER", "TREASURER", "Office of the Barangay Treasurer"),
    ("SEAT-ASST-TREASURER", "ASST_TREASURER", "Assistant Treasury Desk"),
    ("SEAT-HEPE", "HEPE", "Barangay Tanod Command (BPSO)"),
]


def get_actor_role(user):
    if user.is_superuser:
        return "SUPERADMIN"
    prof = getattr(user, "staff_profile", None)
    if prof and prof.approval_status == "ACTIVE":
        return prof.role
    return "NONE"


def allowed_creation_roles(actor_role):
    all_roles = dict(BarangayStaffProfile.ROLE_CHOICES)
    if actor_role in ("SUPERADMIN", "CAPTAIN"):
        return list(all_roles.items())
    if actor_role in ("SECRETARY", "ASST_SECRETARY"):
        return [(k, all_roles[k]) for k in ("ASST_SECRETARY", "WAREHOUSE_KEEPER", "CUSTODIAN", "SOCIAL_WORKER")]
    if actor_role == "TREASURER":
        return [("ASST_TREASURER", all_roles["ASST_TREASURER"])]
    return []


@login_required(login_url="/login/")
def staff_roster_and_turnover(request):
    User = get_user_model()
    brgy = BarangayTenant.objects.first()
    actor_role = get_actor_role(request.user)
    creatable_roles = allowed_creation_roles(actor_role)
    can_approve = actor_role in ("SUPERADMIN", "CAPTAIN")
    notice, error = "", ""

    if brgy:
        for seat_code, role, unit in DEFAULT_SEATS:
            if not BarangayStaffProfile.objects.filter(barangay=brgy, seat_code=seat_code).exists():
                uname = seat_code.lower().replace("-", "_")
                u, _ = User.objects.get_or_create(username=uname, defaults={"is_staff": False})
                if not u.has_usable_password():
                    u.set_password("BioasSeat2026!")
                    u.save(update_fields=["password"])
                BarangayStaffProfile.objects.create(
                    user=u, barangay=brgy, seat_code=seat_code,
                    full_name=f"Vacant / Incumbent ({seat_code})", role=role,
                    committee_or_unit=unit, approval_status="PENDING_CAPTAIN",
                )

    if request.method == "POST" and brgy:
        action = request.POST.get("action")
        if action == "CREATE_STAFF" and creatable_roles:
            role = request.POST.get("role", "")
            if role in dict(creatable_roles):
                uname = request.POST["username"].strip().lower()
                if User.objects.filter(username=uname).exists():
                    error = f"Username '{uname}' already exists."
                else:
                    u = User.objects.create_user(username=uname, password=request.POST["password"])
                    auto_active = can_approve and bool(request.POST.get("auto_approve"))
                    prof = BarangayStaffProfile.objects.create(
                        user=u, barangay=brgy,
                        seat_code=request.POST.get("seat_code", "").strip().upper() or f"STAFF-{uname.upper()}",
                        full_name=request.POST["full_name"].strip(),
                        role=role,
                        committee_or_unit=request.POST.get("committee_or_unit", "").strip(),
                        term_start_date=request.POST.get("term_start_date") or date.today(),
                        approval_status="ACTIVE" if auto_active else "PENDING_CAPTAIN",
                        created_by=request.user,
                        approved_by=request.user if auto_active else None,
                    )
                    SystemAuditLog.objects.create(
                        barangay=brgy, action_type="STAFF_ACCOUNT_CREATED",
                        actor_name=request.user.username, actor_role=actor_role, reference_code=prof.seat_code,
                        details=f"Created {prof.get_role_display()} account for {prof.full_name} ({prof.get_approval_status_display()}).",
                    )
                    notice = f"Created {prof.full_name} ({prof.get_role_display()}) — {prof.get_approval_status_display()}."
        elif action == "UPDATE_SEAT_HOLDER":
            prof = get_object_or_404(BarangayStaffProfile, id=request.POST["profile_id"], barangay=brgy)
            if can_approve or prof.created_by == request.user:
                prof.full_name = request.POST["full_name"].strip()
                prof.committee_or_unit = request.POST.get("committee_or_unit", prof.committee_or_unit).strip()
                if request.POST.get("new_password"):
                    prof.user.set_password(request.POST["new_password"])
                    prof.user.save(update_fields=["password"])
                prof.save(update_fields=["full_name", "committee_or_unit"])
                notice = f"Updated seat {prof.seat_code} holder to {prof.full_name}."
        elif action == "EXECUTE_OATH_TURNOVER" and can_approve:
            oath_doc = request.FILES.get("oath_document")
            oath_ref = request.POST.get("oath_taking_doc_ref", "").strip()
            start_d = request.POST.get("scoped_start_date")
            end_d = request.POST.get("scoped_end_date")
            if not oath_doc or not oath_ref or not start_d or not end_d:
                error = "Oath-Taking / Proclamation document upload, reference number, and scoped term dates are required."
            else:
                outgoing_cap = BarangayStaffProfile.objects.filter(barangay=brgy, seat_code="SEAT-CAPTAIN").first()
                outgoing_cap_name = outgoing_cap.full_name if outgoing_cap else "Outgoing Punong Barangay"
                roster_before = list(BarangayStaffProfile.objects.filter(barangay=brgy).values("seat_code", "full_name", "role", "committee_or_unit", "approval_status"))
                counts = {
                    "certificates_archived": CertificateRequest.objects.filter(barangay=brgy, created_at__date__range=[start_d, end_d]).count(),
                    "blotter_cases_archived": BlotterCase.objects.filter(barangay=brgy, created_at__date__range=[start_d, end_d]).count(),
                    "official_receipts_archived": OfficialReceipt.objects.filter(barangay=brgy, created_at__date__range=[start_d, end_d]).count(),
                    "community_reports_archived": CitizenCommunityReport.objects.filter(barangay=brgy, created_at__date__range=[start_d, end_d]).count(),
                    "audit_logs_archived": SystemAuditLog.objects.filter(barangay=brgy, timestamp__date__range=[start_d, end_d]).count(),
                    "total_201_citizens": CitizenProfile.objects.filter(barangay=brgy).count(),
                }
                incoming_cap_name = outgoing_cap_name
                for prof in BarangayStaffProfile.objects.filter(barangay=brgy):
                    new_name = request.POST.get(f"incoming_name_{prof.id}", "").strip()
                    if new_name and new_name != prof.full_name:
                        prof.full_name = new_name
                        prof.term_start_date = date.today()
                        prof.save(update_fields=["full_name", "term_start_date"])
                    if prof.seat_code == "SEAT-CAPTAIN":
                        incoming_cap_name = prof.full_name

                snap = TermArchiveSnapshot.objects.create(
                    barangay=brgy, term_label=request.POST.get("term_label", "Completed Barangay & SK Term").strip(),
                    scoped_start_date=start_d, scoped_end_date=end_d,
                    outgoing_captain_name=outgoing_cap_name, incoming_captain_name=incoming_cap_name,
                    oath_taking_doc_ref=oath_ref, oath_document=oath_doc,
                    archived_counts_json=counts, roster_snapshot_json=roster_before,
                    executed_by=request.user.username,
                )
                OfficialTurnoverRecord.objects.create(
                    barangay=brgy, transition_cycle=f"Oath Turnover ({oath_ref})",
                    outgoing_punong_barangay=outgoing_cap_name, incoming_punong_barangay=incoming_cap_name,
                    outgoing_treasurer="Archived Term Treasurer", outgoing_secretary="Archived Term Secretary",
                    status="COMPLETED_TURNOVER",
                )
                SystemAuditLog.objects.create(
                    barangay=brgy, action_type="ELECTION_OATH_TURNOVER",
                    actor_name=request.user.username, actor_role=actor_role, reference_code=oath_ref,
                    details=f"Executed Election/Oath-Taking Turnover ({start_d} to {end_d}). Archived {sum(counts.values())} scoped records and updated persistent official seats.",
                )
                notice = f"Oath-Taking Turnover executed! Scoped records ({start_d} to {end_d}) archived under {oath_ref} and official seat names updated."

    roster = BarangayStaffProfile.objects.filter(barangay=brgy).order_by("id") if brgy else []
    archives = TermArchiveSnapshot.objects.filter(barangay=brgy).order_by("-executed_at") if brgy else []

    tpl = """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>BIOAS Official Roster & Oath Turnover</title>
<style>*{box-sizing:border-box;font-family:system-ui,sans-serif}body{margin:0;background:#f3f4f6}.top{background:#1e3a8a;color:#fff;padding:14px 24px;display:flex;justify-content:space-between;align-items:center;border-bottom:4px solid #f59e0b}.top a{color:#fff;text-decoration:none;font-weight:700;margin-left:14px}.wrap{max-width:1180px;margin:20px auto;padding:0 16px}.card{background:#fff;border-radius:10px;padding:18px;box-shadow:0 1px 4px rgba(0,0,0,.08);margin-bottom:18px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}label{display:block;font-size:.8rem;font-weight:700;margin:8px 0 4px}input,select{width:100%;padding:8px;border:1px solid #d1d5db;border-radius:6px}.btn{padding:8px 14px;background:#1e3a8a;color:#fff;border:0;border-radius:6px;font-weight:700;cursor:pointer;text-decoration:none;display:inline-block;font-size:.82rem}.btn-ok{background:#15803d}.btn-warn{background:#b91c1c}table{width:100%;border-collapse:collapse}th,td{padding:8px;border-bottom:1px solid #e5e7eb;font-size:.83rem;text-align:left}.badge{padding:3px 8px;border-radius:999px;font-size:.73rem;font-weight:800}.ACTIVE{background:#dcfce7;color:#166534}.PENDING_CAPTAIN{background:#fef3c7;color:#92400e}.SUSPENDED{background:#fee2e2;color:#991b1b}</style></head><body>
<div class="top"><strong>BIOAS Official Roster, Captain Approval & Oath-Taking Turnover</strong><div><a href="/?tier=BARANGAY&module=TURNOVER">← Back to Dashboard</a></div></div>
<div class="wrap">
{% if notice %}<div class="card" style="background:#dcfce7;color:#166534;font-weight:700;">{{ notice }}</div>{% endif %}
{% if error %}<div class="card" style="background:#fee2e2;color:#991b1b;font-weight:700;">{{ error }}</div>{% endif %}

{% if creatable_roles %}
<div class="card"><h3 style="margin-top:0;">Create Barangay / SK / Delegated Staff Account (Subject to Captain Approval)</h3>
<form method="post">{% csrf_token %}<input type="hidden" name="action" value="CREATE_STAFF">
<div class="grid">
<div><label>Official Role</label><select name="role">{% for code, label in creatable_roles %}<option value="{{ code }}">{{ label }}</option>{% endfor %}</select></div>
<div><label>Full Name</label><input name="full_name" placeholder="Hon. / Name" required></div>
<div><label>Login Username</label><input name="username" placeholder="e.g., sec_lagare" required></div>
<div><label>Initial Password</label><input type="password" name="password" required></div>
<div><label>Seat Code / Desk</label><input name="seat_code" placeholder="e.g., DESK-WAREHOUSE-1"></div>
<div><label>Committee / Unit</label><input name="committee_or_unit" placeholder="e.g., DSWD / MSWD Focal"></div>
</div>
{% if can_approve %}<label style="margin-top:10px;"><input type="checkbox" name="auto_approve" style="width:auto;" checked> Approve & Activate Immediately (Captain / Admin Privilege)</label>{% endif %}
<button type="submit" class="btn" style="margin-top:12px;">Create Staff Account</button></form></div>
{% endif %}

<div class="card"><h3 style="margin-top:0;">Persistent Official Seats & Staff Roster (Captain, 7 Councilors, SK Chair, 7 SK Councilors, Sec/Treas + Assts, Hepe & Units)</h3>
<table><thead><tr><th>Seat ID</th><th>Role</th><th>Official / Staff Name (Editable)</th><th>Login User</th><th>Status</th><th>Actions</th></tr></thead><tbody>
{% for p in roster %}<tr>
<td><strong>{{ p.seat_code }}</strong></td>
<td>{{ p.get_role_display }}<br><small style="color:#6b7280;">{{ p.committee_or_unit }}</small></td>
<td><form method="post" style="display:flex;gap:6px;align-items:center;">{% csrf_token %}<input type="hidden" name="action" value="UPDATE_SEAT_HOLDER"><input type="hidden" name="profile_id" value="{{ p.id }}"><input name="full_name" value="{{ p.full_name }}" style="padding:5px;"><input type="password" name="new_password" placeholder="New Pass (opt)" style="padding:5px;width:120px;"><button type="submit" class="btn" style="padding:5px 9px;">Save</button></form></td>
<td><code>{{ p.user.username }}</code></td>
<td><span class="badge {{ p.approval_status }}">{{ p.get_approval_status_display }}</span></td>
<td>{% if can_approve %}
  {% if p.approval_status != "ACTIVE" %}<a href="/staff-roster/approve/{{ p.id }}/ACTIVE/" class="btn btn-ok">Approve</a>{% endif %}
  {% if p.approval_status == "ACTIVE" %}<a href="/staff-roster/approve/{{ p.id }}/SUSPENDED/" class="btn btn-warn">Suspend</a>{% endif %}
{% else %}<small>Captain Approval Required</small>{% endif %}</td>
</tr>{% endfor %}</tbody></table></div>

{% if can_approve %}
<div class="card" style="border-left:5px solid #d97706;"><h3 style="margin-top:0;">Election & Oath-Taking Seat Transition + Scoped-Date Term Archival</h3>
<p style="font-size:.85rem;color:#374151;">Upload the signed <strong>COMELEC Proclamation / Oath-Taking Document</strong> and set the outgoing term date scope. All records processed within those dates will be archived for COA/DILG audit reference, while persistent seat accounts remain intact with updated official names.</p>
<form method="post" enctype="multipart/form-data">{% csrf_token %}<input type="hidden" name="action" value="EXECUTE_OATH_TURNOVER">
<div class="grid">
<div><label>Outgoing Term Label</label><input name="term_label" value="2023-2026 Barangay & SK Term" required></div>
<div><label>Scoped Term Start Date</label><input type="date" name="scoped_start_date" required></div>
<div><label>Scoped Term End Date</label><input type="date" name="scoped_end_date" required></div>
<div><label>Oath-Taking / Proclamation Ref. No.</label><input name="oath_taking_doc_ref" placeholder="e.g., COMELEC-OATH-2026-001" required></div>
<div><label>Signed Oath-Taking Document (PDF/JPG/PNG)</label><input type="file" name="oath_document" required></div>
</div>
<h4 style="margin:14px 0 6px;">Incoming Sworn-In Officials (Leave unchanged if re-elected)</h4>
<div class="grid">{% for p in roster %}{% if "SEAT-" in p.seat_code %}<div><label>{{ p.seat_code }} ({{ p.get_role_display }})</label><input name="incoming_name_{{ p.id }}" value="{{ p.full_name }}"></div>{% endif %}{% endfor %}</div>
<button type="submit" class="btn btn-ok" style="margin-top:14px;">Execute Oath-Taking Turnover & Archive Scoped Term</button></form></div>
{% endif %}

<div class="card"><h3 style="margin-top:0;">Archived Term Snapshots (Audit & Paper Trail Vault)</h3>
<table><thead><tr><th>Term Label</th><th>Scoped Dates</th><th>Outgoing → Incoming Captain</th><th>Oath Ref.</th><th>Archived Counts</th><th>Audit Export</th></tr></thead><tbody>
{% for a in archives %}<tr><td><strong>{{ a.term_label }}</strong></td><td>{{ a.scoped_start_date }} to {{ a.scoped_end_date }}</td><td>{{ a.outgoing_captain_name }} → <strong>{{ a.incoming_captain_name }}</strong></td><td>{{ a.oath_taking_doc_ref }}</td><td><small>{{ a.archived_counts_json }}</small></td><td><a href="/staff-roster/archive/{{ a.id }}/" class="btn">Download Archive JSON</a></td></tr>{% empty %}<tr><td colspan="6">No archived term snapshots yet.</td></tr>{% endfor %}</tbody></table></div>
</div></body></html>"""
    return HttpResponse(engines["django"].from_string(tpl).render({
        "roster": roster, "archives": archives, "creatable_roles": creatable_roles,
        "can_approve": can_approve, "notice": notice, "error": error,
    }, request))


@login_required(login_url="/login/")
def approve_staff_account(request, profile_id, new_status):
    actor_role = get_actor_role(request.user)
    if actor_role in ("SUPERADMIN", "CAPTAIN") and new_status in ("ACTIVE", "SUSPENDED"):
        prof = get_object_or_404(BarangayStaffProfile, id=profile_id)
        prof.approval_status = new_status
        prof.approved_by = request.user
        prof.save(update_fields=["approval_status", "approved_by"])
        SystemAuditLog.objects.create(
            barangay=prof.barangay, action_type="CAPTAIN_STAFF_APPROVAL",
            actor_name=request.user.username, actor_role=actor_role, reference_code=prof.seat_code,
            details=f"Punong Barangay updated {prof.full_name} ({prof.get_role_display()}) status to {prof.get_approval_status_display()}.",
        )
    return redirect("/staff-roster/")


@login_required(login_url="/login/")
def download_term_archive(request, archive_id):
    snap = get_object_or_404(TermArchiveSnapshot, id=archive_id)
    payload = {
        "barangay": snap.barangay.name, "term_label": snap.term_label,
        "scoped_start_date": str(snap.scoped_start_date), "scoped_end_date": str(snap.scoped_end_date),
        "outgoing_captain": snap.outgoing_captain_name, "incoming_captain": snap.incoming_captain_name,
