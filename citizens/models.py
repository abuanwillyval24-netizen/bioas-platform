from datetime import date
from django.db import models
from django.utils import timezone
from governance.models import BarangayTenant, PhysicalStructure


class Household(models.Model):
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="households")
    structure = models.ForeignKey(PhysicalStructure, on_delete=models.SET_NULL, null=True, blank=True, related_name="households")
    household_code = models.CharField(max_length=50, unique=True)
    household_head_name = models.CharField(max_length=150)
    purok = models.CharField(max_length=40, default="Purok I")
    address_line = models.CharField(max_length=220, blank=True)
    monthly_income_bracket = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.household_code} - {self.household_head_name} ({self.purok})"


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
    RELATIONSHIP_CHOICES = [
        ("HEAD", "Head of Family"),
        ("SPOUSE", "Spouse"),
        ("CHILD", "Child (Son / Daughter)"),
        ("PARENT", "Parent"),
        ("SIBLING", "Sibling"),
        ("GRANDCHILD", "Grandchild"),
        ("IN_LAW", "Son / Daughter-in-Law"),
        ("OTHER", "Other Household Member"),
    ]
    RESIDENCY_CHOICES = [
        ("PERMANENT", "Permanent / Homeowner"),
        ("RENTER", "Renter / Boarder"),
        ("SHARER", "Sharer / Living with Relatives"),
        ("TRANSIENT", "Transient / Temporary"),
    ]
    EDUCATION_CHOICES = [
        ("NO_FORMAL", "No Formal Education"),
        ("ELEMENTARY_LEVEL", "Elementary Level"),
        ("ELEMENTARY_GRAD", "Elementary Graduate"),
        ("HIGHSCHOOL_LEVEL", "High School / JHS Level"),
        ("HIGHSCHOOL_GRAD", "High School / SHS Graduate"),
        ("VOCATIONAL", "Vocational / TESDA"),
        ("COLLEGE_LEVEL", "College Level"),
        ("COLLEGE_GRAD", "College Graduate"),
        ("POST_GRAD", "Post-Graduate (Master's / Doctorate)"),
    ]
    STATUS_CHOICES = [
        ("PENDING_APPROVAL", "Pending Portal Approval"),
        ("ACTIVE_RESIDENT", "Active Verified Resident"),
        ("TRANSFERRED_OUT", "Transferred Out"),
        ("DECEASED", "Deceased"),
    ]

    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="citizens")
    household = models.ForeignKey(Household, on_delete=models.SET_NULL, null=True, blank=True, related_name="members")
    relationship_to_head = models.CharField(max_length=20, choices=RELATIONSHIP_CHOICES, default="HEAD")
    citizen_qr_id = models.CharField(max_length=40, unique=True)
    philsys_id = models.CharField(max_length=40, blank=True)

    last_name = models.CharField(max_length=80)
    first_name = models.CharField(max_length=80)
    middle_name = models.CharField(max_length=80, blank=True)
    suffix = models.CharField(max_length=20, blank=True)
    alias_nickname = models.CharField(max_length=80, blank=True)
    sex = models.CharField(max_length=10, choices=SEX_CHOICES)
    gender_identity = models.CharField(max_length=25, choices=GENDER_CHOICES, default="PREFER_NOT_TO_SAY")
    birth_date = models.DateField()
    birth_place = models.CharField(max_length=140, blank=True)
    citizenship = models.CharField(max_length=50, default="Filipino")
    religion = models.CharField(max_length=80, blank=True)
    blood_type = models.CharField(max_length=10, blank=True)
    civil_status = models.CharField(max_length=20, choices=CIVIL_STATUS_CHOICES, default="SINGLE")

    house_lot_no = models.CharField(max_length=80, blank=True)
    street_name = models.CharField(max_length=140, blank=True)
    address_line = models.CharField(max_length=220, blank=True)
    purok = models.CharField(max_length=40, default="Purok I")
    residency_status = models.CharField(max_length=20, choices=RESIDENCY_CHOICES, default="PERMANENT")
    years_in_barangay = models.PositiveIntegerField(default=1)

    mobile_number = models.CharField(max_length=30, blank=True)
    email_address = models.EmailField(blank=True)
    emergency_contact_name = models.CharField(max_length=120, blank=True)
    emergency_contact_phone = models.CharField(max_length=30, blank=True)
    emergency_contact_relationship = models.CharField(max_length=60, blank=True)

    father_name = models.CharField(max_length=140, blank=True)
    mother_maiden_name = models.CharField(max_length=140, blank=True)
    spouse_name = models.CharField(max_length=140, blank=True)

    education_level = models.CharField(max_length=25, choices=EDUCATION_CHOICES, blank=True)
    currently_attending_school = models.BooleanField(default=False)
    school_or_course = models.CharField(max_length=140, blank=True)
    grade_year_level = models.CharField(max_length=60, blank=True)
    SOCIOECONOMIC_TIER_CHOICES = [
        ("SUBSISTENCE", "Subsistence / Priority Support"),
        ("LOW_INCOME", "Low-Income / Vulnerable"),
        ("LOWER_MIDDLE", "Lower-Middle / Marginal"),
        ("SELF_SUSTAINING", "Self-Sustaining"),
    ]
    LIVELIHOOD_SOURCE_CHOICES = [
        ("CITIZEN_DECLARATION", "Citizen Declaration"),
        ("CENSUS_SNAPSHOT", "Census Snapshot"),
        ("FIELD_VALIDATION", "Field Validation"),
    ]
    LIVELIHOOD_VERIFY_CHOICES = [
        ("UNVERIFIED", "Unverified"),
        ("VERIFIED", "Verified"),
        ("UNDER_REVIEW", "Under Review"),
    ]
    employment_status = models.CharField(max_length=60, blank=True)
    occupation = models.CharField(max_length=120, blank=True)
    secondary_livelihood = models.CharField(max_length=140, blank=True)
    employer_or_business = models.CharField(max_length=140, blank=True)
    employer_address = models.CharField(max_length=200, blank=True)
    monthly_income = models.CharField(max_length=60, blank=True)
    socioeconomic_tier = models.CharField(max_length=25, choices=SOCIOECONOMIC_TIER_CHOICES, blank=True)
    livelihood_source = models.CharField(max_length=25, choices=LIVELIHOOD_SOURCE_CHOICES, default="CITIZEN_DECLARATION", blank=True)
    livelihood_verification_status = models.CharField(max_length=20, choices=LIVELIHOOD_VERIFY_CHOICES, default="UNVERIFIED", blank=True)
    livelihood_effective_date = models.DateField(null=True, blank=True)

    is_registered_voter = models.BooleanField(default=False)
    precinct_number = models.CharField(max_length=30, blank=True)
    philhealth_number = models.CharField(max_length=40, blank=True)
    sss_gsis_number = models.CharField(max_length=40, blank=True)
    tin_number = models.CharField(max_length=40, blank=True)
    pagibig_number = models.CharField(max_length=40, blank=True)

    is_senior_citizen = models.BooleanField(default=False)
    osca_id_number = models.CharField(max_length=40, blank=True)
    is_pwd = models.BooleanField(default=False)
    pwd_id_number = models.CharField(max_length=40, blank=True)
    pwd_disability_type = models.CharField(max_length=80, blank=True)
    is_solo_parent = models.BooleanField(default=False)
    solo_parent_id_number = models.CharField(max_length=40, blank=True)
    is_4ps_beneficiary = models.BooleanField(default=False)
    four_ps_household_id = models.CharField(max_length=40, blank=True)
    is_first_time_jobseeker = models.BooleanField(default=False)
    is_ofw = models.BooleanField(default=False)
    ofw_country = models.CharField(max_length=80, blank=True)
    is_osy_osc = models.BooleanField(default=False)
    is_indigenous_people = models.BooleanField(default=False)
    ip_group_tribe = models.CharField(max_length=80, blank=True)

    is_pregnant = models.BooleanField(default=False)
    birth_registered_date = models.DateField(null=True, blank=True)
    date_of_death = models.DateField(null=True, blank=True)

    photo = models.FileField(upload_to="citizen_201/photos/", null=True, blank=True)
    photo_data_uri = models.TextField(blank=True)
    supporting_document = models.FileField(upload_to="citizen_201/docs/", null=True, blank=True)
    supporting_doc_data_uri = models.TextField(blank=True)
    data_privacy_consent = models.BooleanField(default=True)
    electronic_signature = models.CharField(max_length=140, blank=True)
    encoded_by = models.CharField(max_length=120, blank=True)
    validated_by = models.CharField(max_length=120, blank=True)

    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default="ACTIVE_RESIDENT")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def full_name(self):
        parts = [self.first_name, self.middle_name, self.last_name, self.suffix]
        return " ".join(p for p in parts if p)

    @property
    def age(self):
        if not self.birth_date:
            return 0
        ref = self.date_of_death if (self.status == "DECEASED" and self.date_of_death) else date.today()
        return max(0, ref.year - self.birth_date.year - ((ref.month, ref.day) < (self.birth_date.month, self.birth_date.day)))

    @property
    def profile_completion_pct(self):
        checks = [
            bool(self.last_name and self.first_name),
            bool(self.birth_date),
            bool(self.birth_place),
            bool(self.address_line),
            bool(self.purok),
            bool(self.mobile_number),
            bool(self.emergency_contact_name),
            bool(self.education_level),
            bool(self.occupation),
            bool(self.household_id),
            bool(self.photo),
            bool(self.supporting_document),
        ]
        return int(round((sum(checks) / len(checks)) * 100))

    def save(self, *args, **kwargs):
        if self.status == "DECEASED" and not self.date_of_death:
            self.date_of_death = date.today()
        if self.birth_date and self.age >= 60:
            self.is_senior_citizen = True
        super().save(*args, **kwargs)

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
        return f"Update Request - {self.citizen.full_name} ({self.get_status_display()})"

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
        return f"{self.tracking_code} - {self.citizen.full_name} ({self.get_status_display()})"
