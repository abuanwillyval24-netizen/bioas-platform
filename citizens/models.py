from django.db import models
from django.utils import timezone
from governance.models import BarangayTenant, PhysicalStructure


class Household(models.Model):
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="households")
    structure = models.ForeignKey(PhysicalStructure, on_delete=models.SET_NULL, null=True, blank=True, related_name="households")
    household_code = models.CharField(max_length=50, unique=True)
    household_head_name = models.CharField(max_length=150)
    monthly_income_bracket = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.household_code} — {self.household_head_name}"


class CitizenProfile(models.Model):
    SEX_CHOICES = [("MALE", "Male"), ("FEMALE", "Female")]
    GENDER_CHOICES = [
        ("MALE", "Male"),
        ("FEMALE", "Female"),
        ("NON_BINARY", "Non-Binary"),
        ("TRANSGENDER", "Transgender"),
        ("PREFER_NOT_TO_SAY", "Prefer not to say"),
    ]
    CIVIL_STATUS_CHOICES = [
        ("SINGLE", "Single"),
        ("MARRIED", "Married"),
        ("WIDOWED", "Widowed"),
        ("SEPARATED", "Separated"),
    ]
    STATUS_CHOICES = [
        ("PENDING_APPROVAL", "Pending Portal Approval"),
        ("ACTIVE_RESIDENT", "Active Verified Resident"),
        ("TRANSFERRED_OUT", "Transferred Out"),
        ("DECEASED", "Deceased"),
    ]
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="citizens")
    household = models.ForeignKey(Household, on_delete=models.SET_NULL, null=True, blank=True, related_name="members")
    citizen_qr_id = models.CharField(max_length=40, unique=True)
    last_name = models.CharField(max_length=80)
    first_name = models.CharField(max_length=80)
    middle_name = models.CharField(max_length=80, blank=True)
    suffix = models.CharField(max_length=20, blank=True)
    sex = models.CharField(max_length=10, choices=SEX_CHOICES)
    gender_identity = models.CharField(max_length=25, choices=GENDER_CHOICES, default="PREFER_NOT_TO_SAY")
    birth_date = models.DateField()
    civil_status = models.CharField(max_length=20, choices=CIVIL_STATUS_CHOICES, default="SINGLE")
    mobile_number = models.CharField(max_length=30, blank=True)
    is_registered_voter = models.BooleanField(default=False)
    is_senior_citizen = models.BooleanField(default=False)
    is_pwd = models.BooleanField(default=False)
    is_solo_parent = models.BooleanField(default=False)
    is_4ps_beneficiary = models.BooleanField(default=False)
    is_first_time_jobseeker = models.BooleanField(default=False)
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default="ACTIVE_RESIDENT")
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def full_name(self):
        parts = [self.first_name, self.middle_name, self.last_name, self.suffix]
        return " ".join(p for p in parts if p)

    def __str__(self):
        return f"{self.full_name} ({self.citizen_qr_id})"


class CitizenPortalUpdateRequest(models.Model):
    STATUS_CHOICES = [
        ("PENDING_REVIEW", "Pending Secretary Review"),
        ("APPROVED_MERGED", "Approved & Synced to 201 Master"),
        ("REJECTED", "Rejected"),
    ]
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="portal_updates")
    citizen = models.ForeignKey(CitizenProfile, on_delete=models.CASCADE, related_name="update_requests")
    requested_mobile_number = models.CharField(max_length=30, blank=True)
    requested_civil_status = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING_REVIEW")
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Update Request — {self.citizen.full_name} ({self.get_status_display()})"


class CitizenCommunityReport(models.Model):
    REPORT_CATEGORIES = [
        ("INFRASTRUCTURE_LIGHT", "Broken Streetlight / Road & Drainage Issue"),
        ("PEACE_ORDER_NOISE", "Peace & Order / Curfew / Noise Concern"),
        ("SANITATION_WASTE", "Garbage Collection / Drainage Clogging"),
        ("DRRM_HAZARD", "Flood / Fallen Tree / Emergency Hazard Report"),
        ("GENERAL_SUGGESTION", "General Inquiry / Suggestion for Barangay Council"),
    ]
    STATUS_CHOICES = [
        ("SUBMITTED_OPEN", "Submitted / Open for Action"),
        ("DISPATCHED_TANOD_WO", "Dispatched to Tanod / Maintenance Work Order"),
        ("RESOLVED_CLOSED", "Resolved / Closed"),
    ]
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="citizen_reports")
    citizen = models.ForeignKey(CitizenProfile, on_delete=models.CASCADE, related_name="community_reports")
    tracking_code = models.CharField(max_length=40, unique=True)
    category = models.CharField(max_length=30, choices=REPORT_CATEGORIES)
    location_landmark = models.CharField(max_length=160)
    description = models.TextField()
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default="SUBMITTED_OPEN")
    barangay_remarks = models.CharField(max_length=220, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.tracking_code} — {self.citizen.full_name} ({self.get_status_display()})"
