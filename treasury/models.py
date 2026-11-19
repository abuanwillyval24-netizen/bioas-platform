from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from governance.models import BarangayTenant
from citizens.models import CitizenProfile
from documents.models import CertificateRequest


class OfficialReceipt(models.Model):
    PAYMENT_TYPES = [
        ("CLEARANCE_FEE", "Barangay Clearance / Certification Fee"),
        ("BUSINESS_PERMIT", "Barangay Business Clearance Fee"),
        ("KP_FILING_FEE", "Katarungang Pambarangay Filing Fee"),
        ("RENTAL_FACILITY", "Barangay Facility / Tent / Equipment Rental"),
        ("OTHER_COLLECTION", "Other Miscellaneous Collection"),
    ]
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="receipts")
    or_number = models.CharField(max_length=50, unique=True)
    payor_citizen = models.ForeignKey(CitizenProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="receipts")
    payor_name = models.CharField(max_length=150)
    payment_type = models.CharField(max_length=25, choices=PAYMENT_TYPES, default="CLEARANCE_FEE")
    linked_certificate = models.OneToOneField(CertificateRequest, on_delete=models.SET_NULL, null=True, blank=True, related_name="treasury_or")
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    collected_by = models.CharField(max_length=120)
    issued_date = models.DateField(default=timezone.localdate)
    is_voided = models.BooleanField(default=False)
    void_reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-issued_date", "-created_at"]

    def clean(self):
        if self.barangay and not self.barangay.fee_collection_enabled:
            raise ValidationError("Fee collection is currently disabled for this Barangay (No-Fee Mode active).")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.linked_certificate and not self.is_voided:
            cert = self.linked_certificate
            cert.official_receipt_number = self.or_number
            cert.or_date = self.issued_date
            if cert.status == "PENDING_OR":
                cert.status = "READY_TO_PRINT"
            cert.save(update_fields=["official_receipt_number", "or_date", "status"])

    def __str__(self):
        return f"OR #{self.or_number} — {self.payor_name} (₱{self.amount_paid})"


class AbuloySheet(models.Model):
    STATUS_CHOICES = [
        ("OPEN_COLLECTING", "Open / Active Collection"),
        ("CLOSED_VERIFIED", "Closed & Treasurer Verified"),
        ("RELEASED_BENEFICIARY", "Released to Beneficiary Family"),
    ]
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="abuloy_sheets")
    serial_number = models.CharField(max_length=45, unique=True)
    deceased_name = models.CharField(max_length=150)
    beneficiary_name = models.CharField(max_length=150)
    beneficiary_relationship = models.CharField(max_length=60, default="Spouse / Immediate Family")
    date_issued = models.DateField(default=timezone.localdate)
    total_collected = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default="OPEN_COLLECTING")
    verified_by_treasurer = models.CharField(max_length=120, blank=True)
    released_at = models.DateTimeField(blank=True, null=True)
    remarks = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_issued", "-created_at"]

    def __str__(self):
        return f"Abuloy Sheet {self.serial_number} — Deceased: {self.deceased_name} (₱{self.total_collected})"
