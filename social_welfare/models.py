from django.db import models
from django.utils import timezone
from governance.models import BarangayTenant
from citizens.models import CitizenProfile


class SocialAidDistribution(models.Model):
    PROGRAM_CATEGORIES = [
        ("SENIOR_SOCIAL_PENSION", "Senior Citizen Social Pension / Cash Gift"),
        ("PWD_ALLOWANCE", "PWD Financial / Medical Assistance"),
        ("SOLO_PARENT_SUPPORT", "Solo Parent Welfare Support"),
        ("FOUR_PS_COMPLIANCE", "4Ps / Pantawid Pamilya Verification"),
        ("CALAMITY_RELIEF_PACK", "Emergency Calamity Relief Goods / Cash Aid"),
        ("BURIAL_AICS_ENDORSEMENT", "AICS / Crisis Intervention Endorsement"),
    ]
    STATUS_CHOICES = [("PENDING_REVIEW", "Pending Social Welfare Verification"),
        ("VERIFIED_ELIGIBLE", "Verified Eligible"),
        ("RELEASED_CLAIMED", "Released & Claimed by Beneficiary"),
        ("UNCLAIMED_RETURNED", "Unclaimed / Returned to Treasury"),
    ]

    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="social_aid_releases")
    citizen = models.ForeignKey(CitizenProfile, on_delete=models.CASCADE, related_name="social_aid_releases")
    program_category = models.CharField(max_length=30, choices=PROGRAM_CATEGORIES)
    distribution_cycle = models.CharField(max_length=80)
    amount_or_pack_value = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    item_description = models.CharField(max_length=150, default="Cash Assistance / Relief Pack")
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default="PENDING_REVIEW")
    released_date = models.DateField(default=timezone.localdate)
    released_by = models.CharField(max_length=120, blank=True)
    remarks = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("barangay", "citizen", "program_category", "distribution_cycle")
        ordering = ["-released_date", "-created_at"]

    def __str__(self):
        return f"{self.citizen.full_name} — {self.get_program_category_display()} ({self.distribution_cycle})"
class AssociationGroup(models.Model):
    barangay = models.ForeignKey(BarangayTenant, on_delete=models.CASCADE, related_name="association_groups")
    group_code = models.CharField(max_length=40, unique=True)
    group_name = models.CharField(max_length=140)
    association_head = models.ForeignKey(
        CitizenProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="headed_associations"
    )
    head_name_override = models.CharField(max_length=150, blank=True)
    description = models.CharField(max_length=220, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["group_name"]

    @property
    def display_head(self):
        return self.association_head.full_name if self.association_head else (self.head_name_override or "Unassigned")

    def __str__(self):
        return f"{self.group_name} (Head: {self.display_head})"


class AssociationMember(models.Model):
    association = models.ForeignKey(AssociationGroup, on_delete=models.CASCADE, related_name="members")
    citizen = models.ForeignKey(CitizenProfile, on_delete=models.CASCADE, related_name="association_memberships")
    role_in_group = models.CharField(max_length=80, default="Member")
    joined_date = models.DateField(default=timezone.localdate)

    class Meta:
        unique_together = ("association", "citizen")

    def __str__(self):
        return f"{self.citizen.full_name} — {self.association.group_name} ({self.role_in_group})"
