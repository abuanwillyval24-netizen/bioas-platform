import json
from pathlib import Path
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template import engines
from django.db.models import Count, Sum
from django.contrib.auth import authenticate, login, logout, get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from .models import Province, CityMunicipality, BarangayTenant, OfficialTurnoverRecord
from .models import Province, CityMunicipality, BarangayTenant, OfficialTurnoverRecord, BarangayPortalShowcase
from citizens.models import CitizenProfile, Household, CitizenCommunityReport
from documents.models import CertificateRequest
from blotter.models import BlotterCase
from treasury.models import OfficialReceipt, AbuloySheet
from health_station.models import HealthConsultationRecord, HealthMedicineInventory
from social_welfare.models import SocialAidDistribution, AssociationGroup
from assets_fleet.models import BarangayVehicle, VehicleTripTicket, CommunityEquipmentLoan
from drrm.models import HazardIncidentAlert, EvacuationCenterStatus
from sk_youth.models import KatipunanKabataanProfile, SKProjectActivity
from planning_legislation.models import LegislativeMeasure, DevelopmentPlanProject
from audit_analytics.models import SystemAuditLog, DILGComplianceReport, COAAuditCompliance


def staff_login(request):
    if request.user.is_authenticated:
        return redirect("/")
    error = ""
    brgy = BarangayTenant.objects.first()
    showcase = BarangayPortalShowcase.objects.filter(barangay=brgy).first() if brgy else None
    if request.method == "POST":
        user = authenticate(request, username=request.POST.get("username", "").strip(), password=request.POST.get("password", ""))
        if user is not None:
            prof = getattr(user, "staff_profile", None)
            if not user.is_superuser and prof and prof.approval_status != "ACTIVE":
                error = f"Account status: {prof.get_approval_status_display()}. Punong Barangay (Captain) approval is required before signing in."
            else:
                login(request, user)
                return redirect(request.GET.get("next") or "/")
        else:
            error = "Invalid staff username or password."
    bg_css = (
        f"background:linear-gradient(120deg,rgba(15,23,42,.82) 0%,rgba(15,23,42,.52) 55%,rgba(15,23,42,.75) 100%),url('{showcase.background_image_url}') center/cover no-repeat fixed;"
        if (showcase and showcase.background_image_url)
        else "background:radial-gradient(circle at 20% 25%,#1d4ed8 0%,#0f172a 55%,#090d16 100%);"
    )
    tpl = """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>BIOAS Official Portal - {{ brgy.name|default:"Barangay Lagare" }}</title>
<style>*{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}body{margin:0;min-height:100vh;""" + bg_css + """color:#fff;display:flex;flex-direction:column;justify-content:space-between}.hero-stage{padding:28px 36px 24px;display:flex;flex-direction:column;justify-content:space-between;min-height:74vh}.top-row{display:flex;justify-content:space-between;align-items:flex-start;gap:24px;flex-wrap:wrap}.brand{display:flex;align-items:center;gap:14px;max-width:620px}.seal{width:64px;height:64px;border-radius:50%;object-fit:cover;border:2px solid rgba(255,255,255,.5);background:#fff;box-shadow:0 6px 18px rgba(0,0,0,.35)}.seal-fallback{width:64px;height:64px;border-radius:50%;background:rgba(255,255,255,.12);border:2px solid #f59e0b;display:flex;align-items:center;justify-content:center;font-weight:900;font-size:1.1rem;color:#fbbf24;letter-spacing:.05em}.gov-tag{font-size:.72rem;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:#fbbf24;margin-bottom:4px}.brand h1{margin:0;font-size:1.75rem;font-weight:800;letter-spacing:-.01em;text-shadow:0 2px 10px rgba(0,0,0,.4)}.brand p{margin:4px 0 0;color:#e2e8f0;font-size:.92rem;text-shadow:0 1px 6px rgba(0,0,0,.4)}.login-card{width:360px;max-width:100%;background:rgba(255,255,255,.97);color:#0f172a;border-radius:14px;padding:24px 26px;box-shadow:0 20px 50px rgba(0,0,0,.45);border-top:4px solid #1e3a8a}.login-card h2{margin:0 0 4px;font-size:1.15rem;color:#0f172a}.login-card .sub{margin:0 0 14px;font-size:.8rem;color:#64748b}label{display:block;font-size:.78rem;font-weight:700;color:#334155;margin:10px 0 4px}input{width:100%;padding:10px 12px;border:1px solid #cbd5e1;border-radius:8px;font-size:.9rem;background:#f8fafc}input:focus{outline:none;border-color:#1e3a8a;background:#fff;box-shadow:0 0 0 3px rgba(30,58,138,.12)}button{width:100%;margin-top:16px;padding:11px;background:#1e3a8a;color:#fff;border:0;border-radius:8px;font-weight:700;font-size:.92rem;cursor:pointer;transition:background .15s}button:hover{background:#1d4ed8}.recovery-row{text-align:center;margin-top:10px;font-size:.75rem;color:#64748b}.recovery-row a{color:#1e3a8a;text-decoration:none;font-weight:600}.recovery-row a:hover{text-decoration:underline}.err{background:#fef2f2;color:#b91c1c;border:1px solid #fecaca;padding:8px 10px;border-radius:8px;font-size:.8rem;margin-bottom:10px;font-weight:600}.links{margin-top:12px;padding-top:12px;border-top:1px solid #e2e8f0;display:flex;justify-content:space-between;font-size:.78rem}.links a{color:#1e3a8a;font-weight:700;text-decoration:none}.links a:hover{text-decoration:underline}.accomplishments{display:flex;gap:10px;flex-wrap:wrap;max-width:860px;margin-top:24px}.acc-pill{background:rgba(15,23,42,.68);backdrop-filter:blur(8px);border:1px solid rgba(255,255,255,.18);padding:8px 14px;border-radius:10px;font-size:.8rem;color:#f8fafc}.acc-pill span{color:#fbbf24;font-weight:800;margin-right:6px}.gov-footer{background:#0b1324;border-top:3px solid #f59e0b;color:#cbd5e1}.tier1-grid{max-width:1240px;margin:0 auto;padding:28px 36px;display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:24px}.tier1-grid h4{margin:0 0 10px;font-size:.84rem;text-transform:uppercase;letter-spacing:.06em;color:#fbbf24}.tier1-grid p,.tier1-grid li{font-size:.78rem;line-height:1.6;color:#cbd5e1;margin:0 0 4px}.tier1-grid ul{list-style:none;padding:0;margin:0}.tier1-grid a{color:#e2e8f0;text-decoration:none}.tier1-grid a:hover{color:#fbbf24;text-decoration:underline}.agency-badge{display:flex;align-items:center;gap:10px;margin-bottom:8px}.agency-badge img,.agency-mini{width:38px;height:38px;border-radius:50%;object-fit:cover;border:1px solid #f59e0b;background:#1e3a8a;color:#fbbf24;display:inline-flex;align-items:center;justify-content:center;font-weight:800;font-size:.75rem}.social-row{display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap}.social-btn{display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:8px;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.2);color:#fff;font-size:.75rem;font-weight:800;text-decoration:none;transition:background .15s,transform .15s}.social-btn:hover{background:#f59e0b;color:#0f172a;transform:translateY(-2px)}.tier2-strip{background:#060a14;border-top:1px solid rgba(255,255,255,.12);padding:22px 36px}.tier2-grid{max-width:1240px;margin:0 auto;display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:24px;align-items:start}.rep-seal{display:flex;gap:12px;align-items:flex-start}.coat{width:46px;height:46px;border-radius:50%;border:2px solid #94a3b8;background:#0f172a;color:#f8fafc;display:flex;align-items:center;justify-content:center;font-weight:900;font-size:.72rem;flex-shrink:0}.tier2-grid h5{margin:0 0 8px;font-size:.8rem;text-transform:uppercase;letter-spacing:.05em;color:#f8fafc}.tier2-grid p,.tier2-grid li{font-size:.75rem;line-height:1.55;color:#94a3b8;margin:0 0 4px}.tier2-grid ul{list-style:none;padding:0;margin:0}.tier2-grid a{color:#94a3b8;text-decoration:none}.tier2-grid a:hover{color:#fff;text-decoration:underline}</style></head><body>
<div class="hero-stage">
  <div class="top-row">
    <div class="brand">
      {% if showcase and showcase.featured_photo_url %}<img src="{{ showcase.featured_photo_url }}" alt="Official Seal" class="seal">{% else %}<div class="seal-fallback">BIOAS</div>{% endif %}
      <div>
        <div class="gov-tag">Republic of the Philippines &bull; Official LGU Command Portal</div>
        <h1>{{ brgy.name|default:"Barangay Lagare" }}</h1>
        <p>{{ showcase.hero_tagline|default:"Transparent, Fast & Citizen-Centered Digital Barangay Governance" }}</p>
      </div>
    </div>
    <div class="login-card">
      <h2>Authorized Sign In</h2>
      <p class="sub">Barangay, SK &amp; LGU Operations Access</p>
      {% if error %}<div class="err">{{ error }}</div>{% endif %}
      <form method="post">{% csrf_token %}
        <label>Username</label><input name="username" placeholder="Enter official username" required autofocus>
        <label>Password</label><input type="password" name="password" placeholder="Enter password" required>
        <button type="submit">Log In</button>
      </form>
      <div class="recovery-row"><a href="/portal-info/#recovery">Forgot Password?</a> &nbsp;&bull;&nbsp; <a href="/portal-info/#recovery">Forgot Username?</a></div>
      <div class="links"><a href="/portal/">Citizen Sign-Up</a><a href="/citizen-home/">Resident Self-Service</a></div>
    </div>
  </div>
  <div class="accomplishments">
    <div class="acc-pill"><span>&#10003;</span>{{ showcase.accomplishment_1|default:"100% Digital Citizen 201 & QR ID Synchronization" }}</div>
    <div class="acc-pill"><span>&#10003;</span>{{ showcase.accomplishment_2|default:"Zero-Backlog Barangay & Business Clearance Issuance" }}</div>
    <div class="acc-pill"><span>&#10003;</span>{{ showcase.accomplishment_3|default:"COA & DILG Full Disclosure Policy Compliant" }}</div>
  </div>
</div>

<footer class="gov-footer">
  <div class="tier1-grid">
    <div>
      <div class="agency-badge">
        {% if showcase and showcase.featured_photo_url %}<img src="{{ showcase.featured_photo_url }}" alt="LGU Seal">{% else %}<span class="agency-mini">LGU</span>{% endif %}
        <strong style="color:#fff;font-size:.92rem;">{{ brgy.name|default:"Barangay Lagare" }}</strong>
      </div>
      <p>{{ brgy.city_municipality.name|default:"Cabanatuan City" }}, {{ brgy.city_municipality.province.name|default:"Nueva Ecija" }}, Philippines</p>
      <p>Email: info@barangaylagare.gov.ph</p>
      <p>Tel: (044) 463-0000</p>
    </div>
    <div>
      <h4>About Us</h4>
      <ul>
        <li><a href="/portal-info/#mandate">&bull; Who We Are / Mandate</a></li>
        <li><a href="/portal-info/#officials">&bull; Key Officials</a></li>
        <li><a href="/portal-info/#charter">&bull; Citizen's Charter</a></li>
        <li><a href="/portal-info/#transparency">&bull; Transparency Seal</a></li>
      </ul>
    </div>
    <div>
      <h4>Help &amp; Legal</h4>
      <ul>
        <li><a href="/portal-info/#guide">&bull; User Guide / How to Register</a></li>
        <li><a href="/portal-info/#faqs">&bull; FAQs</a></li>
        <li><a href="/portal-info/#contact">&bull; Contact Us / Helpdesk</a></li>
        <li><a href="/portal-info/#privacy">&bull; Data Privacy Notice (RA 10173)</a></li>
        <li><a href="/portal-info/#terms">&bull; Terms of Use</a></li>
      </ul>

          </div>
    <div>
      <h4>Connect With Us</h4>
      <div class="social-row">
        <a href="https://facebook.com" target="_blank" rel="noopener" class="social-btn" title="Facebook">FB</a>
        <a href="https://instagram.com" target="_blank" rel="noopener" class="social-btn" title="Instagram">IG</a>
        <a href="https://tiktok.com" target="_blank" rel="noopener" class="social-btn" title="TikTok">TT</a>
        <a href="/portal-info/#mandate" class="social-btn" title="Official Website">WEB</a>
      </div>
      <p>Follow our verified social media pages for official updates.</p>
    </div>
  </div>
  <div class="tier2-strip">
    <div class="tier2-grid">
      <div class="rep-seal">
        <div class="coat">RP</div>
        <div>
          <h5>Republic of the Philippines</h5>
          <p>All content is in the public domain unless otherwise stated.</p>
        </div>
      </div>
      <div>
        <h5>About GOV.PH</h5>
        <p>Learn more about the Philippine government, its structure, how government works, and the people behind it.</p>
        <ul>
          <li><a href="https://www.gov.ph" target="_blank" rel="noopener">&bull; GOV.PH</a></li>
          <li><a href="https://data.gov.ph" target="_blank" rel="noopener">&bull; Open Data Portal</a></li>
          <li><a href="https://officialgazette.gov.ph" target="_blank" rel="noopener">&bull; Official Gazette</a></li>
        </ul>
      </div>
      <div>
        <h5>Government Links</h5>
        <ul>
          <li><a href="https://op-proper.gov.ph" target="_blank" rel="noopener">&bull; Office of the President</a></li>
          <li><a href="https://ovp.gov.ph" target="_blank" rel="noopener">&bull; Office of the Vice President</a></li>
          <li><a href="https://senate.gov.ph" target="_blank" rel="noopener">&bull; Senate of the Philippines</a></li>
          <li><a href="https://congress.gov.ph" target="_blank" rel="noopener">&bull; House of Representatives</a></li>
          <li><a href="https://judiciary.gov.ph" target="_blank" rel="noopener">&bull; Supreme Court</a></li>
        </ul>
      </div>
    </div>
  </div>
</footer>
</body></html>"""
    return HttpResponse(engines["django"].from_string(tpl).render({"error": error, "brgy": brgy, "showcase": showcase}, request))


