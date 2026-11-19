from django.contrib import admin
from .models import OfficialReceipt, AbuloySheet


@admin.register(OfficialReceipt)
class OfficialReceiptAdmin(admin.ModelAdmin):
    list_display = (
        "or_number",
        "payor_name",
        "payment_type",
        "amount_paid",
        "linked_certificate",
        "issued_date",
        "is_voided",
    )
    list_filter = ("barangay", "payment_type", "is_voided", "issued_date")
    search_fields = ("or_number", "payor_name", "linked_certificate__control_number")


@admin.register(AbuloySheet)
class AbuloySheetAdmin(admin.ModelAdmin):
    list_display = (
        "serial_number",
        "deceased_name",
        "beneficiary_name",
        "total_collected",
        "status",
        "date_issued",
    )
    list_filter = ("barangay", "status", "date_issued")
    search_fields = ("serial_number", "deceased_name", "beneficiary_name")
