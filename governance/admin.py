from django.contrib import admin
from .models import (
    Province,
    CityMunicipality,
    BarangayTenant,
    LetterheadVersion,
    OccasionTheme,
    AreaSubdivision,
    PhysicalStructure,
    OfficialSeat,
    TermAssignment,
    ActingDesignation,
)


@admin.register(Province)
class ProvinceAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "region", "governor_office_name")
    search_fields = ("code", "name")


@admin.register(CityMunicipality)
class CityMunicipalityAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "lgu_type", "province", "mayor_office_name")
    list_filter = ("province", "lgu_type")
    search_fields = ("code", "name")


@admin.register(BarangayTenant)
class BarangayTenantAdmin(admin.ModelAdmin):
    list_display = (
        "tenant_code",
        "name",
        "city_municipality",
        "status",
        "fee_collection_enabled",
        "provisioned_at",
    )
    list_filter = ("status", "city_municipality", "fee_collection_enabled")
    search_fields = ("tenant_code", "name", "provisioning_authority_ref")


@admin.register(LetterheadVersion)
class LetterheadVersionAdmin(admin.ModelAdmin):
    list_display = ("barangay", "version_label", "effective_from", "effective_until", "is_current")
    list_filter = ("barangay", "is_current")


@admin.register(OccasionTheme)
class OccasionThemeAdmin(admin.ModelAdmin):
    list_display = ("barangay", "occasion_name", "start_date", "end_date", "is_active")
    list_filter = ("barangay", "is_active")


@admin.register(AreaSubdivision)
class AreaSubdivisionAdmin(admin.ModelAdmin):
    list_display = ("barangay", "area_type", "name", "is_active")
    list_filter = ("barangay", "area_type", "is_active")
    search_fields = ("name",)


@admin.register(PhysicalStructure)
class PhysicalStructureAdmin(admin.ModelAdmin):
    list_display = (
        "house_code",
        "barangay",
        "subdivision",
        "street_name",
        "occupancy_type",
        "property_owner_name",
    )
    list_filter = ("barangay", "subdivision", "occupancy_type")
    search_fields = ("house_code", "street_name", "property_owner_name")


@admin.register(OfficialSeat)
class OfficialSeatAdmin(admin.ModelAdmin):
    list_display = (
        "seat_code",
        "seat_title",
        "category",
        "barangay",
        "can_approve_clearances",
        "can_collect_fees",
        "can_manage_blotter",
    )
    list_filter = ("barangay", "category", "can_approve_clearances")
    search_fields = ("seat_code", "seat_title", "committee_assignment")


@admin.register(TermAssignment)
class TermAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "official_full_name",
        "seat",
        "term_label",
        "term_start",
        "term_end",
        "status",
    )
    list_filter = ("status", "term_label", "seat__barangay")
    search_fields = ("official_full_name", "oath_or_appointment_ref")


@admin.register(ActingDesignation)
class ActingDesignationAdmin(admin.ModelAdmin):
    list_display = (
        "acting_official_name",
        "seat",
        "valid_from",
        "valid_until",
        "allow_clearance_signing",
        "is_active",
    )
    list_filter = ("is_active", "seat__barangay")
    search_fields = ("acting_official_name", "designation_order_ref")
from .models import OfficialTurnoverRecord


@admin.register(OfficialTurnoverRecord)
class OfficialTurnoverRecordAdmin(admin.ModelAdmin):
    list_display = ("transition_cycle", "outgoing_punong_barangay", "incoming_punong_barangay", "turnover_date", "status", "barangay")
    list_filter = ("barangay", "status", "turnover_date")
    search_fields = ("transition_cycle", "outgoing_punong_barangay", "incoming_punong_barangay")
from .models import BarangayStaffProfile, TermArchiveSnapshot


@admin.register(BarangayStaffProfile)
class BarangayStaffProfileAdmin(admin.ModelAdmin):
    list_display = ("seat_code", "full_name", "role", "barangay", "approval_status", "term_start_date", "approved_by")
    list_filter = ("barangay", "role", "approval_status")
    search_fields = ("full_name", "seat_code", "user__username", "committee_or_unit")


@admin.register(TermArchiveSnapshot)
class TermArchiveSnapshotAdmin(admin.ModelAdmin):
    list_display = ("term_label", "barangay", "scoped_start_date", "scoped_end_date", "outgoing_captain_name", "incoming_captain_name", "oath_taking_doc_ref", "executed_at")
    list_filter = ("barangay",)
    readonly_fields = ("archived_counts_json", "roster_snapshot_json", "executed_at")
