from django.db import models
from django.utils import timezone
from governance.models import BarangayTenant
from citizens.models import CitizenProfile


class HealthConsultationRecord(models.Model):
    PROGRAM_TYPES = [
        ("MATERNAL_PRENATAL", "Maternal / Prenatal & Postpartum Care"),
        ("CHILD_IMMUNIZATION", "Child Immunization (EPI — BCG / Penta / OPV / MMR)"),
        ("NUTRITION_OPT", "Operation Timbang (OPT) / Child Nutrition Monitoring"),
        ("SENIOR_MAINTENANCE", "Senior Citizen / Hypertension & Diabetes Maintenance"),
        ("MEDICAL_REFERRAL", "Hospital / RHU / PhilHealth Medical Assistance Referral"),
    ]
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="health_records")
    citizen = models.ForeignKey(CitizenProfile, on_delete=models.CASCADE, related_name="health_records")
    program_type = models.CharField(max_length=30, choices=PROGRAM_TYPES)
    visit_date = models.DateField(default=timezone.localdate)
    blood_pressure = models.CharField(max_length=25, blank=True)
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    vaccine_or_medicine_given = models.CharField(max_length=150, blank=True)
    next_schedule_date = models.DateField(blank=True, null=True)
    attending_bhw_or_midwife = models.CharField(max_length=120)
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-visit_date", "-created_at"]

    def __str__(self):
        return f"{self.citizen.full_name} — {self.get_program_type_display()} ({self.visit_date})"


class HealthMedicineInventory(models.Model):
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="medicine_stocks")
    item_code = models.CharField(max_length=40)
    medicine_name = models.CharField(max_length=150)
    unit = models.CharField(max_length=30, default="Tablets / Boxes")
    quantity_on_hand = models.PositiveIntegerField(default=0)
    reorder_level = models.PositiveIntegerField(default=20)
    expiration_date = models.DateField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("barangay", "item_code")
        ordering = ["expiration_date", "medicine_name"]

    @property
    def is_low_stock(self):
        return self.quantity_on_hand <= self.reorder_level

    def __str__(self):
        return f"{self.medicine_name} ({self.quantity_on_hand} {self.unit})"
