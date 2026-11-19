from django.contrib import admin
from django.utils.html import format_html
from .models import CertificateRequest


@admin.register(CertificateRequest)
class CertificateRequestAdmin(admin.ModelAdmin):
    list_display = (
        "control_number",
        "citizen",
        "cert_type",
        "purpose",
        "is_fee_exempt",
        "official_receipt_number",
        "status",
        "issued_date",
        "print_link",
    )
    list_filter = ("barangay", "cert_type", "status", "is_fee_exempt", "issued_date")
    search_fields = ("control_number", "citizen__last_name", "citizen__first_name", "official_receipt_number")

    @admin.display(description="Certificate")
    def print_link(self, obj):
        if obj.status in ("READY_TO_PRINT", "ISSUED_PRINTED"):
            return format_html('<a href="/certificate/{}/" target="_blank">Print / View</a>', obj.control_number)
        return "OR Required"
