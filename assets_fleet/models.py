from django.db import models
from django.utils import timezone
from governance.models import BarangayTenant
from citizens.models import CitizenProfile


class BarangayVehicle(models.Model):
    VEHICLE_TYPES = [
        ("PATROL_CAR", "Barangay Tanod Patrol Vehicle"),
        ("AMBULANCE_RESCUE", "Barangay Ambulance / Emergency Rescue"),
        ("GARBAGE_DUMP_TRUCK", "Solid Waste / Garbage Dump Truck"),
        ("MULTICAB_SERVICE", "Multicab / Service Utility Vehicle"),
        ("RESCUE_BOAT", "BDRRMC Fiber / Rubber Rescue Boat"),
    ]
    STATUS_CHOICES = [
        ("OPERATIONAL", "Operational / Ready for Dispatch"),
        ("DISPATCHED_TRIP", "Currently on Trip / Dispatched"),
        ("UNDER_MAINTENANCE", "Under Repair / Maintenance"),
    ]
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="vehicles")
    plate_or_body_number = models.CharField(max_length=40, unique=True)
    vehicle_name = models.CharField(max_length=120)
    vehicle_type = models.CharField(max_length=25, choices=VEHICLE_TYPES)
    assigned_driver = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default="OPERATIONAL")
    current_odometer_km = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["vehicle_name"]

    def __str__(self):
        return f"{self.vehicle_name} [{self.plate_or_body_number}] ({self.get_status_display()})"


class VehicleTripTicket(models.Model):
    TRIP_PURPOSES = [
        ("EMERGENCY_MEDICAL", "Emergency Medical / Patient Transport"),
        ("PEACE_ORDER_PATROL", "Peace & Order / Night Patrol"),
        ("DISASTER_RESCUE", "Disaster Response / Evacuation"),
        ("GARBAGE_COLLECTION", "Scheduled Garbage / Waste Hauling"),
        ("OFFICIAL_ERRAND", "Official LGU / City Hall Errand"),
    ]
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="trip_tickets")
    ticket_number = models.CharField(max_length=45, unique=True)
    vehicle = models.ForeignKey(BarangayVehicle, on_delete=models.PROTECT, related_name="trips")
    driver_name = models.CharField(max_length=120)
    purpose = models.CharField(max_length=25, choices=TRIP_PURPOSES)
    destination = models.CharField(max_length=180)
    trip_date = models.DateField(default=timezone.localdate)
    fuel_liters_issued = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    approved_by = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-trip_date", "-created_at"]

    def __str__(self):
        return f"Trip #{self.ticket_number} — {self.vehicle.vehicle_name} ({self.destination})"


class CommunityEquipmentLoan(models.Model):
    STATUS_CHOICES = [
        ("BORROWED_OUT", "Borrowed / Issued Out"),
        ("RETURNED_GOOD", "Returned in Good Condition"),
        ("RETURNED_DAMAGED", "Returned with Damage / Missing Items"),
    ]
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="equipment_loans")
    borrower_citizen = models.ForeignKey(CitizenProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="equipment_loans")
    borrower_name = models.CharField(max_length=150)
    equipment_description = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField(default=1)
    purpose_or_event = models.CharField(max_length=150)
    date_borrowed = models.DateField(default=timezone.localdate)
    expected_return_date = models.DateField()
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default="BORROWED_OUT")
    released_by = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_borrowed", "-created_at"]

    def __str__(self):
        return f"{self.equipment_description} (x{self.quantity}) — {self.borrower_name}"


class FacilityEquipmentReservation(models.Model):
    ASSET_CHOICES = [
        ("COVERED_COURT", "Barangay Covered Court / Gym"),
        ("MULTIPURPOSE_HALL", "Barangay Multipurpose Hall"),
        ("TENTS_CHAIRS", "Event Tents, Tables & Monobloc Chairs"),
        ("SOUND_SYSTEM", "Barangay Sound System / PA"),
        ("SERVICE_VEHICLE", "Barangay Utility / Service Vehicle"),
    ]
    STATUS_CHOICES = [("PENDING", "Pending Custodian Approval"), ("APPROVED", "Approved & Slot Locked"), ("REJECTED", "Declined / Unavailable"), ("COMPLETED", "Completed / Returned")]
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="reservations")
    citizen = models.ForeignKey(CitizenProfile, on_delete=models.CASCADE, related_name="facility_reservations")
    booking_code = models.CharField(max_length=32, unique=True)
    facility_or_item = models.CharField(max_length=30, choices=ASSET_CHOICES)
    reservation_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    purpose = models.CharField(max_length=180)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    custodian_remarks = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.end_time and self.start_time and self.end_time <= self.start_time:
            raise ValidationError("End time must be later than start time.")
        if self.barangay_id and self.reservation_date and self.start_time and self.end_time:
            clash = FacilityEquipmentReservation.objects.filter(
                barangay_id=self.barangay_id, facility_or_item=self.facility_or_item,
                reservation_date=self.reservation_date, status__in=["PENDING", "APPROVED"],
                start_time__lt=self.end_time, end_time__gt=self.start_time,
            ).exclude(pk=self.pk).first()
            if clash:
                raise ValidationError(f"Time-Slot Conflict Lock: Already reserved on {self.reservation_date} from {clash.start_time.strftime('%H:%M')} to {clash.end_time.strftime('%H:%M')} ({clash.booking_code}).")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
