from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone


class Province(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=120, unique=True)
    region = models.CharField(max_length=100, default="Region III (Central Luzon)")
    governor_office_name = models.CharField(max_length=150, default="Office of the Provincial Governor")
    official_seal = models.ImageField(upload_to="seals/province/", blank=True, null=True)
    primary_color = models.CharField(max_length=7, default="#1E3A8A")
    secondary_color = models.CharField(max_length=7, default="#F59E0B")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"Province of {self.name}"


class CityMunicipality(models.Model):
    LGU_TYPES = [("CITY", "City"), ("MUNICIPALITY", "Municipality")]
    province = models.ForeignKey(Province, on_delete=models.PROTECT, related_name="cities")
    code = models.CharField(max_length=25, unique=True)
    name = models.CharField(max_length=120)
    lgu_type = models.CharField(max_length=20, choices=LGU_TYPES, default="CITY")
    mayor_office_name = models.CharField(max_length=150, default="Office of the City Mayor")
    official_seal = models.ImageField(upload_to="seals/city/", blank=True, null=True)
    primary_color = models.CharField(max_length=7, default="#0F4C81")
    secondary_color = models.CharField(max_length=7, default="#D97706")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Cities and Municipalities"
        unique_together = ("province", "name")
        ordering = ["name"]

    def __str__(self):
        return f"{self.name}, {self.province.name}"


class BarangayTenant(models.Model):
    PROVISION_STATUS = [
        ("PENDING_APPROVAL", "Pending City/DILG Provisioning"),
        ("TRIAL_ACTIVE", "Active Trial Pilot"),
        ("FULL_ACTIVE", "Fully Operational"),
        ("SUSPENDED", "Suspended"),
    ]
    BARANGAY_CLASSIFICATIONS = [
        ("RURAL", "Rural Barangay"),
        ("URBAN", "Urban Barangay"),
    ]
    city_municipality = models.ForeignKey(CityMunicipality, on_delete=models.PROTECT, related_name="barangays")
    tenant_code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=120)
    barangay_classification = models.CharField(max_length=15, choices=BARANGAY_CLASSIFICATIONS, default="RURAL")
    classification_supporting_doc = models.FileField(upload_to="classification_docs/", blank=True, null=True)
    classification_updated_at = models.DateTimeField(blank=True, null=True)
    classification_updated_by = models.CharField(max_length=150, blank=True)
    zip_code = models.CharField(max_length=10, default="3100")
    hall_address = models.CharField(max_length=255, blank=True)
    official_email = models.EmailField(blank=True)
    contact_number = models.CharField(max_length=30, blank=True)
    status = models.CharField(max_length=25, choices=PROVISION_STATUS, default="PENDING_APPROVAL")
    provisioning_authority_ref = models.CharField(max_length=120, blank=True)
    provisioning_document = models.FileField(upload_to="provisioning_docs/", blank=True, null=True)
    provisioned_by_name = models.CharField(max_length=120, blank=True)
    provisioned_at = models.DateTimeField(blank=True, null=True)
    term_years = models.PositiveSmallIntegerField(default=3)
    fee_collection_enabled = models.BooleanField(default=False)
    default_primary_color = models.CharField(max_length=7, default="#1E3A8A")
    default_secondary_color = models.CharField(max_length=7, default="#F59E0B")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("city_municipality", "name")
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.city_municipality.name})"

    def get_active_theme(self):
        today = timezone.localdate()
        active_occasion = self.occasion_themes.filter(is_active=True, start_date__lte=today, end_date__gte=today).first()
        if active_occasion:
            return {
                "title": active_occasion.occasion_name,
                "banner_text": active_occasion.banner_message,
                "primary_color": active_occasion.primary_color,
                "secondary_color": active_occasion.secondary_color,
                "is_occasion": True,
            }
        return {
            "title": self.name,
            "banner_text": f"Official Digital Operations Portal — {self.name}",
            "primary_color": self.default_primary_color,
            "secondary_color": self.default_secondary_color,
            "is_occasion": False,
        }


