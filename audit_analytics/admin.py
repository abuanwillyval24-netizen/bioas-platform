from django.contrib import admin
from .models import SystemAuditLog, DILGComplianceReport, COAAuditCompliance


@admin.register(SystemAuditLog)
class SystemAuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "action_type", "actor_name", "actor_role", "reference_code", "barangay")
    list_filter = ("barangay", "action_type", "timestamp")
    search_fields = ("actor_name", "reference_code", "details")
    readonly_fields = ("timestamp",)


@admin.register(DILGComplianceReport)
class DILGComplianceReportAdmin(admin.ModelAdmin):
    list_display = ("report_category", "reporting_period", "due_date", "status", "transmittal_reference", "submitted_by")
    list_filter = ("barangay", "report_category", "status", "due_date")
    search_fields = ("reporting_period", "transmittal_reference", "submitted_by")


@admin.register(COAAuditCompliance)
class COAAuditComplianceAdmin(admin.ModelAdmin):
    list_display = ("audit_reference", "audit_type", "period_covered", "amount_involved", "status", "updated_at")
    list_filter = ("barangay", "audit_type", "status")
    search_fields = ("audit_reference", "period_covered", "remarks")
