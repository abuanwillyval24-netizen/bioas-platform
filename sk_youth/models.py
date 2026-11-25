from django.db import models
from django.utils import timezone
from governance.models import BarangayTenant
from citizens.models import CitizenProfile


class KatipunanKabataanProfile(models.Model):
    YOUTH_CLASSIFICATIONS = [
        ("IN_SCHOOL", "In-School Youth (ISY)"),
        ("OUT_OF_SCHOOL", "Out-of-School Youth (OSY)"),
        ("WORKING_YOUTH", "Working Youth (WY)"),
        ("SPECIFIC_NEEDS", "Youth with Specific Needs (PWD / IP / Teen Parent)"),
    ]
    EDUCATION_LEVELS = [
        ("JUNIOR_HIGH", "Junior High School"),
        ("SENIOR_HIGH", "Senior High School"),
        ("TECH_VOC", "Technical / Vocational (TESDA)"),
        ("COLLEGE_UNDERGRAD", "College / Undergraduate"),
        ("COLLEGE_GRADUATE", "College Graduate / Post-Grad"),
    ]
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="kk_youth_profiles")
    citizen = models.OneToOneField(CitizenProfile, on_delete=models.CASCADE, related_name="kk_profile")
    youth_classification = models.CharField(max_length=25, choices=YOUTH_CLASSIFICATIONS, default="IN_SCHOOL")
    education_level = models.CharField(max_length=25, choices=EDUCATION_LEVELS, default="SENIOR_HIGH")
    is_sk_registered_voter = models.BooleanField(default=True)
    attended_last_kk_assembly = models.BooleanField(default=False)
    skills_and_interests = models.CharField(max_length=200, blank=True)
    registered_date = models.DateField(default=timezone.localdate)

    class Meta:
        ordering = ["-registered_date"]

    def __str__(self):
        return f"KK Youth: {self.citizen.full_name} ({self.get_youth_classification_display()})"


class SKProjectActivity(models.Model):
    PROJECT_CATEGORIES = [
        ("SPORTS_WELLNESS", "Sports League & Youth Wellness"),
        ("EDUCATION_SCHOLARSHIP", "Educational Assistance / School Supplies"),
        ("ENVIRONMENT_CLEANUP", "Tree Planting & Green Youth Drive"),
        ("LIVELIHOOD_SKILLS", "Digital Skills & Youth Livelihood Training"),
        ("KK_ASSEMBLY", "Mandatory Katipunan ng Kabataan (KK) Assembly"),
    ]
    STATUS_CHOICES = [
        ("PLANNED_ABYIP", "Planned (In ABYIP)"),
        ("ONGOING", "Ongoing Implementation"),
        ("COMPLETED", "Completed & Liquidated"),
    ]
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="sk_projects")
    project_code = models.CharField(max_length=45, unique=True)
    title = models.CharField(max_length=160)
    category = models.CharField(max_length=30, choices=PROJECT_CATEGORIES)
    allocated_budget = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    event_date = models.DateField(default=timezone.localdate)
    youth_participants_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default="PLANNED_ABYIP")
    sk_chairperson_lead = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-event_date", "-created_at"]

    def __str__(self):
        return f"{self.project_code} — {self.title} ({self.get_status_display()})"


class SKOfficialSeat(models.Model):
    SK_POSITIONS = [
        ("SK_CHAIRPERSON", "SK Chairperson (Ex-Officio Councilor)"),
        ("SK_KAGAWAD", "SK Kagawad (Elected)"),
        ("SK_SECRETARY", "SK Secretary (Appointed)"),
        ("SK_TREASURER", "SK Treasurer (Appointed)"),
    ]
    TERM_STATUS = [("ACTIVE", "Active Term"), ("ARCHIVED", "Archived (Past Term)")]
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="sk_seats")
    citizen = models.ForeignKey(CitizenProfile, on_delete=models.CASCADE, related_name="sk_seats")
    position = models.CharField(max_length=25, choices=SK_POSITIONS)
    term_label = models.CharField(max_length=60, default="2023-2026 SK Term")
    election_date = models.DateField(default=timezone.localdate)
    term_status = models.CharField(max_length=15, choices=TERM_STATUS, default="ACTIVE", db_index=True)
    appointed_by = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.citizen and self.citizen.birth_date and self.election_date:
            b, e = self.citizen.birth_date, self.election_date
            age_on_elec = e.year - b.year - ((e.month, e.day) < (b.month, b.day))
            if self.term_status == "ACTIVE" and (age_on_elec < 18 or age_on_elec > 24):
                raise ValidationError(f"RA 10742 Rule: Candidate must be 18 to 24 years old on Election Day (calculated age: {age_on_elec}).")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
