from django.db import models
from django.utils import timezone
from governance.models import BarangayTenant


class SystemAuditLog(models.Model):
    ACTION_TYPES = [
        ("PORTAL_SYNC_APPROVED", "Citizen Portal Sync Approved to 201 Master"),
        ("CERTIFICATE_PRINTED", "Official Certificate / Clearance Printed"),
        ("VAWC_RECORD_ACCESSED", "VAWC / BCPC Confidential Record Accessed"),
        ("BLOTTER_CASE_REOPENED", "Blotter Case Reopened via Request Letter"),
        ("TREASURY_OR_VOIDED", "Official Receipt Voided / Adjusted"),
        ("ROLE_DELEGATION_SET", "Punong Barangay Acting Delegation Updated"),
    ]
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="audit_logs")
    action_type = models.CharField(max_length=30, choices=ACTION_TYPES)
    actor_name = models.CharField(max_length=150)
    actor_role = models.CharField(max_length=100, default="Barangay Secretary")
    reference_code = models.CharField(max_length=80)
    details = models.TextField()
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {self.get_action_type_display()} — {self.reference_code}"


class DILGComplianceReport(models.Model):
    REPORT_CATEGORIES = [
        ("KP_LUPON_MONTHLY", "Katarungang Pambarangay (KP) Monthly Case Report"),
        ("BDRRMC_QUARTERLY", "BDRRMC Preparedness & Fund Utilization Report"),
        ("FULL_DISCLOSURE_BOARD", "Barangay Full Disclosure Policy (BFDP) Posting"),
        ("KASAMBAHAY_REGISTRY", "Kasambahay Masterlist Report (RA 10361)"),
        ("BADAC_ANTI_DRUG", "BADAC Monthly Anti-Drug Accomplishment Report"),
        ("SK_ABYIP_CBYDP", "SK ABYIP / CBYDP Youth Investment Transmittal"),
    ]
    STATUS_CHOICES = [
        ("PENDING_PREPARATION", "Pending Preparation"),
        ("SUBMITTED_DILG_CITY", "Submitted to DILG / City Hall"),
        ("VERIFIED_COMPLIANT", "Verified Compliant (Receiving Stamp Logged)"),
    ]
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="dilg_reports")
    report_category = models.CharField(max_length=30, choices=REPORT_CATEGORIES)
    reporting_period = models.CharField(max_length=80)
    due_date = models.DateField()
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default="PENDING_PREPARATION")
    transmittal_reference = models.CharField(max_length=80, blank=True)
    submitted_by = models.CharField(max_length=120, blank=True)
    uploaded_copy = models.FileField(upload_to="dilg_reports/", blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_date", "-updated_at"]

    def __str__(self):
        return f"{self.get_report_category_display()} — {self.reporting_period} ({self.get_status_display()})"
class COAAuditCompliance(models.Model):
    AUDIT_TYPES = [
        ("CASH_BOOK_MONTHLY", "Monthly Cashbook & OR Remittance Reconciliation"),
        ("DV_LIQUIDATION_VOUCHER", "Disbursement Voucher (DV) & Liquidation Package"),
        ("ANNUAL_INVENTORY_COA", "COA Annual Physical Count of Property & Equipment"),
        ("BDRRMF_UTILIZATION_COA", "COA BDRRMF 70% / 30% QRF Fund Utilization Report"),
        ("COA_AOM_FINDING", "COA Audit Observation Memorandum (AOM) Compliance"),
    ]
    STATUS_CHOICES = [
        ("FOR_VERIFICATION", "For Barangay Treasurer / Bookkeeper Review"),
        ("SUBMITTED_CITY_ACCT", "Submitted to City Accountant / COA Audit Team"),
        ("CLEARED_LIQUIDATED", "Cleared / Liquidated"),
    ]
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="coa_audits")
    audit_reference = models.CharField(max_length=60, unique=True)
    audit_type = models.CharField(max_length=30, choices=AUDIT_TYPES)
    period_covered = models.CharField(max_length=80)
    amount_involved = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default="FOR_VERIFICATION")
    remarks = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.audit_reference} — {self.get_audit_type_display()} ({self.get_status_display()})"
