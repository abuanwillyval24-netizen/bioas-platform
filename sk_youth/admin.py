from django.contrib import admin
from .models import KatipunanKabataanProfile, SKProjectActivity


@admin.register(KatipunanKabataanProfile)
class KatipunanKabataanProfileAdmin(admin.ModelAdmin):
    list_display = ("citizen", "youth_classification", "education_level", "is_sk_registered_voter", "attended_last_kk_assembly", "registered_date")
    list_filter = ("barangay", "youth_classification", "education_level", "is_sk_registered_voter")
    search_fields = ("citizen__last_name", "citizen__first_name", "skills_and_interests")


@admin.register(SKProjectActivity)
class SKProjectActivityAdmin(admin.ModelAdmin):
    list_display = ("project_code", "title", "category", "allocated_budget", "youth_participants_count", "status", "event_date")
    list_filter = ("barangay", "category", "status", "event_date")
    search_fields = ("project_code", "title", "sk_chairperson_lead")
