import uuid
from pathlib import Path
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template import engines
from django.utils import timezone
from governance.models import BarangayTenant
from citizens.models import CitizenProfile
from .models import CertificateRequest


def issue_certificate_counter(request):
    barangay = BarangayTenant.objects.first()
    citizens = CitizenProfile.objects.filter(barangay=barangay).order_by("last_name", "first_name") if barangay else CitizenProfile.objects.none()
    error_msg = ""

    if request.method == "POST" and barangay:
        citizen = CitizenProfile.objects.get(id=request.POST["citizen_id"])
        cert_type = request.POST["cert_type"]
        purpose = request.POST["purpose"].strip()
        is_exempt = cert_type in ("INDIGENCY", "FIRST_TIME_JOBSEEKER") or bool(request.POST.get("is_fee_exempt"))
        fee = 0.00 if is_exempt else float(barangay.default_clearance_fee)
        or_num = request.POST.get("official_receipt_number", "").strip()

        if citizen.status != "ACTIVE_RESIDENT":
            error_msg = f"Blocked: {citizen.full_name} is currently '{citizen.get_status_display()}'. Approve or activate their 201 profile first."
        elif citizen.respondent_cases.filter(blocks_clearance=True).exists():
            error_msg = f"Clearance Hold: {citizen.full_name} has an active Katarungang Pambarangay / Blotter case."
        else:
            control_num = f"CERT-{uuid.uuid4().hex[:6].upper()}"
            status = "READY_TO_PRINT" if (is_exempt or not barangay.fee_collection_enabled or or_num) else "PENDING_OR"
            cert = CertificateRequest.objects.create(
                barangay=barangay,
                citizen=citizen,
                control_number=control_num,
                cert_type=cert_type,
                purpose=purpose,
                is_fee_exempt=is_exempt,
                fee_amount=fee,
                official_receipt_number=or_num,
                status=status,
            )
            return redirect(f"/certificate/{cert.control_number}/")

    html_path = Path(__file__).resolve().parent / "issue_counter.html"
    template = engines["django"].from_string(html_path.read_text(encoding="utf-8"))
    return HttpResponse(template.render({
        "barangay": barangay,
        "citizens": citizens,
        "error_msg": error_msg,
    }, request))


def print_certificate(request, control_number):
    cert = get_object_or_404(CertificateRequest, control_number=control_number)
    if cert.status in ("PENDING_REVIEW", "PENDING_OR", "PENDING_COUNCILOR", "PENDING_CAPTAIN", "REJECTED_HOLD"):
        return HttpResponse(f"<h2>Approval Gate ({cert.control_number}): Current status is '{cert.get_status_display()}'. Punong Barangay Final Approval is required before printing &amp; Barangay Dry Seal. <a href='/?tier=BARANGAY&module=CERTIFICATES'>Back</a></h2>")
    if cert.status == "READY_TO_PRINT":
        cert.status = "ISSUED_PRINTED"
        cert.signatory_name = cert.barangay.get_active_signatory()
        cert.issued_by = request.user.username if request.user.is_authenticated else "Releasing Clerk"
        cert.save(update_fields=["status", "signatory_name", "issued_by"])

    signatory = cert.barangay.get_active_signatory()
    fee_label = "FEE EXEMPT" if cert.is_fee_exempt else (f"OR #{cert.official_receipt_number}" if cert.official_receipt_number else "NO FEE")
    return HttpResponse(f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>{cert.control_number}</title>
<style>
  body {{ font-family: 'Times New Roman', serif; background: #e5e7eb; padding: 24px; }}
  .sheet {{ max-width: 780px; margin: auto; background: #fff; padding: 48px 56px; box-shadow: 0 2px 10px rgba(0,0,0,0.12); }}
  .header {{ text-align: center; border-bottom: 3px double #111827; padding-bottom: 12px; margin-bottom: 24px; }}
  .title {{ text-align: center; font-size: 1.5rem; font-weight: bold; margin: 24px 0; text-decoration: underline; }}
  .body-text {{ font-size: 1.12rem; line-height: 1.8; text-align: justify; }}
  .footer {{ margin-top: 48px; display: flex; justify-content: space-between; font-size: 0.95rem; }}
  .sign {{ text-align: center; margin-top: 40px; }}
  @media print {{ body {{ background: #fff; padding: 0; }} .sheet {{ box-shadow: none; }} .no-print {{ display: none; }} }}
</style></head><body>
<div class="no-print" style="max-width:780px;margin:0 auto 12px;display:flex;justify-content:space-between;">
  <a href="/?tier=BARANGAY&module=CERTIFICATES">← Back to Certificates</a>
  <button onclick="window.print()">Print Official Copy</button>
</div>
<div class="sheet">
  <div class="header">
    <div>Republic of the Philippines</div>
    <div>Province of {cert.barangay.city_municipality.province.name} | {cert.barangay.city_municipality.name}</div>
    <h2 style="margin:4px 0;">OFFICE OF THE PUNONG BARANGAY — {cert.barangay.name.upper()}</h2>
  </div>
  <div class="title">{cert.get_cert_type_display().upper()}</div>
  <p class="body-text"><strong>TO WHOM IT MAY CONCERN:</strong></p>
  <p class="body-text">This is to certify that <strong>{cert.citizen.full_name.upper()}</strong>, of legal age, {cert.citizen.get_sex_display().lower()}, and a bona fide resident of <strong>{cert.barangay.name}, {cert.barangay.city_municipality.name}</strong>, is known to be of good moral character and has no derogatory record on file.</p>
  <p class="body-text">Issued upon request for <strong>{cert.purpose}</strong> on <strong>{timezone.localdate():%B %d, %Y}</strong>.</p>
  <div class="footer">
    <div><div>Control No.: <strong>{cert.control_number}</strong></div><div>QR ID: <strong>{cert.citizen.citizen_qr_id}</strong></div><div>Fee / OR: <strong>{fee_label}</strong></div></div>
    <div class="sign"><div style="font-weight:bold;text-decoration:underline;">{signatory['name'].upper()}</div><div>{signatory['title']}</div></div>
  </div>
</div></body></html>""")
