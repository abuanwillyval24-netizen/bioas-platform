from django.contrib import admin
from .models import BarangayVehicle, VehicleTripTicket, CommunityEquipmentLoan


@admin.register(BarangayVehicle)
class BarangayVehicleAdmin(admin.ModelAdmin):
    list_display = ("plate_or_body_number", "vehicle_name", "vehicle_type", "assigned_driver", "status", "current_odometer_km")
    list_filter = ("barangay", "vehicle_type", "status")
    search_fields = ("plate_or_body_number", "vehicle_name", "assigned_driver")


@admin.register(VehicleTripTicket)
class VehicleTripTicketAdmin(admin.ModelAdmin):
    list_display = ("ticket_number", "vehicle", "driver_name", "purpose", "destination", "trip_date", "fuel_liters_issued")
    list_filter = ("barangay", "purpose", "trip_date")
    search_fields = ("ticket_number", "driver_name", "destination")


@admin.register(CommunityEquipmentLoan)
class CommunityEquipmentLoanAdmin(admin.ModelAdmin):
    list_display = ("borrower_name", "equipment_description", "quantity", "date_borrowed", "expected_return_date", "status")
    list_filter = ("barangay", "status", "date_borrowed")
    search_fields = ("borrower_name", "equipment_description", "purpose_or_event")