class LetterheadVersion(models.Model):
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="letterheads")
    version_label = models.CharField(max_length=50)
    barangay_logo = models.ImageField(upload_to="letterheads/logos/")
    city_logo = models.ImageField(upload_to="letterheads/city_logos/", blank=True, null=True)
    header_line_1 = models.CharField(max_length=150, default="Republic of the Philippines")
    header_line_2 = models.CharField(max_length=150, default="Province of Nueva Ecija")
    header_line_3 = models.CharField(max_length=150, default="City of Cabanatuan")
    effective_from = models.DateField(default=timezone.localdate)
    effective_until = models.DateField(blank=True, null=True)
    is_current = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_from", "-created_at"]

    def __str__(self):
        return f"{self.barangay.name} — {self.version_label}"


class OccasionTheme(models.Model):
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="occasion_themes")
    occasion_name = models.CharField(max_length=100)
    banner_message = models.CharField(max_length=200, blank=True)
    primary_color = models.CharField(max_length=7, default="#B91C1C")
    secondary_color = models.CharField(max_length=7, default="#FBBF24")
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-start_date"]

    def clean(self):
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValidationError("End date cannot be earlier than start date.")

    def __str__(self):
        return f"{self.barangay.name}: {self.occasion_name} ({self.start_date} to {self.end_date})"


class AreaSubdivision(models.Model):
    AREA_TYPES = [("PUROK", "Purok"), ("SUBDIVISION", "Subdivision"), ("ZONE", "Zone"), ("SITIO", "Sitio"), ("DISTRICT", "District")]
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="subdivisions")
    area_type = models.CharField(max_length=20, choices=AREA_TYPES, default="PUROK")
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("barangay", "area_type", "name")
        ordering = ["area_type", "name"]

    def __str__(self):
        return f"{self.get_area_type_display()} — {self.name} ({self.barangay.name})"


class PhysicalStructure(models.Model):
    OCCUPANCY_TYPES = [
        ("OWNER_OCCUPIED", "Owner-Occupied"),
        ("RENTED_TENANT", "Rented / Tenant-Occupied"),
        ("CARETAKER", "Caretaker / Rent-Free"),
        ("VACANT", "Vacant Structure"),
    ]
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="structures")
    subdivision = models.ForeignKey(AreaSubdivision, on_delete=models.PROTECT, related_name="structures")
    house_code = models.CharField(max_length=40)
    parent_structure = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="extensions")
    street_name = models.CharField(max_length=120, blank=True)
    block_lot_or_number = models.CharField(max_length=80, blank=True)
    landmark = models.CharField(max_length=150, blank=True)
    occupancy_type = models.CharField(max_length=25, choices=OCCUPANCY_TYPES, default="OWNER_OCCUPIED")
    property_owner_name = models.CharField(max_length=150, blank=True)
    owner_contact = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("barangay", "house_code")
        ordering = ["house_code"]

    def clean(self):
        if self.subdivision and self.subdivision.area_type == "SUBDIVISION" and not self.street_name.strip():
            raise ValidationError({"street_name": "Street Name is required when the citizen resides inside a Subdivision."})

    def __str__(self):
        street = f", {self.street_name}" if self.street_name else ""
        return f"{self.house_code} ({self.subdivision.name}{street})"


class OfficialSeat(models.Model):
    SEAT_CATEGORIES = [
        ("PUNONG_BARANGAY", "Punong Barangay"),
        ("KAGAWAD", "Sangguniang Barangay Member (Kagawad)"),
        ("SECRETARY", "Barangay Secretary"),
        ("TREASURER", "Barangay Treasurer"),
        ("SK_CHAIRPERSON", "SK Chairperson"),
        ("LUPON", "Lupong Tagapamayapa Member"),
        ("TANOD_CHIEF", "Chief Barangay Tanod"),
        ("BHW_FOCAL", "BHW / Health Focal"),
    ]
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="seats")
    seat_code = models.CharField(max_length=30)
    category = models.CharField(max_length=25, choices=SEAT_CATEGORIES)
    seat_title = models.CharField(max_length=120)
    committee_assignment = models.CharField(max_length=150, blank=True)
    can_approve_clearances = models.BooleanField(default=False)
    can_collect_fees = models.BooleanField(default=False)
    can_manage_blotter = models.BooleanField(default=False)
    sort_order = models.PositiveSmallIntegerField(default=10)

    class Meta:
        unique_together = ("barangay", "seat_code")
        ordering = ["sort_order", "seat_title"]

    def __str__(self):
        return f"{self.seat_title} ({self.barangay.name})"
