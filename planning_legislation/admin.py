from django.contrib import admin
from .models import LegislativeMeasure, DevelopmentPlanProject


@admin.register(LegislativeMeasure)
class LegislativeMeasureAdmin(admin.ModelAdmin):
    list_display = ("series_number", "measure_type", "title", "authored_by", "session_date", "status")
    list_filter = ("barangay", "measure_type", "status", "session_date")
    search_fields = ("series_number", "title", "authored_by", "summary")


@admin.register(DevelopmentPlanProject)
class DevelopmentPlanProjectAdmin(admin.ModelAdmin):
    list_display = ("aip_reference_code", "project_title", "sector", "fiscal_year", "allocated_budget", "status")
    list_filter = ("barangay", "sector", "fiscal_year", "status")
    search_fields = ("aip_reference_code", "project_title")
