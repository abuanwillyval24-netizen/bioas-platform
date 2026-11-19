from django.contrib import admin
from .models import SocialAidDistribution, AssociationGroup, AssociationMember


@admin.register(SocialAidDistribution)
class SocialAidDistributionAdmin(admin.ModelAdmin):
    list_display = ("citizen", "program_category", "distribution_cycle", "amount_or_pack_value", "status")
    list_filter = ("barangay", "program_category", "status", "distribution_cycle")
    search_fields = ("citizen__last_name", "citizen__first_name", "distribution_cycle", "voucher_or_payroll_ref")


@admin.register(AssociationGroup)
class AssociationGroupAdmin(admin.ModelAdmin):
    list_display = ("group_code", "group_name", "display_head", "is_active", "barangay")
    list_filter = ("barangay", "is_active")
    search_fields = ("group_code", "group_name", "head_name_override", "association_head__last_name")


@admin.register(AssociationMember)
class AssociationMemberAdmin(admin.ModelAdmin):
    list_display = ("association", "citizen", "role_in_group", "joined_date")
    list_filter = ("association", "role_in_group")
    search_fields = ("citizen__last_name", "citizen__first_name", "association__group_name")