class TermAssignment(models.Model):
    ASSIGNMENT_STATUS = [
        ("SCHEDULED_INCOMING", "Scheduled Incoming (3-Textbox Transition)"),
        ("ACTIVE", "Active Incumbent"),
        ("COMPLETED_TERM", "Completed Term (Historical Archive)"),
        ("RESIGNED_OR_REMOVED", "Resigned / Vacated Early"),
    ]
    seat = models.ForeignKey(OfficialSeat, on_delete=models.PROTECT, related_name="assignments")
    official_full_name = models.CharField(max_length=150)
    contact_email_or_mobile = models.CharField(max_length=120, blank=True)
    term_label = models.CharField(max_length=60, default="2026–2029 Term")
    term_start = models.DateField(default=timezone.localdate)
    term_end = models.DateField()
    status = models.CharField(max_length=25, choices=ASSIGNMENT_STATUS, default="ACTIVE")
    oath_or_appointment_ref = models.CharField(max_length=120, blank=True)
    facilitated_by = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-term_start", "seat__sort_order"]

    def clean(self):
        if self.term_end and self.term_start and self.term_end < self.term_start:
            raise ValidationError("Term end date cannot be earlier than term start date.")

    def __str__(self):
        return f"{self.official_full_name} — {self.seat.seat_title} ({self.term_label})"


class ActingDesignation(models.Model):
    seat = models.ForeignKey(OfficialSeat, on_delete=models.CASCADE, related_name="acting_designations")
    principal_assignment = models.ForeignKey(TermAssignment, on_delete=models.SET_NULL, null=True, blank=True, related_name="acting_periods")
    acting_official_name = models.CharField(max_length=150)
    designation_order_ref = models.CharField(max_length=120)
    reason = models.CharField(max_length=200, blank=True)
    valid_from = models.DateField()
    valid_until = models.DateField()
    allow_clearance_signing = models.BooleanField(default=True)
    allow_blotter_mediation = models.BooleanField(default=False)
    allow_disbursement_approval = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-valid_from"]

    def clean(self):
        if self.valid_until and self.valid_from and self.valid_until < self.valid_from:
            raise ValidationError("Acting valid_until date cannot be earlier than valid_from date.")

    def __str__(self):
        return f"Acting {self.seat.seat_title}: {self.acting_official_name} ({self.valid_from} to {self.valid_until})"
class OfficialTurnoverRecord(models.Model):
    STATUS_CHOICES = [
        ("DRAFT_INVENTORY", "Preparing BGTT Inventory"),
        ("PENDING_INCOMING_SIGN", "Pending Incoming Official Verification"),
        ("COMPLETED_SIGNED", "Formally Turned Over & Signed"),
    ]
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="turnovers")
    transition_cycle = models.CharField(max_length=80)
    outgoing_punong_barangay = models.CharField(max_length=150)
    incoming_punong_barangay = models.CharField(max_length=150)
    outgoing_treasurer = models.CharField(max_length=150, blank=True)
    incoming_treasurer = models.CharField(max_length=150, blank=True)
    outgoing_secretary = models.CharField(max_length=150, blank=True)
    incoming_secretary = models.CharField(max_length=150, blank=True)
    turnover_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default="DRAFT_INVENTORY")
    handover_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-turnover_date"]

    def __str__(self):
        return f"{self.transition_cycle}: {self.outgoing_punong_barangay} → {self.incoming_punong_barangay}"