def staff_logout(request):
    logout(request)
    return redirect("/login/")


@login_required(login_url="/login/")
def command_dashboard(request):
    import uuid
    from datetime import date, timedelta
    from .models import BarangayStaffProfile

    params = request.GET
    tier = params.get("tier", "BARANGAY").upper()
    module = params.get("module", "OVERVIEW").upper()

    province = Province.objects.first()
    city = CityMunicipality.objects.filter(province=province).first() if province else None
    barangays = BarangayTenant.objects.select_related("city_municipality__province").all()
    active_barangay = barangays.filter(tenant_code=params.get("tenant")).first() or barangays.first()

    staff_profile = getattr(request.user, "staff_profile", None)
    all_mod_codes = [code for code, _ in BarangayStaffProfile.ALL_MODULE_CHOICES]
    if request.user.is_superuser or (staff_profile and staff_profile.role == "CAPTAIN"):
        visible_modules = all_mod_codes
    elif staff_profile:
        visible_modules = staff_profile.get_visible_modules()
    else:
        visible_modules = all_mod_codes

    if tier == "BARANGAY" and module not in visible_modules:
        module = "OVERVIEW"

    actor_name = staff_profile.full_name if staff_profile else (request.user.get_full_name() or request.user.username)
    actor_role = staff_profile.get_role_display() if staff_profile else "System Administrator"

    action_notice = ""
    if request.method == "POST" and active_barangay:
        act = request.POST.get("action")
        if act == "APPROVE_CITIZEN":
            cid = request.POST.get("citizen_id")
            target = CitizenProfile.objects.filter(barangay=active_barangay, id=cid).first()
            if target:
                target.status = "ACTIVE_RESIDENT"
                target.save()
                SystemAuditLog.objects.create(
                    barangay=active_barangay,
                    action_type="PORTAL_SYNC_APPROVED",
                    actor_name=actor_name,
                    actor_role=actor_role,
                    reference_code=target.citizen_qr_id,
                    details=f"Approved citizen portal sign-up for {target.full_name} ({target.citizen_qr_id}).",
                )
                action_notice = f"Approved {target.full_name} ({target.citizen_qr_id}) into Master 201 Registry!"
        elif act == "SAVE_CITIZEN_201":
            edit_qr = request.POST.get("edit_qr_id", "").strip().upper()
            cit = CitizenProfile.objects.filter(barangay=active_barangay, citizen_qr_id=edit_qr).first() if edit_qr else None
            is_new = cit is None
            if is_new:
                cit = CitizenProfile(
                    barangay=active_barangay,
                    citizen_qr_id=f"CIT-{uuid.uuid4().hex[:6].upper()}",
                )
            cit.last_name = request.POST.get("last_name", cit.last_name).strip()
            cit.first_name = request.POST.get("first_name", cit.first_name).strip()
            cit.middle_name = request.POST.get("middle_name", "").strip()
            cit.suffix = request.POST.get("suffix", "").strip()
            cit.sex = "FEMALE" if request.POST.get("sex", "MALE").upper().startswith("F") else "MALE"
            if request.POST.get("birth_date"):
                cit.birth_date = request.POST["birth_date"]
            cit.birth_place = request.POST.get("birth_place", "").strip()
            cit.civil_status = request.POST.get("civil_status", "SINGLE")
            cit.address_line = request.POST.get("address_line", "").strip()
            cit.purok = request.POST.get("purok", "Purok I").strip() or "Purok I"
            cit.residency_status = request.POST.get("residency_status", "PERMANENT")
            cit.mobile_number = request.POST.get("mobile_number", "").strip()
            cit.email_address = request.POST.get("email_address", "").strip()
            cit.emergency_contact_name = request.POST.get("emergency_contact_name", "").strip()
            cit.emergency_contact_phone = request.POST.get("emergency_contact_phone", "").strip()
            cit.education_level = request.POST.get("education_level", "")
            cit.school_or_course = request.POST.get("school_or_course", "").strip()
            cit.occupation = request.POST.get("occupation", "").strip()
            cit.employer_or_business = request.POST.get("employer_or_business", "").strip()
            cit.philsys_id = request.POST.get("philsys_id", "").strip()
            cit.precinct_number = request.POST.get("precinct_number", "").strip()
            cit.is_registered_voter = bool(request.POST.get("is_registered_voter"))
            cit.is_senior_citizen = bool(request.POST.get("is_senior_citizen"))
            cit.is_pwd = bool(request.POST.get("is_pwd"))
            cit.is_solo_parent = bool(request.POST.get("is_solo_parent"))
            cit.is_4ps_beneficiary = bool(request.POST.get("is_4ps_beneficiary"))
            cit.is_first_time_jobseeker = bool(request.POST.get("is_first_time_jobseeker"))
            cit.is_ofw = bool(request.POST.get("is_ofw"))
            cit.is_pregnant = bool(request.POST.get("is_pregnant"))
            cit.status = request.POST.get("status", "ACTIVE_RESIDENT")
            if request.POST.get("birth_registered_date"):
                cit.birth_registered_date = request.POST["birth_registered_date"]
            if request.POST.get("date_of_death"):
                cit.date_of_death = request.POST["date_of_death"]
            if request.FILES.get("photo"):
                cit.photo = request.FILES["photo"]
            if request.FILES.get("supporting_document"):
                cit.supporting_document = request.FILES["supporting_document"]

            hh_code = request.POST.get("household_code", "").strip().upper()
            if hh_code:
                hh = Household.objects.filter(barangay=active_barangay, household_code=hh_code).first()
                head_name = request.POST.get("household_head_name", "").strip() or cit.full_name
                if not hh:
                    hh = Household.objects.create(
                        barangay=active_barangay,
                        household_code=hh_code,
                        household_head_name=head_name,
                        purok=cit.purok,
                        address_line=cit.address_line,
                    )
                elif request.POST.get("household_head_name", "").strip():
                    hh.household_head_name = request.POST["household_head_name"].strip()
                    hh.purok = cit.purok
                    hh.save()
                cit.household = hh
                cit.relationship_to_head = request.POST.get("relationship_to_head", "HEAD")

            cit.save()
            SystemAuditLog.objects.create(
                barangay=active_barangay,
                action_type="PORTAL_SYNC_APPROVED",
                actor_name=actor_name,
                actor_role=actor_role,
                reference_code=cit.citizen_qr_id,
                details=f"{'Encoded walk-in' if is_new else 'Updated'} 201 Master Record for {cit.full_name} ({cit.citizen_qr_id}).",
            )
            action_notice = f"{'Encoded new' if is_new else 'Updated'} 201 Master Record: {cit.full_name} ({cit.citizen_qr_id})."

    theme = active_barangay.get_active_theme() if active_barangay else {
        "title": "BIOAS Command Portal", "banner_text": "Philippine Barangay Information & Operations System",
        "primary_color": "#1E3A8A", "secondary_color": "#F59E0B", "is_occasion": False,
    }

    citizens = CitizenProfile.objects.select_related("household").filter(barangay=active_barangay) if active_barangay else CitizenProfile.objects.none()
    households = Household.objects.prefetch_related("members").filter(barangay=active_barangay) if active_barangay else Household.objects.none()
    citizen_reports = CitizenCommunityReport.objects.filter(barangay=active_barangay) if active_barangay else CitizenCommunityReport.objects.none()
    certificates = CertificateRequest.objects.filter(barangay=active_barangay) if active_barangay else CertificateRequest.objects.none()
    pending_or_certs = certificates.filter(status="PENDING_OR")
    blotter_cases = BlotterCase.objects.filter(barangay=active_barangay) if active_barangay else BlotterCase.objects.none()
    receipts = OfficialReceipt.objects.filter(barangay=active_barangay, is_voided=False) if active_barangay else OfficialReceipt.objects.none()
    abuloy_sheets = AbuloySheet.objects.filter(barangay=active_barangay) if active_barangay else AbuloySheet.objects.none()
    total_collections = receipts.aggregate(total=Sum("amount_paid"))["total"] or 0

    health_records = HealthConsultationRecord.objects.filter(barangay=active_barangay) if active_barangay else HealthConsultationRecord.objects.none()
    medicines = HealthMedicineInventory.objects.filter(barangay=active_barangay) if active_barangay else HealthMedicineInventory.objects.none()
    social_aids = SocialAidDistribution.objects.filter(barangay=active_barangay) if active_barangay else SocialAidDistribution.objects.none()
    associations = AssociationGroup.objects.filter(barangay=active_barangay).annotate(member_count=Count("members")) if active_barangay else AssociationGroup.objects.none()
    vehicles = BarangayVehicle.objects.filter(barangay=active_barangay) if active_barangay else BarangayVehicle.objects.none()
    trips = VehicleTripTicket.objects.filter(barangay=active_barangay) if active_barangay else VehicleTripTicket.objects.none()
    equipment_loans = CommunityEquipmentLoan.objects.filter(barangay=active_barangay) if active_barangay else CommunityEquipmentLoan.objects.none()
    hazards = HazardIncidentAlert.objects.filter(barangay=active_barangay) if active_barangay else HazardIncidentAlert.objects.none()
    evac_centers = EvacuationCenterStatus.objects.filter(barangay=active_barangay) if active_barangay else EvacuationCenterStatus.objects.none()