class CitizenSupportingDocument(models.Model):
    SOURCE_CHOICES = [
        ("PORTAL_SIGNUP", "Online Citizen Portal Sign-Up / Update"),
        ("WALKIN_DESK", "Barangay Hall Walk-In / Desk Encoding"),
        ("CERTIFICATE_REQ", "Certificate / Clearance Supporting Attachment"),
        ("STAFF_REPOSITORY", "Direct Staff Repository Upload"),
    ]
    citizen = models.ForeignKey(CitizenProfile, on_delete=models.CASCADE, related_name="repository_docs")
    document_title = models.CharField(max_length=160)
    source_channel = models.CharField(max_length=25, choices=SOURCE_CHOICES, default="WALKIN_DESK")
    file = models.FileField(upload_to="citizens/repository_docs/")
    file_data_uri = models.TextField(blank=True)

    uploaded_by = models.CharField(max_length=120, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.citizen.citizen_qr_id} — {self.document_title}"


from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=CitizenProfile)
def archive_citizen_supporting_doc(sender, instance, **kwargs):
    if instance.supporting_document and instance.supporting_document.name:
        if not CitizenSupportingDocument.objects.filter(citizen=instance, file=instance.supporting_document.name).exists():
            source = "PORTAL_SIGNUP" if instance.status == "PENDING_APPROVAL" else "WALKIN_DESK"
            CitizenSupportingDocument.objects.create(
                citizen=instance,
                document_title=f"201 Supporting Document ({instance.full_name})",
                source_channel=source,
                file=instance.supporting_document.name,
                uploaded_by="Citizen Portal" if source == "PORTAL_SIGNUP" else "Barangay Staff",
            )