from django.conf import settings


class BarangayStaffProfile(models.Model):
    ROLE_CHOICES = [
        ("CAPTAIN", "Punong Barangay (Captain)"),
        ("COUNCILOR", "Sangguniang Barangay Member (Councilor)"),
        ("SK_CHAIRMAN", "SK Chairperson (Youth Chairman)"),
        ("SK_COUNCILOR", "SK Kagawad (SK Youth Councilor)"),
        ("SECRETARY", "Barangay Secretary"),
        ("ASST_SECRETARY", "Assistant Barangay Secretary"),
        ("TREASURER", "Barangay Treasurer"),
        ("ASST_TREASURER", "Assistant Barangay Treasurer"),
        ("HEPE", "Chief Tanod (Hepe)"),
        ("WAREHOUSE_KEEPER", "Warehouse Keeper"),
        ("CUSTODIAN", "Property Custodian"),
        ("SOCIAL_WORKER", "Barangay Social Worker (DSWD / MSWD)"),
    ]
    STATUS_CHOICES = [
        ("PENDING_CAPTAIN", "Pending Captain Approval"),
        ("ACTIVE", "Approved & Active"),
        ("SUSPENDED", "Suspended"),
    ]
    ALL_MODULE_CHOICES = [
        ("OVERVIEW", "Command Overview"),
        ("CITIZENS", "02. Citizens & Reports"),
        ("LEDGER_201", "02B. Master 201 Excel Ledger"),
        ("DOCS_REPO", "02C. Supporting Docs Repository"),
        ("CERTIFICATES", "03. Certificates & Clearances"),
        ("BLOTTER", "04. Derogatory Record Flag"),
        ("TREASURY", "05. Treasury & Collections"),
        ("HEALTH", "06. Health Station"),
        ("WELFARE", "07. Welfare & Associations"),
        ("FLEET", "08. Fleet & Equipment"),
        ("DRRM", "09. BDRRMC & Evac"),
        ("SK", "10. SK & Youth (KK)"),
        ("LEGISLATION", "11. Ordinances & BDP"),
        ("AUDIT", "12. COA & DILG Audit"),
        ("TURNOVER", "13. Governance Turnover"),
        ("POLICY", "14. Policy & Glossary"),
        ("TEMPLATES", "15. Official Forms & Templates"),
    ]
    ROLE_DEFAULT_MODULES = {
        "CAPTAIN": ["OVERVIEW", "CITIZENS", "LEDGER_201", "CERTIFICATES", "BLOTTER", "TREASURY", "HEALTH", "WELFARE", "FLEET", "DRRM", "SK", "LEGISLATION", "AUDIT", "TURNOVER", "POLICY", "TEMPLATES"],
        "COUNCILOR": ["OVERVIEW", "CITIZENS", "LEDGER_201", "WELFARE", "FLEET", "DRRM", "LEGISLATION", "TURNOVER", "POLICY", "TEMPLATES"],
        "SK_CHAIRMAN": ["OVERVIEW", "LEDGER_201", "SK", "LEGISLATION", "TURNOVER", "POLICY", "TEMPLATES"],
        "SK_COUNCILOR": ["OVERVIEW", "SK", "POLICY"],
        "SECRETARY": ["OVERVIEW", "CITIZENS", "LEDGER_201", "CERTIFICATES", "BLOTTER", "LEGISLATION", "AUDIT", "TURNOVER", "POLICY", "TEMPLATES"],
        "ASST_SECRETARY": ["OVERVIEW", "CITIZENS", "LEDGER_201", "CERTIFICATES", "POLICY"],
        "TREASURER": ["OVERVIEW", "CERTIFICATES", "TREASURY", "FLEET", "AUDIT", "TURNOVER", "POLICY", "TEMPLATES"],
        "ASST_TREASURER": ["OVERVIEW", "CERTIFICATES", "TREASURY", "POLICY"],
        "HEPE": ["OVERVIEW", "CITIZENS", "BLOTTER", "FLEET", "DRRM", "POLICY"],
        "WAREHOUSE_KEEPER": ["OVERVIEW", "FLEET", "DRRM", "TURNOVER", "POLICY", "TEMPLATES"],
        "CUSTODIAN": ["OVERVIEW", "FLEET", "AUDIT", "TURNOVER", "POLICY", "TEMPLATES"],
        "SOCIAL_WORKER": ["OVERVIEW", "CITIZENS", "LEDGER_201", "HEALTH", "WELFARE", "DRRM", "POLICY"],
    }

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="staff_profile")
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="staff_profiles")
    citizen = models.OneToOneField("citizens.CitizenProfile", on_delete=models.SET_NULL, null=True, blank=True, related_name="staff_account", help_text="Optional link to verified 201 Master Resident record")
    seat_code = models.CharField(max_length=40, blank=True, help_text="Persistent official seat ID (e.g., SEAT-CAPTAIN, SEAT-KAGAWAD-1, SEAT-SK-CHAIR)")
    official_code = models.CharField(max_length=40, unique=True, null=True, blank=True, help_text="Unique Official Code assigned upon appointment/election; deactivated upon term turnover")
    is_term_active = models.BooleanField(default=True, help_text="False once term ends and post-election turnover completes")
    full_name = models.CharField(max_length=150)
    role = models.CharField(max_length=25, choices=ROLE_CHOICES)
    committee_or_unit = models.CharField(max_length=150, blank=True)
    term_start_date = models.DateField(null=True, blank=True)
    allowed_modules = models.JSONField(default=list, blank=True, help_text="Configurable list of module codes visible in this officer's sidebar")
    approval_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING_CAPTAIN")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_staff_profiles")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_staff_profiles")
    created_at = models.DateTimeField(auto_now_add=True)

    def get_visible_modules(self):
        if self.allowed_modules:
            return list(self.allowed_modules)
        return self.ROLE_DEFAULT_MODULES.get(self.role, ["OVERVIEW", "POLICY"])

    def save(self, *args, **kwargs):
        if not self.allowed_modules:
            self.allowed_modules = list(self.ROLE_DEFAULT_MODULES.get(self.role, ["OVERVIEW", "POLICY"]))
        super().save(*args, **kwargs)
        if not self.official_code:
            b_code = getattr(self.barangay, "code", "BRGY")
            self.official_code = f"OFF-{b_code}-{timezone.now().year}-{self.id:04d}"
            type(self).objects.filter(pk=self.pk).update(official_code=self.official_code)

    def __str__(self):
        return f"{self.full_name} — {self.get_role_display()} ({self.get_approval_status_display()})"


