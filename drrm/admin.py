from django.contrib import admin
from .models import HazardIncidentAlert, EvacuationCenterStatus


@admin.register(HazardIncidentAlert)
class HazardIncidentAlertAdmin(admin.ModelAdmin):
    list_display = (
        "alert_code",
        "title",
        "hazard_type",
        "alert_level",
        "affected_families_count",
        "reported_by",
        "reported_at",
    )
    list_filter = ("barangay", "hazard_type", "alert_level", "reported_at")
    search_fields = ("alert_code", "title", "situation_report", "reported_by")


@admin.register(EvacuationCenterStatus)
class EvacuationCenterStatusAdmin(admin.ModelAdmin):
    list_display = (
        "center_name",
        "status",
        "current_families_housed",
        "max_family_capacity",
        "current_individuals_housed",
        "camp_manager",
    )
    list_filter = ("barangay", "status")
    search_fields = ("center_name", "location_address", "camp_manager")
