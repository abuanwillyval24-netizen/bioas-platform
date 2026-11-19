import csv
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from governance.models import BarangayTenant
from documents.models import CertificateRequest
from audit_analytics.models import SystemAuditLog
from .models import OfficialReceipt, AbuloySheet


def export_treasury_excel(request):
    barangay = BarangayTenant.objects.first()
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="BIOAS_Treasury_{timezone.localdate()}.csv"'
    writer = csv.writer(response)
    writer.writerow(["RECORD TYPE", "OR / SERIAL NO.", "PAYOR / DECEASED", "CATEGORY / BENEFICIARY", "AMOUNT (PHP)", "STATUS / ISSUED BY", "DATE"])

    for r in OfficialReceipt.objects.filter(barangay=barangay, is_voided=False):
        writer.writerow(["OFFICIAL RECEIPT", r.or_number, r.payor_name, r.get_collection_type_display(), f"{r.amount_paid:.2f}", r.issued_by, r.issued_at.strftime("%Y-%m-%d")])

    for a in AbuloySheet.objects.filter(barangay=barangay):
        writer.writerow(["BEREAVEMENT WELFARE SHEET", a.serial_number, a.deceased_name, a.beneficiary_family_name, f"{a.total_collected:.2f}", a.get_status_display(), ""])

    return response


def issue_or_and_unlock(request, cert_id):
    cert = get_object_or_404(CertificateRequest, id=cert_id)
    if cert.status == "PENDING_OR":
        or_num = f"OR-{timezone.localdate().year}-{1000 + OfficialReceipt.objects.count() + 1}"
        OfficialReceipt.objects.create(
            barangay=cert.barangay,
            or_number=or_num,
            payor_name=cert.citizen.full_name,
            collection_type="CLEARANCE_FEE",
            amount_paid=cert.fee_amount,
            issued_by=request.user.username if request.user.is_authenticated else "Barangay Treasurer",
        )
        cert.official_receipt_number = or_num
        cert.status = "READY_TO_PRINT"
        cert.save(update_fields=["official_receipt_number", "status"])
        SystemAuditLog.objects.create(
            barangay=cert.barangay,
            action_type="TREASURY_OR_UNLOCK",
            actor_name=request.user.username if request.user.is_authenticated else "Barangay Treasurer",
            actor_role="Barangay Treasurer",
            reference_code=or_num,
            details=f"Issued {or_num} and unlocked certificate {cert.control_number} for {cert.citizen.full_name}.",
        )
    return redirect("/?tier=BARANGAY&module=TREASURY")