class TrustedLoginDevice(models.Model):
    account_key = models.CharField(max_length=80, db_index=True)
    device_token_hash = models.CharField(max_length=128, db_index=True)
    device_label = models.CharField(max_length=160, blank=True)
    ip_prefix = models.CharField(max_length=45, blank=True)
    verified_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("account_key", "device_token_hash")

    def __str__(self):
        return f"{self.account_key} ({self.ip_prefix})"


class WalkInRecoveryRequest(models.Model):
    STATUS_CHOICES = [
        ("PENDING_CAPTAIN", "Pending Punong Barangay Approval"),
        ("APPROVED", "Approved & Activated"),
        ("REJECTED", "Rejected"),
    ]
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="walkin_recovery_requests")
    citizen = models.ForeignKey("citizens.CitizenProfile", on_delete=models.CASCADE, related_name="recovery_requests")
    requested_username = models.CharField(max_length=60)
    pending_password_hash = models.CharField(max_length=128)
    signed_request_letter_uri = models.TextField(blank=True)
    signed_request_letter_name = models.CharField(max_length=160, blank=True)
    submitted_by_name = models.CharField(max_length=150)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING_CAPTAIN")
    reviewed_by_name = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class OfficialFormTemplate(models.Model):
    CATEGORY_CHOICES = [
        ("COMPLETION_REPORT", "Completion Report"),
        ("ACCEPTANCE_REPORT", "Acceptance Report"),
        ("INSPECTION_REPORT", "Inspection Report"),
        ("ASSET_PROFILE", "Asset Profile"),
        ("WORK_ORDER", "Work Order"),
        ("WALKIN_RECOVERY_LETTER", "Walk-In Account Recovery Request Letter"),
        ("DATA_PRIVACY_POLICY", "Data Privacy Policy & Terms of Use"),
        ("OTHER", "Other Official Form"),
    ]
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="form_templates")
    category = models.CharField(max_length=35, choices=CATEGORY_CHOICES, default="COMPLETION_REPORT")
    title = models.CharField(max_length=160)
    form_code = models.CharField(max_length=40, blank=True)
    description = models.TextField(blank=True)
    body_template = models.TextField(blank=True)
    file_data_uri = models.TextField(blank=True)
    file_name = models.CharField(max_length=160, blank=True)
    has_pending_approval = models.BooleanField(default=False)
    pending_title = models.CharField(max_length=160, blank=True)
    pending_body_template = models.TextField(blank=True)
    pending_submitted_by = models.CharField(max_length=150, blank=True)
    updated_by = models.CharField(max_length=150, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "title"]


