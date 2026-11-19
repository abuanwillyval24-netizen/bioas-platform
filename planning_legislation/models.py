from django.db import models
from django.utils import timezone
from governance.models import BarangayTenant


class LegislativeMeasure(models.Model):
    MEASURE_TYPES = [
        ("ORDINANCE", "Barangay Ordinance"),
        ("RESOLUTION", "Sangguniang Barangay Resolution"),
        ("EXECUTIVE_ORDER", "Punong Barangay Executive Order (EO)"),
        ("SESSION_MINUTES", "Regular / Special Session Minutes"),
    ]
    STATUS_CHOICES = [
        ("FIRST_READING", "First Reading / Committee Referral"),
        ("ENACTED_APPROVED", "Enacted / Approved by Council"),
        ("TRANSMITTED_SP", "Transmitted to Sangguniang Panlungsod / Bayan"),
        ("REPEALED_ARCHIVED", "Repealed / Archived"),
    ]
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="legislative_measures")
    measure_type = models.CharField(max_length=25, choices=MEASURE_TYPES, default="RESOLUTION")
    series_number = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=220)
    authored_by = models.CharField(max_length=150)
    session_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default="ENACTED_APPROVED")
    signed_document = models.FileField(upload_to="legislative_docs/", blank=True, null=True)
    summary = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-session_date", "-created_at"]

    def __str__(self):
        return f"{self.get_measure_type_display()} #{self.series_number} — {self.title}"


class DevelopmentPlanProject(models.Model):
    SECTOR_CHOICES = [
        ("INFRASTRUCTURE", "Infrastructure & Public Works (20% Dev Fund)"),
        ("PEACE_ORDER_BDRRM", "Peace & Order / BDRRMC Preparedness"),
        ("HEALTH_NUTRITION", "Health, Nutrition & Sanitation"),
        ("SOCIAL_EDUCATION", "Social Welfare, Senior Citizens & Education"),
        ("LIVELIHOOD_ENV", "Livelihood, Agriculture & Solid Waste"),
    ]
    STATUS_CHOICES = [
        ("PROGRAMMED_AIP", "Programmed in AIP / BDP"),
        ("PROCUREMENT_BIDDING", "Under Procurement / Bidding"),
        ("ONGOING_IMPLEMENTATION", "Ongoing Implementation"),
        ("COMPLETED_TURNED_OVER", "Completed & Turned Over"),
    ]
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="bdp_projects")
    aip_reference_code = models.CharField(max_length=50, unique=True)
    project_title = models.CharField(max_length=200)
    sector = models.CharField(max_length=25, choices=SECTOR_CHOICES, default="INFRASTRUCTURE")
    fiscal_year = models.PositiveIntegerField(default=2026)
    allocated_budget = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default="PROGRAMMED_AIP")
    target_completion_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fiscal_year", "aip_reference_code"]

    def __str__(self):
        return f"[{self.fiscal_year}] {self.aip_reference_code} — {self.project_title}"
