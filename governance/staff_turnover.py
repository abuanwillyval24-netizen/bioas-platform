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
