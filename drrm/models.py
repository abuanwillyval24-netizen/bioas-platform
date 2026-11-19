from django.db import models
from django.utils import timezone
from governance.models import BarangayTenant, AreaSubdivision


class HazardIncidentAlert(models.Model):
    HAZARD_TYPES = [
        ("FLOOD_WATER_LEVEL", "Flooding / River & Creek Water Level"),
        ("TYPHOON_STORM", "Typhoon / Severe Wind & Rain"),
        ("FIRE_INCIDENT", "Structural / Grass Fire Incident"),
        ("EARTHQUAKE_AFTERSHOCK", "Earthquake / Infrastructure Damage"),
        ("HEALTH_OUTBREAK", "Dengue / Waterborne / Public Health Advisory"),
    ]
    ALERT_LEVELS = [
        ("NORMAL_MONITORING", "Blue / Normal Monitoring"),
        ("YELLOW_ADVISORY", "Yellow / Preparedness Advisory"),
        ("ORANGE_ALERT", "Orange / Pre-Emptive Evacuation Alert"),
        ("RED_MANDATORY", "Red / Mandatory Evacuation & Emergency"),
        ("RESOLVED_CLEARED", "Resolved / All Clear"),
    ]
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="hazard_alerts")
    subdivision = models.ForeignKey(AreaSubdivision, on_delete=models.SET_NULL, null=True, blank=True, related_name="hazard_alerts")
    alert_code = models.CharField(max_length=45, unique=True)
    hazard_type = models.CharField(max_length=30, choices=HAZARD_TYPES)
    alert_level = models.CharField(max_length=25, choices=ALERT_LEVELS, default="YELLOW_ADVISORY")
    title = models.CharField(max_length=160)
    situation_report = models.TextField()
    affected_families_count = models.PositiveIntegerField(default=0)
    reported_by = models.CharField(max_length=120)
    reported_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-reported_at"]

    def __str__(self):
        return f"[{self.get_alert_level_display()}] {self.title} ({self.barangay.name})"


class EvacuationCenterStatus(models.Model):
    STATUS_CHOICES = [
        ("STANDBY_READY", "Standby / Ready for Activation"),
        ("ACTIVE_OPEN", "Active / Accepting Evacuees"),
        ("FULL_CAPACITY", "At Full Capacity"),
        ("CLOSED_DEACTIVATED", "Closed / Evacuees Returned Home"),
    ]
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="evacuation_centers")
    center_name = models.CharField(max_length=150)
    location_address = models.CharField(max_length=200)
    max_family_capacity = models.PositiveIntegerField(default=50)
    current_families_housed = models.PositiveIntegerField(default=0)
    current_individuals_housed = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default="STANDBY_READY")
    camp_manager = models.CharField(max_length=120, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["center_name"]

    def __str__(self):
        return f"{self.center_name} — {self.current_families_housed}/{self.max_family_capacity} Families ({self.get_status_display()})"