class TermArchiveSnapshot(models.Model):
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="term_archives")
    term_label = models.CharField(max_length=120)
    scoped_start_date = models.DateField()
    scoped_end_date = models.DateField()
    outgoing_captain_name = models.CharField(max_length=150)
    incoming_captain_name = models.CharField(max_length=150)
    oath_taking_doc_ref = models.CharField(max_length=150, help_text="COMELEC Proclamation / Oath-Taking Reference No.")
    oath_document = models.FileField(upload_to="turnover_oaths/", null=True, blank=True)
    archived_counts_json = models.JSONField(default=dict)
    roster_snapshot_json = models.JSONField(default=list)
    executed_by = models.CharField(max_length=150)
    executed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.barangay.name} — {self.term_label} ({self.scoped_start_date} to {self.scoped_end_date})"
class BarangayPortalShowcase(models.Model):
    barangay = models.OneToOneField(BarangayTenant, on_delete=models.CASCADE, related_name="portal_showcase")
    hero_tagline = models.CharField(max_length=200, default="Transparent, Fast & Citizen-Centered Digital Barangay Governance")
    background_image_url = models.URLField(blank=True, help_text="Optional custom background photo URL for the Login & Portal header")
    featured_photo_url = models.URLField(blank=True, help_text="Optional Barangay Hall / Accomplishment photo URL")
    accomplishment_1 = models.CharField(max_length=200, default="100% Digital Citizen 201 & QR ID Synchronization")
    accomplishment_2 = models.CharField(max_length=200, default="Zero-Backlog Barangay & Business Clearance Issuance")
    accomplishment_3 = models.CharField(max_length=200, default="COA & DILG Full Disclosure Policy Compliant")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Portal Showcase — {self.barangay.name}"


class BarangayBlastAdvisory(models.Model):
    CATEGORY_CHOICES = [
        ("MEMORANDUM", "Official Barangay Memorandum"),
        ("AYUDA_PAYOUT", "Ayuda / Social Welfare Payout Schedule"),
        ("WEATHER_DRRM", "BDRRMC Weather & Safety Alert"),
        ("HEALTH_MISSION", "Health Center & Medical Mission"),
        ("GENERAL_ADVISORY", "General Community Advisory"),
    ]
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="blast_advisories")
    category = models.CharField(max_length=25, choices=CATEGORY_CHOICES, default="GENERAL_ADVISORY")
    title = models.CharField(max_length=180)
    message = models.TextField()
    target_purok = models.CharField(max_length=60, default="ALL")
    is_urgent = models.BooleanField(default=False)
    posted_by_name = models.CharField(max_length=150, blank=True)
    posted_by_role = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_urgent", "-created_at"]
