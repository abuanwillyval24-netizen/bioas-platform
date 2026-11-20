import base64
from io import BytesIO
import uuid
import qrcode
from pathlib import Path
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template import engines
from governance.models import BarangayTenant
from documents.models import CertificateRequest
from audit_analytics.models import SystemAuditLog
from .models import CitizenProfile, CitizenCommunityReport


def make_citizen_qr_uri(payload):
    qr = qrcode.QRCode(box_size=4, border=1)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#111827", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def citizen_portal(request):
    barangays = BarangayTenant.objects.all()
    active_barangay = barangays.first()
    submitted_citizen = None

    if request.method == "POST" and active_barangay:
        submitted_citizen = CitizenProfile.objects.create(
            barangay=active_barangay,
            citizen_qr_id=f"CIT-{uuid.uuid4().hex[:6].upper()}",
            last_name=request.POST["last_name"].strip(),
            first_name=request.POST["first_name"].strip(),
            middle_name=request.POST.get("middle_name", "").strip(),
            suffix=request.POST.get("suffix", "").strip(),
            sex=request.POST["sex"],
            gender_identity=request.POST.get("gender_identity", "PREFER_NOT_TO_SAY"),
            birth_date=request.POST["birth_date"],
            civil_status=request.POST.get("civil_status", "SINGLE"),
            mobile_number=request.POST.get("mobile_number", "").strip(),
            is_registered_voter=bool(request.POST.get("is_registered_voter")),
            is_senior_citizen=bool(request.POST.get("is_senior_citizen")),
            is_pwd=bool(request.POST.get("is_pwd")),
            is_solo_parent=bool(request.POST.get("is_solo_parent")),
            is_4ps_beneficiary=bool(request.POST.get("is_4ps_beneficiary")),
            is_first_time_jobseeker=bool(request.POST.get("is_first_time_jobseeker")),
            status="PENDING_APPROVAL",
        )

    html_path = Path(__file__).resolve().parent.parent / "bioas_core" / "templates" / "governance" / "portal.html"
    template = engines["django"].from_string(html_path.read_text(encoding="utf-8"))
    return HttpResponse(template.render({
        "barangays": barangays,
        "active_barangay": active_barangay,
        "submitted_citizen": submitted_citizen,
    }, request))


