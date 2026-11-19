from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from governance.models import BarangayTenant
from citizens.models import CitizenProfile


class BlotterCase(models.Model):
    CASE_CATEGORIES = [
        ("KP_CIVIL_DISPUTE", "Katarungang Pambarangay — Civil / Neighborhood Dispute"),
        ("KP_MINOR_OFFENSE", "Katarungang Pambarangay — Minor Offense"),
        ("POLICE_BLOTTER", "General Incident / Police Blotter Entry"),
        ("VAWC_RA9262", "VAWC / Violence Against Women & Children (RA 9262 — Confidential)"),
        ("CHILD_PROTECTION", "BCPC / Child Protection Case (Confidential)"),
    ]
    STAGE_CHOICES = [
        ("MEDIATION_PB", "Mediation (Punong Barangay — First 15 Days)"),
        ("CONCILIATION_PANGKAT", "Conciliation (Pangkat ng Tagapagkasundo)"),
        ("ARBITRATION", "Arbitration Award"),
        ("SETTLED_AMICABLE", "Amicably Settled (Cleared)"),
        ("CFA_ISSUED", "Certificate to File Action (CFA) Issued"),
        ("CLOSED_ARCHIVED", "Closed / Archived"),
        ("REOPENED_REVIEW", "Reopened for Formal Review (Party Request Letter)"),
    ]

    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="blotter_cases")
    case_number = models.CharField(max_length=45, unique=True)
    category = models.CharField(max_length=30, choices=CASE_CATEGORIES, default="KP_CIVIL_DISPUTE")
    is_vawc_confidential = models.BooleanField(default=False)

    complainant_citizen = models.ForeignKey(CitizenProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="filed_cases")
    complainant_name = models.CharField(max_length=150)
    respondent_citizen = models.ForeignKey(CitizenProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="respondent_cases")
    respondent_name = models.CharField(max_length=150)

    incident_date = models.DateField(default=timezone.localdate)
    incident_location = models.CharField(max_length=200)
    narrative_summary = models.TextField()

    stage = models.CharField(max_length=25, choices=STAGE_CHOICES, default="MEDIATION_PB")
    blocks_clearance = models.BooleanField(default=True)
    presiding_officer = models.CharField(max_length=150, blank=True)

    reopen_requested_by = models.CharField(max_length=150, blank=True)
    reopen_request_letter = models.FileField(upload_to="blotter_reopen_letters/", blank=True, null=True)
    reopen_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        if self.stage == "REOPENED_REVIEW" and not self.reopen_request_letter and not self.reopen_requested_by.strip():
            raise ValidationError(
                {"reopen_request_letter": "A formal Request Letter and Requesting Party Name are required to reopen a closed case."}
            )

    def save(self, *args, **kwargs):
        if self.category in ("VAWC_RA9262", "CHILD_PROTECTION"):
            self.is_vawc_confidential = True
        self.blocks_clearance = self.stage not in ("SETTLED_AMICABLE", "CLOSED_ARCHIVED")
        super().save(*args, **kwargs)

    @property
    def masked_title(self):
        if self.is_vawc_confidential:
            return f"{self.case_number} [SEALED VAWC / BCPC RECORD — RA 9262 CONFIDENTIAL]"
        return f"{self.case_number} — {self.complainant_name} vs. {self.respondent_name}"

    def __str__(self):
        return self.masked_title
