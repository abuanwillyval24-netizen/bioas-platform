from django.contrib import admin
from .models import Household, CitizenProfile, CitizenPortalUpdateRequest, CitizenCommunityReport


@admin.register(Household)
class HouseholdAdmin(admin.ModelAdmin):
    list_display = ("household_code", "household_head_name", "barangay", "structure")
    list_filter = ("barangay",)
    search_fields = ("household_code", "household_head_name")


@admin.register(CitizenProfile)
class CitizenProfileAdmin(admin.ModelAdmin):
    list_display = (
        "citizen_qr_id", "full_name", "sex", "gender_identity",
        "status", "is_registered_voter", "is_senior_citizen", "is_pwd", "is_first_time_jobseeker",
    )
    list_filter = ("barangay", "status", "sex", "is_registered_voter", "is_senior_citizen", "is_pwd", "is_first_time_jobseeker")
    search_fields = ("citizen_qr_id", "last_name", "first_name", "mobile_number")


@admin.register(CitizenPortalUpdateRequest)
class CitizenPortalUpdateRequestAdmin(admin.ModelAdmin):
    list_display = ("citizen", "requested_mobile_number", "requested_civil_status", "status", "submitted_at")
    list_filter = ("barangay", "status", "submitted_at")
    search_fields = ("citizen__last_name", "citizen__first_name", "notes")


@admin.register(CitizenCommunityReport)
class CitizenCommunityReportAdmin(admin.ModelAdmin):
    list_display = ("tracking_code", "citizen", "category", "location_landmark", "status", "submitted_at")
    list_filter = ("barangay", "category", "status", "submitted_at")
    search_fields = ("tracking_code", "citizen__last_name", "citizen__first_name", "location_landmark", "description")
