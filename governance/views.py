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
    if params.get("download_201_template") == "1":
        import csv, io
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["citizen_qr_id", "household_code", "household_head_name", "relationship_to_head", "last_name", "first_name", "middle_name", "suffix", "sex", "birth_date", "birth_place", "civil_status", "purok", "address_line", "residency_status", "mobile_number", "email_address", "emergency_contact_name", "emergency_contact_phone", "education_level", "school_or_course", "occupation", "employer_or_business", "philsys_id", "precinct_number", "is_registered_voter", "is_senior_citizen", "is_pwd", "is_solo_parent", "is_4ps_beneficiary", "is_first_time_jobseeker", "is_ofw", "is_pregnant", "status", "birth_registered_date", "date_of_death"])
        w.writerow(["", "HH-LAG-001", "Juan Dela Cruz", "HEAD", "Dela Cruz", "Juan", "Santos", "", "MALE", "1985-05-14", "Cabanatuan City", "MARRIED", "Purok I", "House 1, Purok I", "PERMANENT", "09171234567", "juan@lagare.gov.ph", "Maria Dela Cruz", "09181234567", "COLLEGE", "BS Agriculture", "Farmer", "Self-Employed", "4401-0001-1001-2001", "0141A", "Yes", "No", "No", "No", "No", "No", "No", "No", "ACTIVE_RESIDENT", "", ""])
        resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="BIOAS_Universal_201_Master_Template.csv"'
        return resp
    tier = params.get("tier", "BARANGAY").upper()
    module = params.get("module", "OVERVIEW").upper()

    province = Province.objects.first()
    city = CityMunicipality.objects.filter(province=province).first() if province else None
    barangays = BarangayTenant.objects.select_related("city_municipality__province").all()
    active_barangay = barangays.filter(tenant_code=params.get("tenant")).first() or barangays.first()

    staff_profile = getattr(request.user, "staff_profile", None)
    all_mod_codes = [code for code, _ in BarangayStaffProfile.ALL_MODULE_CHOICES]
    if request.user.is_superuser or (staff_profile and staff_profile.role == "CAPTAIN"):
        visible_modules = list(all_mod_codes)
    elif staff_profile:
        visible_modules = list(staff_profile.get_visible_modules())
    else:
        visible_modules = list(all_mod_codes)
    if "CITIZENS" in visible_modules or "LEDGER_201" in visible_modules or request.user.is_superuser:
        for extra_sub in ("CITIZENS_INTAKE", "HOUSEHOLDS", "SHARED_GALLERY", "DOCS_REPO", "CITIZEN_REPORTS"):
            if extra_sub not in visible_modules:
                visible_modules.append(extra_sub)

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
                if target.email_address:
                    try:
                        from django.core.mail import send_mail
                        from django.conf import settings as dj_settings
                        send_mail(
                            subject=f"[{active_barangay.name}] Account Approved ? Complete Your 201 Profile",
                            message=(
                                f"Good day {target.full_name},\n\n"
                                f"Your Barangay registration ({target.citizen_qr_id}) has been verified and approved into the Official 201 Master Registry.\n"
                                f"Next Step: Please sign in at /citizen-home/ using your Citizen ID ({target.citizen_qr_id}) and complete your profile.\n\n"
                                f"? {active_barangay.name} Office of the Barangay Secretary"
                            ),
                            from_email=getattr(dj_settings, "DEFAULT_FROM_EMAIL", None),
                            recipient_list=[target.email_address],
                            fail_silently=True,
                        )
                    except Exception:
                        pass
                action_notice = f"Approved {target.full_name} ({target.citizen_qr_id}) into 201 Master & 02E Gallery! Sent 'Complete your profile' notification."
        elif act == "REJECT_CITIZEN":
            target = CitizenProfile.objects.filter(id=request.POST.get("citizen_id"), barangay=active_barangay).first()
            reason = request.POST.get("reject_reason", "").strip() or "Incomplete or unverified supporting documents"
            if target:
                qr_ref = target.citizen_qr_id
                full_nm = target.full_name
                target.delete()
                SystemAuditLog.objects.create(
                    barangay=active_barangay,
                    action_type="PORTAL_SYNC_APPROVED",
                    actor_name=actor_name,
                    actor_role=actor_role,
                    reference_code=qr_ref,
                    details=f"Rejected & returned 201 application for {full_nm} ({qr_ref}). Reason: {reason}",
                )
                action_notice = f"Rejected 201 submission for {full_nm} ({qr_ref}). Reason: {reason}"
        elif act == "VERIFY_LIVELIHOOD_TIER":
            target = CitizenProfile.objects.filter(id=request.POST.get("citizen_id"), barangay=active_barangay).first()
            new_tier = request.POST.get("socioeconomic_tier", "").strip()
            new_vstat = request.POST.get("livelihood_verification_status", "VERIFIED").strip()
            v_reason = request.POST.get("verify_reason", "").strip() or "Field & cross-module livelihood verification"
            if target:
                if new_tier in ("SUBSISTENCE", "LOW_INCOME", "LOWER_MIDDLE", "SELF_SUSTAINING"):
                    target.socioeconomic_tier = new_tier
                if new_vstat in ("UNVERIFIED", "VERIFIED", "UNDER_REVIEW"):
                    target.livelihood_verification_status = new_vstat
                target.livelihood_source = "FIELD_VALIDATION"
                target.livelihood_effective_date = date.today()
                target.save(update_fields=["socioeconomic_tier", "livelihood_verification_status", "livelihood_source", "livelihood_effective_date"])
                SystemAuditLog.objects.create(
                    barangay=active_barangay,
                    action_type="PORTAL_SYNC_APPROVED",
                    actor_name=actor_name,
                    actor_role=actor_role,
                    reference_code=target.citizen_qr_id,
                    details=f"Field-validated Livelihood & Socioeconomic Tier for {target.full_name} ({target.citizen_qr_id}) -> {target.get_socioeconomic_tier_display() or 'Unclassified'} [{target.get_livelihood_verification_status_display()}]. Note: {v_reason}",
                )
                action_notice = f"Updated Livelihood & Socioeconomic record for {target.full_name} ({target.get_socioeconomic_tier_display() or 'Unclassified'} — {target.get_livelihood_verification_status_display()})."
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
        elif act == "BULK_IMPORT_201" and request.FILES.get("excel_file"):
            import csv, io, zipfile, xml.etree.ElementTree as ET
            up_file = request.FILES["excel_file"]
            fname_low = up_file.name.lower()
            raw_bytes = up_file.read()
            sheets_collected = []
            if fname_low.endswith(".csv"):
                text = raw_bytes.decode("utf-8-sig", errors="replace")
                lines_nonempty = [ln for ln in text.splitlines() if ln.strip()]
                first_line = lines_nonempty.__getitem__(0) if lines_nonempty else ""
                delim = ";" if first_line.count(";") > first_line.count(",") else ("\t" if first_line.count("\t") > first_line.count(",") else ",")
                sheets_collected.append(("Sheet1", list(csv.reader(io.StringIO(text), delimiter=delim))))
            elif fname_low.endswith(".xlsx"):
                with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
                    shared = []
                    if "xl/sharedStrings.xml" in zf.namelist():
                        sroot = ET.fromstring(zf.read("xl/sharedStrings.xml"))
                        for si in sroot.findall(".//{*}si"):
                            shared.append("".join(t.text or "" for t in si.findall(".//{*}t")))
                    sheet_names = []
                    if "xl/workbook.xml" in zf.namelist():
                        wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
                        for sh_el in wb_root.findall(".//{*}sheet"):
                            sheet_names.append(sh_el.attrib.get("name", ""))
                    sheet_files = sorted(
                        [n for n in zf.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")],
                        key=lambda x: int("".join(ch for ch in x if ch.isdigit()) or 0)
                    )
                    for idx_sh, sh_path in enumerate(sheet_files):
                        tab_name = sheet_names.__getitem__(idx_sh) if idx_sh < len(sheet_names) else f"Sheet{idx_sh+1}"
                        wroot = ET.fromstring(zf.read(sh_path))
                        sh_rows = []
                        for r_el in wroot.findall(".//{*}row"):
                            row_vals = []
                            for c_el in r_el.findall("{*}c"):
                                ref = c_el.attrib.get("r", "")
                                col_letters = "".join(ch for ch in ref if ch.isalpha())
                                col_idx = 0
                                for ch in col_letters:
                                    col_idx = col_idx * 26 + (ord(ch.upper()) - 64)
                                while len(row_vals) < max(col_idx - 1, 0):
                                    row_vals.append("")
                                c_type = c_el.attrib.get("t", "")
                                v_el = c_el.find("{*}v")
                                is_el = c_el.find(".//{*}t")
                                val = ""
                                if c_type == "s" and v_el is not None and v_el.text is not None:
                                    idx_s = int(v_el.text)
                                    val = shared.__getitem__(idx_s) if idx_s < len(shared) else ""
                                elif is_el is not None and is_el.text is not None:
                                    val = is_el.text
                                elif v_el is not None and v_el.text is not None:
                                    val = v_el.text
                                row_vals.append(str(val).strip())
                            if any(row_vals):
                                sh_rows.append(row_vals)
                        if len(sh_rows) >= 2:
                            sheets_collected.append((tab_name, sh_rows))

            def _yn(v):
                return str(v or "").strip().lower() in ("yes", "true", "1", "y", "voter")

            def _parse_dt(v):
                from datetime import datetime
                raw_s = str(v or "").strip()
                if not raw_s:
                    return ""
                s = raw_s.split(" ").__getitem__(0)
                if s.replace(".", "", 1).isdigit():
                    return (date(1899, 12, 30) + timedelta(days=int(float(s)))).isoformat()
                for cand in (s, raw_s):
                    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%m-%d-%Y", "%d-%m-%Y", "%d-%b-%Y", "%d-%b-%y", "%b %d, %Y", "%B %d, %Y", "%m/%d/%y"):
                        try:
                            return datetime.strptime(cand, fmt).date().isoformat()
                        except ValueError:
                            continue
                return ""

            imported_count = 0
            sheets_used = 0
            diag_note = ""
            for tab_name, rows_data in sheets_collected:
                hdr_idx = None
                headers = []
                for scan_i in range(min(5, len(rows_data))):
                    cand_h = [str(h or "").strip().lower().replace(" ", "_") for h in rows_data.__getitem__(scan_i)]
                    if "last_name" in cand_h and "first_name" in cand_h:
                        hdr_idx = scan_i
                        headers = cand_h
                        break
                if hdr_idx is None:
                    if not diag_note and rows_data:
                        diag_note = f"Row 1 columns seen: {', '.join(rows_data.__getitem__(0)[:6])}"
                    continue
                sheets_used += 1
                default_purok = tab_name.strip() if any(k in tab_name.lower() for k in ("purok", "zone", "sitio")) else "Purok I"
                for r in rows_data.__getitem__(slice(hdr_idx + 1, None)):
                    rec = {headers.__getitem__(i): (r.__getitem__(i) if i < len(r) else "") for i in range(len(headers))}
                    if len(r) >= 11 and rec.get("birth_date", "").strip().lower() in ("male", "female") and len(_parse_dt(r.__getitem__(10))) == 10:
                        g = lambda idx: (r.__getitem__(idx).strip() if idx < len(r) else "")
                        qr_val = g(1).upper() or g(0).upper()
                        hh_code = g(2).upper()
                        rel_raw = g(3).upper()
                        rel_val = "HEAD" if "HEAD" in rel_raw else ("SPOUSE" if "SPOUSE" in rel_raw else ("CHILD" if "CHILD" in rel_raw else ("PARENT" if "PARENT" in rel_raw else ("SIBLING" if "SIBLING" in rel_raw else "RELATIVE"))))
                        purok_val = g(4) or default_purok
                        lname = g(5)
                        fname_c = g(6)
                        mname_c = g(7)
                        suf_c = g(8)
                        sex_val = "FEMALE" if g(9).upper().startswith("F") else "MALE"
                        bdate = _parse_dt(g(10))
                        cstat_val = g(13).upper() or "SINGLE"
                        occ_val = g(14)
                        is_voter = _yn(g(16))
                        prec_val = g(17)
                        is_sr = _yn(g(18))
                        is_pwd = _yn(g(19))
                        is_solo = _yn(g(21))
                        vital = g(22).lower()
                        is_4ps = _yn(g(24))
                        is_ofw = _yn(g(25))
                        is_preg = _yn(g(26))
                        is_ftj = _yn(g(27))
                        mob_val = g(28)
                        em_val = g(29)
                        br_dt = date.today().isoformat() if "birth" in vital else ""
                        dd_dt = date.today().isoformat() if "death" in vital or "deceased" in vital else ""
                        head_nm = f"{fname_c} {lname}"
                    else:
                        lname = rec.get("last_name", "").strip()
                        fname_c = rec.get("first_name", "").strip()
                        mname_c = rec.get("middle_name", "").strip()
                        suf_c = rec.get("suffix", "").strip()
                        sex_val = "FEMALE" if rec.get("sex", "MALE").strip().upper().startswith("F") else "MALE"
                        bdate = _parse_dt(rec.get("birth_date", ""))
                        cstat_val = rec.get("civil_status", "SINGLE").strip().upper() or "SINGLE"
                        purok_val = rec.get("purok", "").strip() or default_purok
                        occ_val = rec.get("occupation", "").strip()
                        is_voter = _yn(rec.get("is_registered_voter"))
                        prec_val = rec.get("precinct_number", "").strip()
                        is_sr = _yn(rec.get("is_senior_citizen"))
                        is_pwd = _yn(rec.get("is_pwd"))
                        is_solo = _yn(rec.get("is_solo_parent"))
                        is_4ps = _yn(rec.get("is_4ps_beneficiary"))
                        is_ofw = _yn(rec.get("is_ofw"))
                        is_preg = _yn(rec.get("is_pregnant"))
                        is_ftj = _yn(rec.get("is_first_time_jobseeker"))
                        mob_val = rec.get("mobile_number", "").strip()
                        em_val = rec.get("email_address", "").strip()
                        qr_val = rec.get("citizen_qr_id", "").strip().upper()
                        hh_code = rec.get("household_code", "").strip().upper()
                        head_nm = rec.get("household_head_name", "").strip() or f"{fname_c} {lname}"
                        rel_raw = rec.get("relationship_to_head", "HEAD").strip().upper()
                        rel_val = rel_raw if rel_raw in ("HEAD", "SPOUSE", "CHILD", "PARENT", "SIBLING", "RELATIVE", "BOARDER") else "HEAD"
                        br_dt = _parse_dt(rec.get("birth_registered_date", ""))
                        dd_dt = _parse_dt(rec.get("date_of_death", ""))

                    if not lname or not fname_c or len(bdate) != 10:
                        continue
                    cit = CitizenProfile.objects.filter(barangay=active_barangay, citizen_qr_id=qr_val).first() if qr_val else None
                    if not cit:
                        cit = CitizenProfile(
                            barangay=active_barangay,
                            citizen_qr_id=qr_val or f"CIT-{uuid.uuid4().hex[:6].upper()}",
                        )
                    cit.last_name = lname.__getitem__(slice(0, 80))
                    cit.first_name = fname_c.__getitem__(slice(0, 80))
                    cit.middle_name = mname_c.__getitem__(slice(0, 80))
                    cit.suffix = suf_c.__getitem__(slice(0, 15))
                    cit.sex = sex_val.__getitem__(slice(0, 10))
                    cit.birth_date = date.fromisoformat(bdate)
                    cit.birth_place = rec.get("birth_place", "").strip().__getitem__(slice(0, 120))
                    cit.civil_status = (cstat_val if cstat_val in ("SINGLE", "MARRIED", "WIDOWED", "SEPARATED", "LIVE_IN") else "SINGLE").__getitem__(slice(0, 20))
                    cit.purok = purok_val.__getitem__(slice(0, 60))
                    cit.address_line = rec.get("address_line", "").strip().__getitem__(slice(0, 200))
                    res_raw = rec.get("residency_status", "PERMANENT").strip().upper()
                    cit.residency_status = (res_raw if res_raw in ("PERMANENT", "TEMPORARY", "RENTER", "INFORMAL") else "PERMANENT").__getitem__(slice(0, 20))
                    cit.mobile_number = mob_val.__getitem__(slice(0, 20))
                    cit.email_address = em_val.__getitem__(slice(0, 120))
                    cit.emergency_contact_name = rec.get("emergency_contact_name", "").strip().__getitem__(slice(0, 120))
                    cit.emergency_contact_phone = rec.get("emergency_contact_phone", "").strip().__getitem__(slice(0, 20))
                    edu_raw = rec.get("education_level", "").strip().upper()
                    cit.education_level = (edu_raw if edu_raw in ("NONE", "ELEMENTARY", "HIGH_SCHOOL", "SENIOR_HIGH", "VOCATIONAL", "COLLEGE", "POST_GRAD") else "").__getitem__(slice(0, 20))
                    cit.school_or_course = rec.get("school_or_course", "").strip().__getitem__(slice(0, 120))
                    cit.occupation = occ_val.__getitem__(slice(0, 100))
                    cit.employer_or_business = rec.get("employer_or_business", "").strip().__getitem__(slice(0, 120))
                    cit.philsys_id = rec.get("philsys_id", "").strip().__getitem__(slice(0, 30))
                    cit.precinct_number = prec_val.__getitem__(slice(0, 20))
                    cit.is_registered_voter = is_voter
                    cit.is_senior_citizen = is_sr
                    cit.is_pwd = is_pwd
                    cit.is_solo_parent = is_solo
                    cit.is_4ps_beneficiary = is_4ps
                    cit.is_first_time_jobseeker = is_ftj
                    cit.is_ofw = is_ofw
                    cit.is_pregnant = is_preg
                    cit.status = "PENDING_APPROVAL"
                    if len(br_dt) == 10:
                        cit.birth_registered_date = date.fromisoformat(br_dt)
                    if len(dd_dt) == 10:
                        cit.date_of_death = date.fromisoformat(dd_dt)
                        cit.date_of_death = dd_dt
                    if hh_code:
                        hh = Household.objects.filter(barangay=active_barangay, household_code=hh_code).first()
                        if not hh:
                            hh = Household.objects.create(
                                barangay=active_barangay,
                                household_code=hh_code,
                                household_head_name=head_nm,
                                purok=cit.purok,
                                address_line=cit.address_line,
                            )
                        cit.household = hh
                        cit.relationship_to_head = rel_val
                    cit.save()
                    imported_count += 1

            if imported_count > 0:
                SystemAuditLog.objects.create(
                    barangay=active_barangay,
                    action_type="PORTAL_SYNC_APPROVED",
                    actor_name=actor_name,
                    actor_role=actor_role,
                    reference_code=f"STAGE-{imported_count}",
                    details=f"Staged {imported_count} uploaded citizen records across {sheets_used} sheet(s) from '{up_file.name}' into Pending Approval Queue (201 Master File kept strictly intact pending verification).",
                )
                action_notice = f"Staged {imported_count} citizen record(s) across {sheets_used} sheet(s) from '{up_file.name}' into the Pending Citizen Approvals Queue below for individual or mass verification."
            else:
                action_notice = f"0 rows staged from '{up_file.name}'. {diag_note or 'Ensure last_name, first_name, and birth_date (YYYY-MM-DD or MM/DD/YYYY) are filled in.'}"
        elif act == "MASS_APPROVE_201":
            selected_ids = request.POST.getlist("pending_ids")
            qs_pend = CitizenProfile.objects.filter(barangay=active_barangay, status="PENDING_APPROVAL")
            if selected_ids:
                qs_pend = qs_pend.filter(id__in=selected_ids)
            approved_total = qs_pend.update(status="ACTIVE_RESIDENT")
            if approved_total > 0:
                SystemAuditLog.objects.create(
                    barangay=active_barangay,
                    action_type="PORTAL_SYNC_APPROVED",
                    actor_name=actor_name,
                    actor_role=actor_role,
                    reference_code=f"MASS-201-{approved_total}",
                    details=f"Verified and mass-approved {approved_total} pending citizen record(s) into the official 201 Master Registry.",
                )
                action_notice = f"Verified & activated {approved_total} citizen record(s) into the Official 201 Master Registry!"
            else:
                action_notice = "No pending citizen records were selected for approval."
        elif act == "BATCH_ZIP_DOCS" and (request.FILES.getlist("photo_files") or request.FILES.getlist("doc_files")):
            import os, zipfile
            from django.core.files.base import ContentFile
            from citizens.views import save_standardized_citizen_files
            matched_docs = 0
            matched_photos = 0
            skipped_files = []

            def _extract_items(file_list):
                out = []
                for f_item in file_list:
                    if f_item.name.lower().endswith(".zip"):
                        try:
                            with zipfile.ZipFile(f_item) as zf:
                                for info in zf.infolist():
                                    if info.is_dir():
                                        continue
                                    bname = os.path.basename(info.filename).strip()
                                    if not bname or bname.startswith(".") or "__MACOSX" in info.filename:
                                        continue
                                    out.append((bname, zf.read(info.filename)))
                        except zipfile.BadZipFile:
                            skipped_files.append(f_item.name)
                    else:
                        out.append((os.path.basename(f_item.name).strip(), f_item.read()))
                return out

            from citizens.views import _geo_code
            city_o = getattr(active_barangay, "city_municipality", None)
            prov_o = getattr(city_o, "province", None)
            nat_prefix = f"{_geo_code(getattr(prov_o, 'name', ''), 'NE')}-{_geo_code(getattr(city_o, 'name', ''), 'CAB')}-{_geo_code(getattr(active_barangay, 'name', ''), 'LAG')}-{date.today().year}-"

            def _resolve_national_citizen(qr_cand):
                cit = CitizenProfile.objects.filter(barangay=active_barangay, citizen_qr_id__iexact=qr_cand).first()
                tail_digits = "".join(ch for ch in qr_cand.split("-").__getitem__(-1) if ch.isdigit())
                if not cit and tail_digits:
                    seq_int = int(tail_digits)
                    for cand_c in CitizenProfile.objects.filter(barangay=active_barangay):
                        c_tail = "".join(ch for ch in cand_c.citizen_qr_id.split("-").__getitem__(-1) if ch.isdigit())
                        if c_tail and int(c_tail) == seq_int:
                            cit = cand_c
                            break
                if cit and tail_digits and not cit.citizen_qr_id.upper().startswith(nat_prefix):
                    target_nat_id = f"{nat_prefix}{int(tail_digits):05d}"
                    if not CitizenProfile.objects.filter(barangay=active_barangay, citizen_qr_id=target_nat_id).exclude(id=cit.id).exists():
                        cit.citizen_qr_id = target_nat_id
                        cit.save(update_fields=["citizen_qr_id"])
                return cit

            for base_fn, file_bytes in _extract_items(request.FILES.getlist("photo_files")):
                if not base_fn or not file_bytes:
                    continue
                qr_candidate = os.path.splitext(base_fn).__getitem__(0).split("_").__getitem__(0).strip().upper()
                cit_target = _resolve_national_citizen(qr_candidate) if qr_candidate else None
                if not cit_target:
                    skipped_files.append(base_fn)
                    continue
                save_standardized_citizen_files(cit_target, photo_file=ContentFile(file_bytes, name=base_fn))
                matched_photos += 1

            for base_fn, file_bytes in _extract_items(request.FILES.getlist("doc_files")):
                if not base_fn or not file_bytes:
                    continue
                qr_candidate = os.path.splitext(base_fn).__getitem__(0).split("_").__getitem__(0).strip().upper()
                cit_target = _resolve_national_citizen(qr_candidate) if qr_candidate else None
                if not cit_target:
                    skipped_files.append(base_fn)
                    continue
                save_standardized_citizen_files(
                    cit_target,
                    doc_files=[ContentFile(file_bytes, name=base_fn)],
                    source_channel="WALKIN_DESK",
                    uploaded_by=f"{actor_name} (Batch QR Sync)",
                )
                matched_docs += 1

            total_linked = matched_docs + matched_photos
            if total_linked > 0:
                SystemAuditLog.objects.create(
                    barangay=active_barangay,
                    action_type="PORTAL_SYNC_APPROVED",
                    actor_name=actor_name,
                    actor_role=actor_role,
                    reference_code=f"BATCH-QR-{total_linked}",
                    details=f"Batch QR-matched {matched_photos} 2x2 photo(s) and {matched_docs} PDF supporting doc(s). Skipped unmatched: {len(skipped_files)}.",
                )
            skip_msg = f" Skipped {len(skipped_files)} unmatched file(s): {', '.join(skipped_files[:5])}." if skipped_files else ""
            action_notice = f"Batch QR Sync Complete: Attached {matched_photos} 2x2 profile photo(s) and {matched_docs} PDF supporting doc(s) by exact Citizen ID.{skip_msg}"


    theme = active_barangay.get_active_theme() if active_barangay else {
        "title": "BIOAS Command Portal", "banner_text": "Philippine Barangay Information & Operations System",
        "primary_color": "#1E3A8A", "secondary_color": "#F59E0B", "is_occasion": False,
    }

    from citizens.models import CitizenSupportingDocument
    citizens = CitizenProfile.objects.select_related("household").filter(barangay=active_barangay) if active_barangay else CitizenProfile.objects.none()
    all_repo_docs = CitizenSupportingDocument.objects.select_related("citizen").filter(citizen__barangay=active_barangay) if active_barangay else CitizenSupportingDocument.objects.none()
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

    kk_youth = KatipunanKabataanProfile.objects.filter(barangay=active_barangay) if active_barangay else KatipunanKabataanProfile.objects.none()
    sk_projects = SKProjectActivity.objects.filter(barangay=active_barangay) if active_barangay else SKProjectActivity.objects.none()
    measures = LegislativeMeasure.objects.filter(barangay=active_barangay) if active_barangay else LegislativeMeasure.objects.none()
    bdp_projects = DevelopmentPlanProject.objects.filter(barangay=active_barangay) if active_barangay else DevelopmentPlanProject.objects.none()
    audit_logs = SystemAuditLog.objects.filter(barangay=active_barangay)[:50] if active_barangay else SystemAuditLog.objects.none()
    dilg_reports = DILGComplianceReport.objects.filter(barangay=active_barangay) if active_barangay else DILGComplianceReport.objects.none()
    coa_audits = COAAuditCompliance.objects.filter(barangay=active_barangay) if active_barangay else COAAuditCompliance.objects.none()
    turnovers = OfficialTurnoverRecord.objects.filter(barangay=active_barangay) if active_barangay else OfficialTurnoverRecord.objects.none()

    active_citizens = list(citizens.filter(status="ACTIVE_RESIDENT"))
    one_year_ago = date.today() - timedelta(days=365)
    purok_names = ["Purok I", "Purok II", "Purok III", "Purok IV", "Purok V", "Purok VI", "Purok VII"]
    for c in active_citizens:
        if c.purok and c.purok not in purok_names:
            purok_names.append(c.purok)
    purok_rows = [{"name": p, "count": sum(1 for c in active_citizens if (c.purok or "Purok I") == p)} for p in purok_names]

    children_list = [c for c in active_citizens if c.relationship_to_head == "CHILD" or c.age < 18]
    pop_stats = {
        "total_residents": len(active_citizens),
        "male_count": sum(1 for c in active_citizens if c.sex == "MALE"),
        "female_count": sum(1 for c in active_citizens if c.sex == "FEMALE"),
        "registered_voters": sum(1 for c in active_citizens if c.is_registered_voter),
        "non_voters": sum(1 for c in active_citizens if not c.is_registered_voter),
        "purok_rows": purok_rows,
        "children_total": len(children_list),
        "unmarried_children": sum(1 for c in children_list if c.civil_status == "SINGLE"),
        "married_children": sum(1 for c in children_list if c.civil_status == "MARRIED"),
        "senior_count": sum(1 for c in active_citizens if c.is_senior_citizen or c.age >= 60),
        "pwd_count": sum(1 for c in active_citizens if c.is_pwd),
        "solo_parent_count": sum(1 for c in active_citizens if c.is_solo_parent),
        "pregnant_count": sum(1 for c in active_citizens if c.is_pregnant),
        "recent_births_count": sum(1 for c in active_citizens if c.age == 0 or (c.birth_registered_date and c.birth_registered_date >= one_year_ago)),
        "deaths_count": citizens.filter(status="DECEASED").count(),
    }

    household_rows = []
    for hh in households:
        members = [m for m in hh.members.all() if m.status == "ACTIVE_RESIDENT"]
        hh_children = [m for m in members if m.relationship_to_head == "CHILD" or m.age < 18]
        household_rows.append({
            "household": hh,
            "members": members,
            "total_members": len(members),
            "children_count": len(hh_children),
            "unmarried_children": sum(1 for m in hh_children if m.civil_status == "SINGLE"),
            "married_children": sum(1 for m in hh_children if m.civil_status == "MARRIED"),
            "seniors": sum(1 for m in members if m.is_senior_citizen or m.age >= 60),
            "pwds": sum(1 for m in members if m.is_pwd),
            "solo_parents": sum(1 for m in members if m.is_solo_parent),
            "pregnant": sum(1 for m in members if m.is_pregnant),
        })

    turnover_summary = {
        "pending_citizens": citizens.filter(status="PENDING_APPROVAL").count(),
        "open_citizen_reports": citizen_reports.exclude(status="RESOLVED_CLOSED").count(),
        "pending_or_certs": pending_or_certs.count(),
        "active_blotter_holds": blotter_cases.filter(blocks_clearance=True).count(),
        "open_welfare_sheets": abuloy_sheets.exclude(status="TURNED_OVER_SIGNED").count(),
        "unreturned_equipment": equipment_loans.filter(status="OUT_ON_LOAN").count(),
        "pending_coa": coa_audits.exclude(status="CLEARED_LIQUIDATED").count(),
        "pending_dilg": dilg_reports.exclude(status="TRANSMITTED_VERIFIED").count(),
    }
    total_pending_turnover = sum(turnover_summary.values())

    search_index = []
    if "CITIZENS" in visible_modules or "LEDGER_201" in visible_modules:
        target_mod = "LEDGER_201" if "LEDGER_201" in visible_modules else "CITIZENS"
        for c in citizens:
            hh_code = c.household.household_code if c.household else "No Household"
            tags = [t for t, flag in [("Voter", c.is_registered_voter), ("Senior", c.is_senior_citizen), ("PWD", c.is_pwd), ("Solo Parent", c.is_solo_parent), ("4Ps", c.is_4ps_beneficiary), ("Pregnant", c.is_pregnant), ("OFW", c.is_ofw)] if flag]
            detail = f"QR: {c.citizen_qr_id} | {c.purok} | {c.address_line or '-'} | Age {c.age} ({c.get_sex_display()}) | HH: {hh_code} | Job: {c.occupation or '-'} | PhilSys: {c.philsys_id or '-'} | Precinct: {c.precinct_number or '-'} | Mobile: {c.mobile_number or '-'} | {', '.join(tags) or 'General Resident'} | {c.get_status_display()}"
            row_mod = "CITIZENS_INTAKE" if c.status == "PENDING_APPROVAL" else target_mod
            row_lbl = "02B. Pending Queue" if c.status == "PENDING_APPROVAL" else "02C. 201 Master"
            search_index.append({"module_label": row_lbl, "title": f"{c.full_name} [{c.citizen_qr_id}]", "detail": detail, "url": f"/citizen-inspect/{c.id}/"})
    if "CITIZENS" in visible_modules:
        for rep in citizen_reports:
            search_index.append({"module_label": "02. Reports", "title": f"{rep.tracking_code} — {rep.get_category_display()}", "detail": f"Resident: {rep.citizen.full_name} | Landmark: {rep.location_landmark} | {rep.description[:80]} | {rep.get_status_display()}", "url": "?tier=BARANGAY&module=CITIZENS"})
    if "CERTIFICATES" in visible_modules:
        for cert in certificates:
            search_index.append({"module_label": "03. Certificates", "title": f"{cert.control_number} — {cert.get_cert_type_display()}", "detail": f"Citizen: {cert.citizen.full_name} ({cert.citizen.citizen_qr_id}) | Purpose: {getattr(cert, 'purpose', '-')} | Fee: P{getattr(cert, 'fee_amount', 0)} | {cert.get_status_display()}", "url": "?tier=BARANGAY&module=CERTIFICATES"})
    if "BLOTTER" in visible_modules:
        for b in blotter_cases:
            search_index.append({"module_label": "04. Derogatory Record Flag", "title": f"{b.case_number} — {b.complainant_name} vs {b.respondent_name}", "detail": f"{b.get_category_display()} | {b.get_status_display()}", "url": "/?tier=BARANGAY&module=BLOTTER"})
    if "TREASURY" in visible_modules:
        for r in receipts:
            dt = getattr(r, "issued_date", None) or getattr(r, "created_at", "")
            search_index.append({"module_label": "05. Treasury OR", "title": f"OR #{r.or_number} — {getattr(r, 'payor_name', '')}", "detail": f"Amount: P{getattr(r, 'amount_paid', 0)} | Date: {str(dt)[:10]}", "url": "?tier=BARANGAY&module=TREASURY"})
        for a in abuloy_sheets:
            search_index.append({"module_label": "05. Bereavement", "title": f"{a.serial_number} — {getattr(a, 'deceased_name', '')}", "detail": f"Claimant: {getattr(a, 'claimant_name', '-')} | Status: {a.get_status_display()}", "url": "?tier=BARANGAY&module=TREASURY"})
    if "HEALTH" in visible_modules:
        for h in health_records:
            search_index.append({"module_label": "06. Health", "title": f"{h.citizen.full_name} — {getattr(h, 'program_type', 'Consultation')}", "detail": f"Date: {getattr(h, 'visit_date', '')} | {str(getattr(h, 'diagnosis_or_notes', '') or getattr(h, 'notes', ''))[:80]}", "url": "?tier=BARANGAY&module=HEALTH"})
        for m in medicines:
            search_index.append({"module_label": "06. Medicine", "title": f"{getattr(m, 'medicine_name', 'Medicine')}", "detail": f"Stock: {getattr(m, 'stock_quantity', getattr(m, 'quantity_on_hand', 0))}", "url": "?tier=BARANGAY&module=HEALTH"})
    if "WELFARE" in visible_modules:
        for ag in associations:
            search_index.append({"module_label": "07. Association", "title": f"{ag.group_code} — {ag.group_name}", "detail": f"Head: {getattr(ag, 'display_head', '-')} | Members: {getattr(ag, 'member_count', 0)}", "url": "?tier=BARANGAY&module=WELFARE"})
        for s in social_aids:
            search_index.append({"module_label": "07. Social Aid", "title": f"{s.citizen.full_name}", "detail": f"Cycle: {getattr(s, 'distribution_cycle', '-')} | Amount: P{getattr(s, 'cash_amount', getattr(s, 'amount_released', 0))}", "url": "?tier=BARANGAY&module=WELFARE"})
    if "FLEET" in visible_modules:
        for v in vehicles:
            search_index.append({"module_label": "08. Fleet", "title": f"{v.plate_or_body_number} — {getattr(v, 'vehicle_name', '')}", "detail": f"Driver: {getattr(v, 'assigned_driver', '-')} | Status: {v.get_status_display()}", "url": "?tier=BARANGAY&module=FLEET"})
    if "DRRM" in visible_modules:
        for hz in hazards:
            search_index.append({"module_label": "09. BDRRMC", "title": f"{hz.alert_code} — {getattr(hz, 'incident_title', getattr(hz, 'hazard_title', ''))}", "detail": f"Level: {hz.get_alert_level_display()} | Families: {getattr(hz, 'affected_families', 0)}", "url": "?tier=BARANGAY&module=DRRM"})
    if "SK" in visible_modules:
        for sk in sk_projects:
            search_index.append({"module_label": "10. SK Youth", "title": f"{sk.project_code} — {getattr(sk, 'project_title', '')}", "detail": f"Budget: P{getattr(sk, 'allocated_budget', 0)} | Status: {sk.get_status_display()}", "url": "?tier=BARANGAY&module=SK"})
    if "LEGISLATION" in visible_modules:
        for m in measures:
            search_index.append({"module_label": "11. Legislation", "title": f"{m.series_number} — {m.title}", "detail": f"Author: {getattr(m, 'sponsor_author', getattr(m, 'author_name', '-'))} | Status: {m.get_status_display()}", "url": "?tier=BARANGAY&module=LEGISLATION"})
    if "AUDIT" in visible_modules:
        for ca in coa_audits:
            search_index.append({"module_label": "12. COA Audit", "title": f"{ca.audit_reference} — {ca.get_audit_type_display()}", "detail": f"Period: {ca.period_covered} | Amount: P{ca.amount_involved} | {ca.get_status_display()}", "url": "?tier=BARANGAY&module=AUDIT"})
        for dr in dilg_reports:
            search_index.append({"module_label": "12. DILG Report", "title": f"{dr.get_report_category_display()} ({dr.reporting_period})", "detail": f"Ref: {dr.transmittal_reference or '-'} | {dr.get_status_display()}", "url": "?tier=BARANGAY&module=AUDIT"})

    suggestions = [item["title"] for item in search_index]
    query = params.get("q", "").strip()
    if query:
        terms = [t for t in query.lower().split() if t]
        search_results = [
            item for item in search_index
            if all(t in f"{item['module_label']} {item['title']} {item['detail']}".lower() for t in terms)
        ][:50]
    else:
        search_results = []
    city_barangays = BarangayTenant.objects.filter(city_municipality=city).annotate(subdivision_count=Count("subdivisions", distinct=True), structure_count=Count("structures", distinct=True)) if city else BarangayTenant.objects.none()
    province_cities = CityMunicipality.objects.filter(province=province).annotate(barangay_count=Count("barangays", distinct=True)) if province else CityMunicipality.objects.none()

    html_path = Path(__file__).resolve().parent.parent / "bioas_core" / "templates" / "governance" / "dashboard.html"
    template = engines["django"].from_string(html_path.read_text(encoding="utf-8"))
    return HttpResponse(template.render({
        "tier": tier, "module": module, "province": province, "city": city, "barangays": barangays, "active_barangay": active_barangay,
        "theme": theme, "citizens": citizens, "all_repo_docs": all_repo_docs, "households": households, "citizen_reports": citizen_reports,
        "certificates": certificates, "pending_or_certs": pending_or_certs, "blotter_cases": blotter_cases,
        "receipts": receipts, "abuloy_sheets": abuloy_sheets, "total_collections": total_collections,
        "health_records": health_records, "medicines": medicines, "social_aids": social_aids, "associations": associations,
        "socio_counts": {
            "subsistence": citizens.filter(status="ACTIVE_RESIDENT", socioeconomic_tier="SUBSISTENCE").count(),
            "low_income": citizens.filter(status="ACTIVE_RESIDENT", socioeconomic_tier="LOW_INCOME").count(),
            "lower_middle": citizens.filter(status="ACTIVE_RESIDENT", socioeconomic_tier="LOWER_MIDDLE").count(),
            "self_sustaining": citizens.filter(status="ACTIVE_RESIDENT", socioeconomic_tier="SELF_SUSTAINING").count(),
        },
        "vehicles": vehicles, "trips": trips, "equipment_loans": equipment_loans,
        "hazards": hazards, "evac_centers": evac_centers, "kk_youth": kk_youth, "sk_projects": sk_projects,
        "measures": measures, "bdp_projects": bdp_projects, "audit_logs": audit_logs, "dilg_reports": dilg_reports, "coa_audits": coa_audits,
        "turnovers": turnovers, "turnover_summary": turnover_summary, "total_pending_turnover": total_pending_turnover,
        "city_barangays": city_barangays, "province_cities": province_cities,
        "query": query, "search_results": search_results, "suggestions_json": json.dumps(sorted(set(suggestions))), "search_index_json": json.dumps(search_index),
        "pop_stats": pop_stats, "household_rows": household_rows, "action_notice": action_notice,
        "visible_modules": visible_modules, "staff_profile": staff_profile,
    }, request))


@login_required(login_url="/login/")
def theme_settings(request):
    from .models import BarangayStaffProfile

    barangay = BarangayTenant.objects.first()
    showcase, _ = BarangayPortalShowcase.objects.get_or_create(barangay=barangay) if barangay else (None, False)
    User = get_user_model()
    u = request.user
    current_prof = getattr(u, "staff_profile", None)
    can_manage_officers = u.is_superuser or (current_prof and current_prof.role in ("CAPTAIN", "SECRETARY"))
    actor_name = current_prof.full_name if current_prof else (u.get_full_name() or u.username)
    actor_role = current_prof.get_role_display() if current_prof else "System Administrator"
    notice, error = "", ""

    if request.method == "POST":
        act = request.POST.get("action")
        if act == "CREATE_OFFICER" and can_manage_officers and barangay:
            uname = request.POST.get("officer_username", "").strip()
            pwd = request.POST.get("officer_password", "")
            cit_id = request.POST.get("citizen_id", "").strip()
            linked_cit = CitizenProfile.objects.filter(barangay=barangay, id=cit_id, status="ACTIVE_RESIDENT").first() if cit_id else None
            fname = linked_cit.full_name if linked_cit else request.POST.get("officer_full_name", "").strip()
            role = request.POST.get("officer_role", "COUNCILOR")
            seat_code = request.POST.get("officer_seat_code", "").strip()
            committee = request.POST.get("officer_committee", "").strip()
            chosen_mods = request.POST.getlist("modules") or list(BarangayStaffProfile.ROLE_DEFAULT_MODULES.get(role, ["OVERVIEW", "POLICY"]))
            if not uname or len(pwd) < 6 or not fname:
                error = "Full name (from 201 or manual), username, and password (min 6 chars) are required."
            elif linked_cit and hasattr(linked_cit, "staff_account") and linked_cit.staff_account is not None:
                error = f"{linked_cit.full_name} ({linked_cit.citizen_qr_id}) already has an officer account."
            elif User.objects.filter(username=uname).exists():
                error = f"Username '{uname}' already exists."
            else:
                parts = fname.split()
                new_user = User.objects.create_user(username=uname, password=pwd, first_name=parts, last_name=" ".join(parts[1:]))
                auto_status = "ACTIVE" if (u.is_superuser or (current_prof and current_prof.role == "CAPTAIN")) else "PENDING_CAPTAIN"
                sp = BarangayStaffProfile.objects.create(
                    user=new_user,
                    barangay=barangay,
                    citizen=linked_cit,
                    seat_code=seat_code,
                    full_name=fname,
                    role=role,
                    committee_or_unit=committee,
                    allowed_modules=chosen_mods,
                    approval_status=auto_status,
                    created_by=u,
                    approved_by=u if auto_status == "ACTIVE" else None,
                )
                link_note = f" [Linked to 201: {linked_cit.citizen_qr_id}]" if linked_cit else " [Manual Entry]"
                SystemAuditLog.objects.create(
                    barangay=barangay,
                    action_type="ROLE_DELEGATION_SET",
                    actor_name=actor_name,
                    actor_role=actor_role,
                    reference_code=f"ACCT-{uname.upper()}",
                    details=f"Created officer account '{uname}' ({fname} - {sp.get_role_display()}){link_note}, Status: {sp.get_approval_status_display()}, Visible Modules: {', '.join(chosen_mods)}.",
                )
                notice = f"Officer account '{uname}' ({sp.get_role_display()}) created{link_note} with {len(chosen_mods)} configured modules ({sp.get_approval_status_display()})."
        elif act == "UPDATE_OFFICER_MODULES" and can_manage_officers and barangay:
            sp_id = request.POST.get("staff_profile_id")
            sp = BarangayStaffProfile.objects.filter(barangay=barangay, id=sp_id).first()
            if sp:
                chosen_mods = request.POST.getlist("modules") or ["OVERVIEW", "POLICY"]
                new_status = request.POST.get("approval_status", sp.approval_status)
                sp.allowed_modules = chosen_mods
                if new_status in ("ACTIVE", "PENDING_CAPTAIN", "SUSPENDED"):
                    sp.approval_status = new_status
                    if new_status == "ACTIVE" and not sp.approved_by:
                        sp.approved_by = u
                sp.save()
                SystemAuditLog.objects.create(
                    barangay=barangay,
                    action_type="ROLE_DELEGATION_SET",
                    actor_name=actor_name,
                    actor_role=actor_role,
                    reference_code=f"MOD-{sp.user.username.upper()}",
                    details=f"Updated account '{sp.user.username}' ({sp.full_name} - {sp.get_role_display()}) to {sp.get_approval_status_display()} with modules: {', '.join(chosen_mods)}.",
                )
                notice = f"Updated permissions & visible modules for {sp.full_name} ({sp.get_role_display()})."
        elif act == "UPDATE_SHOWCASE" and showcase:
            showcase.hero_tagline = request.POST.get("hero_tagline", showcase.hero_tagline).strip()
            showcase.background_image_url = request.POST.get("background_image_url", "").strip()
            showcase.featured_photo_url = request.POST.get("featured_photo_url", "").strip()
            showcase.accomplishment_1 = request.POST.get("accomplishment_1", showcase.accomplishment_1).strip()
            showcase.accomplishment_2 = request.POST.get("accomplishment_2", showcase.accomplishment_2).strip()
            showcase.accomplishment_3 = request.POST.get("accomplishment_3", showcase.accomplishment_3).strip()
            showcase.save()
            notice = "Login Portal Background Photo, Seal & Barangay Accomplishments updated!"
        elif act == "UPDATE_THEME" and barangay:
            barangay.default_primary_color = request.POST.get("primary_color", "#1E3A8A").strip()
            barangay.default_secondary_color = request.POST.get("secondary_color", "#F59E0B").strip()
            barangay.save(update_fields=["default_primary_color", "default_secondary_color"])
            notice = "Barangay branding colors updated!"
        elif act == "UPDATE_PROFILE":
            uname = request.POST.get("username", "").strip()
            if uname and User.objects.filter(username=uname).exclude(id=u.id).exists():
                error = f"Username '{uname}' is already taken."
            elif uname:
                u.username = uname
                u.first_name = request.POST.get("first_name", "").strip()
                u.last_name = request.POST.get("last_name", "").strip()
                u.email = request.POST.get("email", "").strip()
                u.save()
                notice = "Staff account profile updated!"
        elif act == "UPDATE_PASSWORD":
            pw1 = request.POST.get("new_password", "")
            pw2 = request.POST.get("confirm_password", "")
            if len(pw1) < 6:
                error = "Password must be at least 6 characters."
            elif pw1 != pw2:
                error = "Passwords do not match."
            else:
                u.set_password(pw1)
                u.save()
                update_session_auth_hash(request, u)
                notice = "Password updated securely!"
        elif act == "REGISTER_BARANGAY_TENANT" and u.is_superuser:
            from django.utils import timezone
            prov_nm = request.POST.get("province_name", "").strip()
            city_nm = request.POST.get("city_name", "").strip()
            brgy_nm = request.POST.get("barangay_name", "").strip()
            b_class = request.POST.get("barangay_classification", "").strip().upper()
            if not prov_nm or not city_nm or not brgy_nm or b_class not in ("URBAN", "RURAL"):
                error = "Province, City/Municipality, Barangay Name, and mandatory Classification (Urban or Rural) are all required."
            else:
                prov_obj, _ = Province.objects.get_or_create(
                    name__iexact=prov_nm,
                    defaults={"code": prov_nm[:3].upper(), "name": prov_nm},
                )
                city_obj, _ = CityMunicipality.objects.get_or_create(
                    province=prov_obj,
                    name__iexact=city_nm,
                    defaults={"code": f"{prov_obj.code}-{city_nm[:3].upper()}", "name": city_nm},
                )
                t_code = f"{prov_obj.code}-{city_nm[:3].upper()}-{brgy_nm[:3].upper()}-{BarangayTenant.objects.count() + 1:03d}"
                new_b = BarangayTenant.objects.create(
                    city_municipality=city_obj,
                    tenant_code=t_code,
                    name=brgy_nm,
                    barangay_classification=b_class,
                    classification_supporting_doc=request.FILES.get("classification_supporting_doc"),
                    classification_updated_at=timezone.now(),
                    classification_updated_by=u.get_full_name() or u.username,
                    status="FULL_ACTIVE",
                )
                SystemAuditLog.objects.create(
                    barangay=new_b,
                    action_type="PORTAL_SYNC_APPROVED",
                    actor_name=u.get_full_name() or u.username,
                    actor_role="SUPERUSER_ADMIN",
                    reference_code=t_code,
                    details=f"Registered live Barangay '{brgy_nm}' ({city_nm}, {prov_nm}) with mandatory classification: {new_b.get_barangay_classification_display()}.",
                )
                notice = f"Live Barangay '{brgy_nm}' registered as {new_b.get_barangay_classification_display()} (Tenant Code: {t_code})!"
        elif act == "RECLASSIFY_BARANGAY":
            if not u.is_superuser:
                error = "Access Denied: Only an Administrator account can process Rural-to-Urban or Urban-to-Rural Barangay reclassification."
            elif not barangay:
                error = "No active Barangay selected."
            else:
                new_class = request.POST.get("new_classification", "").strip().upper()
                sup_doc = request.FILES.get("classification_supporting_doc")
                if new_class not in ("URBAN", "RURAL"):
                    error = "Please select a valid PSA classification (Urban Barangay or Rural Barangay)."
                elif not sup_doc:
                    error = "Complete supporting reclassification document (PSA Certification / Sanggunian Ordinance) is required before upgrading classification."
                else:
                    old_label = barangay.get_barangay_classification_display()
                    barangay.barangay_classification = new_class
                    barangay.classification_supporting_doc = sup_doc
                    barangay.classification_updated_at = timezone.now()
                    barangay.classification_updated_by = u.get_full_name() or u.username
                    barangay.save()
                    SystemAuditLog.objects.create(
                        barangay=barangay,
                        action_type="PORTAL_SYNC_APPROVED",
                        actor_name=u.get_full_name() or u.username,
                        actor_role="SUPERUSER_ADMIN",
                        reference_code=barangay.tenant_code,
                        details=f"Admin reclassified {barangay.name} from {old_label} to {barangay.get_barangay_classification_display()} with verified supporting document.",
                    )
                    notice = f"Classification updated immediately: {barangay.name} is now officially classified as {barangay.get_barangay_classification_display()}!"


    staff_list = BarangayStaffProfile.objects.select_related("user", "citizen").filter(barangay=barangay) if barangay else []
    available_201 = CitizenProfile.objects.filter(barangay=barangay, status="ACTIVE_RESIDENT", staff_account__isnull=True).order_by("last_name", "first_name") if barangay else []
    p_col = getattr(barangay, "default_primary_color", "#1E3A8A") if barangay else "#1E3A8A"
    s_col = getattr(barangay, "default_secondary_color", "#F59E0B") if barangay else "#F59E0B"
    tpl = """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Command Settings &amp; Officer Access</title>
<style>
*{box-sizing:border-box;font-family:system-ui,sans-serif}body{margin:0;background:#f3f4f6}
.top{background:{{ p_col }};color:#fff;padding:14px 24px;display:flex;justify-content:space-between;border-bottom:4px solid {{ s_col }}}
.top a{color:#fff;text-decoration:none;font-weight:700}.wrap{max-width:960px;margin:22px auto;padding:0 16px}
.card{background:#fff;border-radius:10px;padding:18px;box-shadow:0 1px 4px rgba(0,0,0,.08);margin-bottom:16px}
label{display:block;font-weight:700;font-size:.8rem;margin:8px 0 4px}input,select{width:100%;padding:8px;border:1px solid #d1d5db;border-radius:6px}
.mod-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:6px;margin-top:8px}
.mod-item{display:flex;align-items:center;gap:6px;background:#f8fafc;border:1px solid #e2e8f0;padding:6px 8px;border-radius:6px;font-size:.78rem;font-weight:600;cursor:pointer}
.mod-item input{width:auto;margin:0}button.save{margin-top:12px;padding:9px 15px;background:{{ p_col }};color:#fff;border:0;border-radius:6px;font-weight:700;cursor:pointer}
.preset{padding:5px 9px;border:1px solid #d1d5db;border-radius:5px;background:#f9fafb;cursor:pointer;font-size:.78rem;font-weight:700;margin-right:6px}
</style></head><body>
<div class="top"><strong>Command Settings, Officer Access &amp; Account</strong><a href="/">&larr; Dashboard</a></div>
<div class="wrap">
{% if notice %}<div class="card" style="background:#dcfce7;color:#166534;font-weight:700;">{{ notice }}</div>{% endif %}
{% if error %}<div class="card" style="background:#fee2e2;color:#991b1b;font-weight:700;">{{ error }}</div>{% endif %}
<div class="card" style="border-top:4px solid #0f766e;">
  <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">
    <div>
      <h3 style="margin:0;">0. Official PSA Barangay Classification &amp; Live Setup Status</h3>
      {% if barangay %}
      <div style="font-size:.84rem;color:#334155;margin-top:4px;">
        <strong>{{ barangay.name }}</strong>, {{ barangay.city_municipality.name }}, {{ barangay.city_municipality.province.name }} &bull; Current Status:
        {% if barangay.barangay_classification == "URBAN" %}
          <span style="background:#dbeafe;color:#1e40af;padding:3px 10px;border-radius:999px;font-weight:800;font-size:.76rem;">&#127961; URBAN BARANGAY</span>
        {% else %}
          <span style="background:#dcfce7;color:#166534;padding:3px 10px;border-radius:999px;font-weight:800;font-size:.76rem;">&#127806; RURAL BARANGAY</span>
        {% endif %}
        {% if barangay.classification_supporting_doc %}&bull; <a href="{{ barangay.classification_supporting_doc.url }}" target="_blank" style="color:#0f766e;font-weight:700;">View Verified Proof &#8599;</a>{% endif %}
      </div>
      {% endif %}
    </div>
  </div>
  {% if u.is_superuser and barangay %}
  <form method="post" enctype="multipart/form-data" style="margin-top:12px;padding-top:12px;border-top:1px solid #e2e8f0;display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px;align-items:end;">
    {% csrf_token %}<input type="hidden" name="action" value="RECLASSIFY_BARANGAY">
    <div>
      <label style="margin-top:0;">Admin-Only Reclassification *</label>
      <select name="new_classification" required>
        <option value="RURAL" {% if barangay.barangay_classification == "RURAL" %}selected{% endif %}>Rural Barangay</option>
        <option value="URBAN" {% if barangay.barangay_classification == "URBAN" %}selected{% endif %}>Urban Barangay (Reclassified / HUC / Urbanized)</option>
      </select>
    </div>
    <div>
      <label style="margin-top:0;">Verified Supporting Reclassification Proof *</label>
      <input type="file" name="classification_supporting_doc" accept=".pdf,.png,.jpg,.jpeg" required style="padding:6px;">
    </div>
    <div>
      <button type="submit" class="save" style="margin:0;width:100%;background:#0f766e;">Verify &amp; Update Classification Immediately</button>
    </div>
  </form>
  {% elif barangay %}
  <p style="font-size:.78rem;color:#64748b;margin:8px 0 0;"><em>Note: Reclassification between Rural and Urban Barangay is restricted strictly to Administrator accounts upon submission and verification of supporting documents.</em></p>
  {% endif %}
  {% if u.is_superuser %}
  <details style="margin-top:12px;">
    <summary style="cursor:pointer;font-weight:700;font-size:.82rem;color:#1e3a8a;">+ Register New Live Barangay Tenant (Mandatory Province, City/Municipality, Barangay &amp; Urban/Rural Classification)</summary>
    <form method="post" enctype="multipart/form-data" style="margin-top:10px;display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;align-items:end;">
      {% csrf_token %}<input type="hidden" name="action" value="REGISTER_BARANGAY_TENANT">
      <div><label style="margin-top:0;">Province *</label><input name="province_name" placeholder="e.g., Nueva Ecija" required></div>
      <div><label style="margin-top:0;">City / Municipality *</label><input name="city_name" placeholder="e.g., Cabanatuan City" required></div>
      <div><label style="margin-top:0;">Barangay Name *</label><input name="barangay_name" placeholder="e.g., Barangay Lagare" required></div>
      <div>
        <label style="margin-top:0;">Barangay Classification *</label>
        <select name="barangay_classification" required>
          <option value="RURAL">Rural Barangay</option>
          <option value="URBAN">Urban Barangay</option>
        </select>
      </div>
      <div><label style="margin-top:0;">Supporting Proof (Optional)</label><input type="file" name="classification_supporting_doc" accept=".pdf,.png,.jpg,.jpeg" style="padding:6px;"></div>
      <div><button type="submit" class="save" style="margin:0;width:100%;">Activate Live Barangay</button></div>
    </form>
  </details>
  {% endif %}
</div>

{% if can_manage_officers and barangay %}
<div class="card" style="border-top:4px solid #16a34a;">
  <h3 style="margin-top:0;">1. Create Elected / Appointed Officer Account (From 201 Master File or Manual Input)</h3>
  <p style="font-size:.82rem;color:#475569;margin-top:-6px;">Pick a verified resident from the <strong>201 Master File</strong> to auto-fill &amp; link their 201 record, or leave on <strong>Manual Input</strong>.</p>
  <form method="post">{% csrf_token %}<input type="hidden" name="action" value="CREATE_OFFICER">
    <div style="margin-bottom:10px;background:#eff6ff;border:1px solid #bfdbfe;padding:10px 12px;border-radius:8px;">
      <label style="margin-top:0;color:#1e3a8a;">Select Verified Resident from 201 Master File:</label>
      <select id="cit201Sel" name="citizen_id" onchange="pick201Resident(this)">
        <option value="">-- Manual Input (Not Yet in 201 Master File) --</option>
        {% for c in available_201 %}<option value="{{ c.id }}" data-name="{{ c.full_name }}">[{{ c.citizen_qr_id }}] {{ c.full_name }} &mdash; {{ c.purok }}</option>{% endfor %}
      </select>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;">
      <div><label>Officer Full Name *</label><input id="offFullName" name="officer_full_name" placeholder="e.g., Hon. Maria Clara Reyes" required></div>
      <div><label>Official Role *</label><select id="roleSel" name="officer_role" onchange="applyRolePreset(this.value)">{% for k,v in role_choices %}<option value="{{ k }}">{{ v }}</option>{% endfor %}</select></div>
      <div><label>Seat / Designation Code</label><input name="officer_seat_code" placeholder="e.g., SEAT-CAPTAIN"></div>
      <div><label>Committee / Unit</label><input name="officer_committee" placeholder="e.g., Executive"></div>
      <div><label>Login Username *</label><input name="officer_username" placeholder="e.g., capt.reyes" required></div>
      <div><label>Initial Password (min 6 chars) *</label><input type="password" name="officer_password" required></div>
    </div>
    <label style="margin-top:12px;">Configurable Sidebar Modules for This Account:</label>
    <div class="mod-grid" id="newModGrid">{% for code,label in module_choices %}<label class="mod-item"><input type="checkbox" name="modules" value="{{ code }}"> {{ label }}</label>{% endfor %}</div>
    <button type="submit" class="save">Create Officer Account &amp; Save Permissions</button>
  </form>
</div>
<div class="card" style="border-top:4px solid {{ p_col }};">
  <h3 style="margin-top:0;">2. Existing Elected &amp; Appointed Officer Accounts (Approve &amp; Customize Modules)</h3>
  {% for sp in staff_list %}
  <form method="post" style="border:1px solid #e2e8f0;border-radius:8px;padding:12px;margin-bottom:10px;background:#f8fafc;">{% csrf_token %}
    <input type="hidden" name="action" value="UPDATE_OFFICER_MODULES"><input type="hidden" name="staff_profile_id" value="{{ sp.id }}">
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
      <div><strong>{{ sp.full_name }}</strong> (<code>{{ sp.user.username }}</code>) &mdash; <span style="color:#1e3a8a;font-weight:700;">{{ sp.get_role_display }}</span> {% if sp.citizen %}<span style="background:#dcfce7;color:#166534;padding:2px 7px;border-radius:999px;font-size:.72rem;font-weight:700;">201 Linked: {{ sp.citizen.citizen_qr_id }}</span>{% endif %}</div>
      <div style="display:flex;gap:8px;align-items:center;">
        <select name="approval_status" style="width:auto;padding:5px 8px;font-size:.8rem;font-weight:700;">{% for k,v in status_choices %}<option value="{{ k }}" {% if sp.approval_status == k %}selected{% endif %}>{{ v }}</option>{% endfor %}</select>
        <button type="submit" class="save" style="margin:0;padding:6px 12px;font-size:.8rem;">Save Access</button>
      </div>
    </div>
    <div class="mod-grid">{% for code,label in module_choices %}<label class="mod-item" style="background:#fff;"><input type="checkbox" name="modules" value="{{ code }}" {% if code in sp.get_visible_modules %}checked{% endif %}> {{ label }}</label>{% endfor %}</div>
  </form>
  {% empty %}<p style="font-size:.84rem;color:#64748b;">No officer profiles created yet.</p>{% endfor %}
</div>
{% endif %}
{% if showcase %}<div class="card" style="border-top:4px solid {{ s_col }};"><h3 style="margin-top:0;">3. Login Screen Photos &amp; Accomplishments</h3><form method="post">{% csrf_token %}<input type="hidden" name="action" value="UPDATE_SHOWCASE"><label>Hero Tagline</label><input name="hero_tagline" value="{{ showcase.hero_tagline }}"><label>Background Photo URL</label><input name="background_image_url" value="{{ showcase.background_image_url }}"><label>Seal / Logo URL</label><input name="featured_photo_url" value="{{ showcase.featured_photo_url }}"><label>Accomplishment 1</label><input name="accomplishment_1" value="{{ showcase.accomplishment_1 }}"><label>Accomplishment 2</label><input name="accomplishment_2" value="{{ showcase.accomplishment_2 }}"><label>Accomplishment 3</label><input name="accomplishment_3" value="{{ showcase.accomplishment_3 }}"><button type="submit" class="save">Save Showcase</button></form></div>{% endif %}
<div class="card"><h3 style="margin-top:0;">4. Barangay Colors</h3><div style="margin-bottom:8px;"><button type="button" class="preset" onclick="sc('#1E3A8A','#F59E0B')">DILG Navy &amp; Gold</button><button type="button" class="preset" onclick="sc('#065F46','#FBBF24')">Emerald &amp; Gold</button><button type="button" class="preset" onclick="sc('#7F1D1D','#F59E0B')">Maroon &amp; Amber</button></div><form method="post">{% csrf_token %}<input type="hidden" name="action" value="UPDATE_THEME"><label>Primary Color</label><input type="color" id="p" name="primary_color" value="{{ p_col }}"><label>Accent Color</label><input type="color" id="s" name="secondary_color" value="{{ s_col }}"><button type="submit" class="save">Apply Colors</button></form></div>
<div class="card"><h3 style="margin-top:0;">5. My Staff Profile</h3><form method="post">{% csrf_token %}<input type="hidden" name="action" value="UPDATE_PROFILE"><label>Username</label><input name="username" value="{{ u.username }}" required><label>Email</label><input type="email" name="email" value="{{ u.email }}"><label>First Name</label><input name="first_name" value="{{ u.first_name }}"><label>Last Name</label><input name="last_name" value="{{ u.last_name }}"><button type="submit" class="save">Save Profile</button></form></div>
<div class="card"><h3 style="margin-top:0;">6. Change Password</h3><form method="post">{% csrf_token %}<input type="hidden" name="action" value="UPDATE_PASSWORD"><label>New Password</label><input type="password" name="new_password" required><label>Confirm Password</label><input type="password" name="confirm_password" required><button type="submit" class="save">Update Password</button></form></div>
</div>
<script>
const ROLE_PRESETS={{ role_presets_json|safe }};
function pick201Resident(sel){const opt=sel.options[sel.selectedIndex];const inp=document.getElementById('offFullName');if(opt&&opt.dataset.name){inp.value=opt.dataset.name;inp.readOnly=true;inp.style.background='#eff6ff';}else{inp.value='';inp.readOnly=false;inp.style.background='#fff';}}
function applyRolePreset(r){const list=ROLE_PRESETS[r]||['OVERVIEW','POLICY'];document.querySelectorAll('#newModGrid input[type="checkbox"]').forEach(cb=>{cb.checked=list.includes(cb.value);});}
if(document.getElementById('roleSel'))applyRolePreset(document.getElementById('roleSel').value);
function sc(a,b){document.getElementById('p').value=a;document.getElementById('s').value=b;}
</script></body></html>"""
    return HttpResponse(engines["django"].from_string(tpl).render({
        "u": u, "p_col": p_col, "s_col": s_col, "notice": notice, "error": error, "showcase": showcase,
        "barangay": barangay, "can_manage_officers": can_manage_officers, "staff_list": staff_list, "available_201": available_201,
        "role_choices": BarangayStaffProfile.ROLE_CHOICES, "status_choices": BarangayStaffProfile.STATUS_CHOICES,

        "module_choices": BarangayStaffProfile.ALL_MODULE_CHOICES, "role_presets_json": json.dumps(BarangayStaffProfile.ROLE_DEFAULT_MODULES),
    }, request))
