from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from governance.models import BarangayTenant, LetterheadVersion
from citizens.models import CitizenProfile


class CertificateRequest(models.Model):
    CERT_TYPES = [
        ("BARANGAY_CLEARANCE", "Barangay Clearance"),
        ("BUSINESS_CLEARANCE", "Barangay Business Clearance / Permit Endorsement"),
        ("INDIGENCY", "Certificate of Indigency (Fee-Exempt)"),
        ("FIRST_TIME_JOBSEEKER", "First-Time Jobseeker Certification — RA 11261 (Fee-Exempt)"),
        ("RESIDENCY", "Certificate of Residency"),
        ("GOOD_MORAL", "Certificate of Good Moral Character"),
        ("SOLO_PARENT", "Solo Parent / Senior / PWD Endorsement"),
        ("BUILDING_FENCING", "Barangay Building / Fencing Clearance"),
        ("LUPON_CFA", "Lupon Certificate to File Action (CFA)"), ("OTHER_CERT", "Others (Custom Barangay Certification / Endorsement)"),
    ]

    STATUS_CHOICES = [
        ("PENDING_REVIEW", "Submitted — Pending"),
        ("PENDING_OR", "Forwarded to Treasurer — Pending OR Payment"),
        ("PENDING_COUNCILOR", "Pending Purok Councilor Endorsement"),
        ("PENDING_CAPTAIN", "Pending Punong Barangay Final Approval"),
        ("READY_TO_PRINT", "Captain Approved — Ready to Print & Dry Seal"),
        ("ISSUED_PRINTED", "Issued, Sealed & Released"), ("RELEASED", "Issued, Sealed & Released"),
        ("REJECTED_HOLD", "Blocked / Rejected"),
        ("RETURNED_FOR_CORRECTION", "Returned to Citizen — Missing / Incomplete Docs"),
    ]

    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="certificates")
    citizen = models.ForeignKey(CitizenProfile, on_delete=models.PROTECT, related_name="certificates")
    control_number = models.CharField(max_length=45, unique=True)
    cert_type = models.CharField(max_length=30, choices=CERT_TYPES)
    purpose = models.CharField(max_length=200)

    is_fee_exempt = models.BooleanField(default=False)
    fee_amount = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    official_receipt_number = models.CharField(max_length=60, blank=True)
    or_date = models.DateField(blank=True, null=True)

    letterhead_snapshot = models.ForeignKey(LetterheadVersion, on_delete=models.SET_NULL, null=True, blank=True)
    assigned_councilor = models.ForeignKey("governance.BarangayStaffProfile", on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_certificates")
    councilor_endorsed_by = models.CharField(max_length=150, blank=True)
    captain_approved_by = models.CharField(max_length=150, blank=True)
    signatory_name = models.CharField(max_length=150, blank=True)
    signatory_title = models.CharField(max_length=150, default="Punong Barangay")
    is_acting_signatory = models.BooleanField(default=False)

    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="PENDING_REVIEW")
    issued_date = models.DateField(default=timezone.localdate)
    valid_until = models.DateField(blank=True, null=True)
    issued_by = models.CharField(max_length=120, blank=True)
    hold_or_delay_reason = models.CharField(max_length=240, blank=True)
    citizen_dispute_note = models.TextField(blank=True)
    dispute_status = models.CharField(max_length=25, choices=[("NONE", "None"), ("DISPUTE_OPEN", "Post-Release Error / Hold Inquiry Open"), ("REISSUED_RESOLVED", "Resolved / Re-Issued")], default="NONE")
    office_dispute_reply = models.CharField(max_length=240, blank=True)
    source_channel = models.CharField(max_length=25, default="WALKIN_DESK")
    intake_desk = models.CharField(max_length=30, default="SECRETARY_ADMIN")
    assessment_tags = models.CharField(max_length=250, blank=True)
    assessment_remarks = models.TextField(blank=True)
    assessed_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        if self.citizen and not self.citizen.can_issue_clearance():
            raise ValidationError(
                {"citizen": f"Cannot issue certificate: Citizen status is '{self.citizen.get_status_display()}'."}
            )
        if self.cert_type in ("INDIGENCY", "FIRST_TIME_JOBSEEKER"):
            self.is_fee_exempt = True
            self.fee_amount = 0.00
        super().save(*args, **kwargs)

    def get_intake_desk_label(self):
        m = {"SECRETARY_ADMIN": "Admin / Business / Secretary Intake", "SOCIAL_WELFARE": "Social Welfare / BHW Desk", "LUPON_VAWC": "Lupon / VAWC Desk", "HEALTH_BHS": "Barangay Health Station Desk"}
        return m.get(self.intake_desk, "Admin / Business / Secretary Intake")

    def get_current_holder_label(self):
        if self.status == "PENDING_REVIEW":
            return f"At {self.get_intake_desk_label()}"
        if self.status == "PENDING_OR":
            return "At Treasury Module (Pending OR Payment)"
        if self.status == "PENDING_COUNCILOR":
            return f"At Purok Councilor ({self.assigned_councilor.full_name})" if self.assigned_councilor else "At Purok Councilor Endorsement"
        if self.status == "PENDING_CAPTAIN":
            return "At Punong Barangay Final Sign-Off"
        if self.status == "READY_TO_PRINT":
            return "Secretary Queue — Ready for Print & Dry Seal"
        if self.status == "RETURNED_FOR_CORRECTION":
            return "Returned to Citizen (Missing Docs)"
        return self.get_status_display()

    def __str__(self):
        return f"{self.control_number} — {self.get_cert_type_display()} ({self.citizen.full_name})"
