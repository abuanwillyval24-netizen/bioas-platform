import os
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from governance.models import Province, CityMunicipality, BarangayTenant, OfficialTurnoverRecord
from citizens.models import CitizenProfile, Household, CitizenCommunityReport
from documents.models import CertificateRequest
from blotter.models import BlotterCase
from treasury.models import OfficialReceipt, AbuloySheet
from health_station.models import HealthMedicineInventory
from social_welfare.models import AssociationGroup, AssociationMember


class Command(BaseCommand):
    help = "Initialize default cloud superuser and Barangay Lagare pilot baseline if empty"

    def handle(self, *args, **options):
        User = get_user_model()
        if not User.objects.filter(is_superuser=True).exists():
            uname = os.environ.get("DJANGO_ADMIN_USER", "admin")
            pwd = os.environ.get("DJANGO_ADMIN_PASS", "BioasLagare2026!")
            User.objects.create_superuser(username=uname, email="Abuanwillyval24@gmail.com", password=pwd)
            self.stdout.write(self.style.SUCCESS(f"Created cloud superuser '{uname}'"))

        if not BarangayTenant.objects.exists():
            prov, _ = Province.objects.get_or_create(code="PROV-NE", defaults={"name": "Nueva Ecija"})
            city, _ = CityMunicipality.objects.get_or_create(code="LGU-CAB", defaults={"province": prov, "name": "Cabanatuan City"})
            brgy = BarangayTenant.objects.create(tenant_code="BRGY-LAGARE", city_municipality=city, name="Barangay Lagare")

            hh1 = Household.objects.create(barangay=brgy, household_code="HH-LAG-001", household_head_name="Juanito S. Reyes", monthly_income_bracket="PHP 15,000 - 25,000")
            c1 = CitizenProfile.objects.create(
                barangay=brgy, household=hh1, citizen_qr_id="CIT-LAG-001", last_name="Reyes", first_name="Juanito", middle_name="Santos",
                sex="MALE", gender_identity="MALE", birth_date=date(1962, 5, 14), civil_status="MARRIED",
                mobile_number="0917-555-0101", is_registered_voter=True, is_senior_citizen=True, status="ACTIVE_RESIDENT",
            )
            c2 = CitizenProfile.objects.create(
                barangay=brgy, citizen_qr_id="CIT-LAG-002", last_name="Villanueva", first_name="Lourdes", middle_name="Mendoza",
                sex="FEMALE", gender_identity="FEMALE", birth_date=date(1984, 9, 22), civil_status="WIDOWED",
                mobile_number="0918-555-0102", is_registered_voter=True, is_solo_parent=True, is_4ps_beneficiary=True, status="ACTIVE_RESIDENT",
            )
            CitizenProfile.objects.create(
                barangay=brgy, citizen_qr_id="CIT-LAG-004", last_name="Magbanua", first_name="Danilo", middle_name="Cruz",
                sex="MALE", gender_identity="MALE", birth_date=date(1995, 2, 18), civil_status="SINGLE",
                mobile_number="0920-555-0104", status="PENDING_APPROVAL",
            )
            CitizenCommunityReport.objects.create(
                barangay=brgy, citizen=c2, tracking_code="RPT-LAG-101", category="INFRASTRUCTURE_LIGHT",
                location_landmark="Purok II Corner Elementary School", description="Streetlight flickering at night",
            )
            CertificateRequest.objects.create(
                barangay=brgy, citizen=c1, control_number="CERT-LAG-2026-001", cert_type="BARANGAY_CLEARANCE",
                purpose="PhilHealth & Senior ID Renewal", is_fee_exempt=False, fee_amount=50.00, official_receipt_number="OR-2026-1001", status="RELEASED",
            )
            CertificateRequest.objects.create(
                barangay=brgy, citizen=c2, control_number="CERT-LAG-2026-003", cert_type="INDIGENCY",
                purpose="DSWD Medical Assistance", is_fee_exempt=True, fee_amount=0.00, status="PENDING_OR",
            )
            OfficialReceipt.objects.create(barangay=brgy, or_number="OR-2026-1001", payor_name="Juanito S. Reyes", collection_type="CLEARANCE_FEE", amount_paid=50.00, issued_by="Marco A. Bautista")
            AbuloySheet.objects.create(barangay=brgy, serial_number="WLF-LAG-2026-01", deceased_name="Late Teodoro M. Ramos", beneficiary_family_name="Maria L. Ramos", total_collected=4250.00, status="COLLECTING")
            HealthMedicineInventory.objects.create(barangay=brgy, item_code="MED-LAG-01", medicine_name="Paracetamol 500mg Tablets", stock_on_hand=450, reorder_level=100, expiration_date=date.today() + timedelta(days=365))
            ag_sr = AssociationGroup.objects.create(barangay=brgy, group_code="ASSOC-SR-01", group_name="Lagare Senior Citizens Association (OSCA)", association_head=c1, description="Senior citizens organization of Barangay Lagare")
            AssociationMember.objects.create(association=ag_sr, citizen=c1, role_in_group="President / Head")
            OfficialTurnoverRecord.objects.create(
                barangay=brgy, transition_cycle="2026-2029 Barangay Governance Transition (BGTT)",
                outgoing_punong_barangay="Hon. Roberto M. Dela Cruz", incoming_punong_barangay="Hon. (Incoming / Elect) — BGTT Verification",
                outgoing_treasurer="Marco A. Bautista", outgoing_secretary="Elena R. Santos", status="DRAFT_INVENTORY",
            )
            self.stdout.write(self.style.SUCCESS("Seeded Barangay Lagare cloud pilot baseline"))