def citizen_home(request):
    qr_id = (request.POST.get("qr_id") or request.GET.get("qr_id") or "").strip().upper()
    citizen = CitizenProfile.objects.filter(citizen_qr_id=qr_id).first() if qr_id else None
    notice, error = "", ""

    if qr_id and not citizen:
        error = f"Citizen QR ID '{qr_id}' not found."
    elif citizen and citizen.status != "ACTIVE_RESIDENT":
        error = f"Account Status: {citizen.get_status_display()}. Awaiting Secretary approval."
        citizen = None

    if request.method == "POST" and citizen:
        if request.POST.get("action") == "SUBMIT_REPORT":
            rep = CitizenCommunityReport.objects.create(
                barangay=citizen.barangay, citizen=citizen, tracking_code=f"RPT-{uuid.uuid4().hex[:6].upper()}",
                category=request.POST["category"], location_landmark=request.POST["location_landmark"].strip(),
                description=request.POST["description"].strip(),
            )
            notice = f"Report Submitted! Tracking Code: {rep.tracking_code}."
        elif request.POST.get("action") == "REQUEST_CERT":
            ctype = request.POST["cert_type"]
            exempt = ctype in ("INDIGENCY", "FIRST_TIME_JOBSEEKER")
            cert = CertificateRequest.objects.create(
                barangay=citizen.barangay, citizen=citizen, control_number=f"CERT-{uuid.uuid4().hex[:6].upper()}",
                cert_type=ctype, purpose=request.POST["purpose"].strip(), is_fee_exempt=exempt,
                fee_amount=0.00 if exempt else float(citizen.barangay.default_clearance_fee),
                status="READY_TO_PRINT" if (exempt or not citizen.barangay.fee_collection_enabled) else "PENDING_OR",
            )
            notice = f"Certificate Requested! Control No.: {cert.control_number} ({cert.get_status_display()})."

    citizen_qr_uri = make_citizen_qr_uri(request.build_absolute_uri(f"/citizen-home/?qr_id={citizen.citizen_qr_id}")) if citizen else ""

    tpl = """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>Citizen Portal</title>
<style>*{box-sizing:border-box;font-family:system-ui,sans-serif}body{margin:0;background:#f3f4f6}.top{background:#1e3a8a;color:#fff;padding:14px 24px;display:flex;justify-content:space-between;border-bottom:4px solid #f59e0b}.top a{color:#fff;text-decoration:none;font-weight:700;margin-left:12px}.wrap{max-width:860px;margin:20px auto;padding:0 16px}.card{background:#fff;border-radius:10px;padding:18px;box-shadow:0 1px 4px rgba(0,0,0,.08);margin-bottom:16px}label{display:block;font-size:.82rem;font-weight:700;margin:8px 0 4px}input,select,textarea{width:100%;padding:8px;border:1px solid #d1d5db;border-radius:6px}button{margin-top:12px;padding:9px 15px;background:#1e3a8a;color:#fff;border:0;border-radius:6px;font-weight:700;cursor:pointer}table{width:100%;border-collapse:collapse}th,td{padding:8px;border-bottom:1px solid #e5e7eb;font-size:.85rem;text-align:left}</style></head><body>
<div class="top"><strong>BIOAS Citizen Self-Service & Reporting</strong><div><a href="/portal/">New Sign-Up</a><a href="/">Dashboard</a></div></div>
<div class="wrap">
{% if notice %}<div class="card" style="background:#dcfce7;color:#166534;font-weight:700;">{{ notice }}</div>{% endif %}
{% if error %}<div class="card" style="background:#fee2e2;color:#991b1b;font-weight:700;">{{ error }}</div>{% endif %}
<div class="card"><h3 style="margin-top:0;">Approved Resident Sign-In</h3><form method="get" style="display:flex;gap:8px;"><input name="qr_id" value="{{ qr_id }}" placeholder="Enter Citizen QR ID (e.g., CIT-LAG-001)" required><button type="submit" style="margin:0;">Sign In</button></form></div>
{% if citizen %}
<div class="card" style="border-left:5px solid #16a34a;display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;">
  <div>
    <div style="font-size:.78rem;font-weight:800;color:#166534;text-transform:uppercase;">Official 201 Digital Resident Card</div>
    <h3 style="margin:4px 0;">{{ citizen.full_name }}</h3>
    <div>QR ID: <strong>{{ citizen.citizen_qr_id }}</strong> | {{ citizen.barangay.name }}</div>
    <div style="font-size:.82rem;color:#4b5563;margin-top:4px;">Status: <strong>{{ citizen.get_status_display }}</strong></div>
  </div>
  <div style="text-align:center;">
    <img src="{{ citizen_qr_uri }}" alt="Resident QR" style="width:96px;height:96px;border:1px solid #d1d5db;border-radius:6px;padding:3px;background:#fff;" />
    <div style="font-size:.72rem;color:#4b5563;">Scan Resident ID</div>
  </div>
</div>
<div class="card"><h3>Report Community Issue</h3><form method="post">{% csrf_token %}<input type="hidden" name="qr_id" value="{{ citizen.citizen_qr_id }}"><input type="hidden" name="action" value="SUBMIT_REPORT">
<label>Category</label><select name="category"><option value="INFRASTRUCTURE_LIGHT">Broken Streetlight / Road Issue</option><option value="PEACE_ORDER_NOISE">Peace & Order / Noise</option><option value="SANITATION_WASTE">Garbage / Drainage</option><option value="DRRM_HAZARD">Flood / Emergency Hazard</option></select>
<label>Location Landmark</label><input name="location_landmark" required><label>Details</label><textarea name="description" rows="2" required></textarea><button type="submit">Submit Report</button></form></div>
<div class="card"><h3>Request Certificate Online</h3><form method="post">{% csrf_token %}<input type="hidden" name="qr_id" value="{{ citizen.citizen_qr_id }}"><input type="hidden" name="action" value="REQUEST_CERT">
<label>Document</label><select name="cert_type"><option value="BARANGAY_CLEARANCE">Barangay Clearance</option><option value="INDIGENCY">Certificate of Indigency (Exempt)</option><option value="FIRST_TIME_JOBSEEKER">First-Time Jobseeker RA 11261 (Exempt)</option></select>
<label>Purpose</label><input name="purpose" required><button type="submit">Request Certificate</button></form></div>
<div class="card"><h3>My Reports</h3><table><thead><tr><th>Code</th><th>Category</th><th>Location</th><th>Status</th></tr></thead><tbody>{% for r in citizen.community_reports.all %}<tr><td><strong>{{ r.tracking_code }}</strong></td><td>{{ r.get_category_display }}</td><td>{{ r.location_landmark }}</td><td>{{ r.get_status_display }}</td></tr>{% empty %}<tr><td colspan="4">None yet.</td></tr>{% endfor %}</tbody></table></div>
<div class="card"><h3>My Certificates</h3><table><thead><tr><th>Control No.</th><th>Type</th><th>Status</th></tr></thead><tbody>{% for c in citizen.certificate_requests.all %}<tr><td><strong>{{ c.control_number }}</strong></td><td>{{ c.get_cert_type_display }}</td><td>{{ c.get_status_display }}</td></tr>{% empty %}<tr><td colspan="3">None yet.</td></tr>{% endfor %}</tbody></table></div>
{% endif %}</div></body></html>"""
    return HttpResponse(engines["django"].from_string(tpl).render({"citizen": citizen, "qr_id": qr_id, "notice": notice, "error": error, "citizen_qr_uri": citizen_qr_uri}, request))


def approve_citizen(request, citizen_id):
    citizen = get_object_or_404(CitizenProfile, id=citizen_id)
    if citizen.status == "PENDING_APPROVAL":
        citizen.status = "ACTIVE_RESIDENT"
        citizen.save(update_fields=["status"])
        SystemAuditLog.objects.create(
            barangay=citizen.barangay,
            action_type="PORTAL_APPROVAL",
            actor_name=request.user.username if request.user.is_authenticated else "Barangay Secretary",
            actor_role="Barangay Secretary",
            reference_code=citizen.citizen_qr_id,
            details=f"Approved Citizen Portal registration and synced {citizen.full_name} to 201 Master.",
        )
    return redirect("/?tier=BARANGAY&module=CITIZENS")


def update_report_status(request, report_id, new_status):
    rep = get_object_or_404(CitizenCommunityReport, id=report_id)
    if new_status in ("DISPATCHED_TANOD_WO", "RESOLVED_CLOSED"):
        rep.status = new_status
        rep.save(update_fields=["status"])
        SystemAuditLog.objects.create(
            barangay=rep.barangay,
            action_type="CITIZEN_REPORT_UPDATE",
            actor_name=request.user.username if request.user.is_authenticated else "Barangay Secretary",
            actor_role="Barangay Secretary",
            reference_code=rep.tracking_code,
            details=f"Updated community report {rep.tracking_code} to {rep.get_status_display()}.",
        )
    return redirect("/?tier=BARANGAY&module=CITIZENS")
