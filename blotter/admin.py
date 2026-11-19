from django.contrib import admin
from .models import BlotterCase


@admin.register(BlotterCase)
class BlotterCaseAdmin(admin.ModelAdmin):
    list_display = (
        "case_number",
        "masked_case_label",
        "category",
        "stage",
        "blocks_clearance",
        "is_vawc_confidential",
        "incident_date",
    )
    list_filter = ("barangay", "category", "stage", "is_vawc_confidential", "blocks_clearance")
    search_fields = ("case_number", "complainant_name", "respondent_name", "incident_location")

    @admin.display(description="Case Parties")
    def masked_case_label(self, obj):
        return obj.masked_title
