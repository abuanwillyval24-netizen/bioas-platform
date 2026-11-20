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
    tpl = """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>BIOAS Official Portal — {{ brgy.name|default:"Barangay Lagare" }}</title>
<style>*{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}body{margin:0;min-height:100vh;""" + bg_css + """color:#fff;display:flex;flex-direction:column;justify-content:space-between}.hero-stage{padding:28px 36px 24px;display:flex;flex-direction:column;justify-content:space-between;min-height:74vh}.top-row{display:flex;justify-content:space-between;align-items:flex-start;gap:24px;flex-wrap:wrap}.brand{display:flex;align-items:center;gap:14px;max-width:620px}.seal{width:64px;height:64px;border-radius:50%;object-fit:cover;border:2px solid rgba(255,255,255,.5);background:#fff;box-shadow:0 6px 18px rgba(0,0,0,.35)}.seal-fallback{width:64px;height:64px;border-radius:50%;background:rgba(255,255,255,.12);border:2px solid #f59e0b;display:flex;align-items:center;justify-content:center;font-weight:900;font-size:1.1rem;color:#fbbf24;letter-spacing:.05em}.gov-tag{font-size:.72rem;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:#fbbf24;margin-bottom:4px}.brand h1{margin:0;font-size:1.75rem;font-weight:800;letter-spacing:-.01em;text-shadow:0 2px 10px rgba(0,0,0,.4)}.brand p{margin:4px 0 0;color:#e2e8f0;font-size:.92rem;text-shadow:0 1px 6px rgba(0,0,0,.4)}.login-card{width:360px;max-width:100%;background:rgba(255,255,255,.97);color:#0f172a;border-radius:14px;padding:24px 26px;box-shadow:0 20px 50px rgba(0,0,0,.45);border-top:4px solid #1e3a8a}.login-card h2{margin:0 0 4px;font-size:1.15rem;color:#0f172a}.login-card .sub{margin:0 0 14px;font-size:.8rem;color:#64748b}label{display:block;font-size:.78rem;font-weight:700;color:#334155;margin:10px 0 4px}input{width:100%;padding:10px 12px;border:1px solid #cbd5e1;border-radius:8px;font-size:.9rem;background:#f8fafc}input:focus{outline:none;border-color:#1e3a8a;background:#fff;box-shadow:0 0 0 3px rgba(30,58,138,.12)}button{width:100%;margin-top:16px;padding:11px;background:#1e3a8a;color:#fff;border:0;border-radius:8px;font-weight:700;font-size:.92rem;cursor:pointer;transition:background .15s}button:hover{background:#1d4ed8}.recovery-row{text-align:center;margin-top:10px;font-size:.75rem;color:#64748b}.recovery-row a{color:#1e3a8a;text-decoration:none;font-weight:600}.recovery-row a:hover{text-decoration:underline}.err{background:#fef2f2;color:#b91c1c;border:1px solid #fecaca;padding:8px 10px;border-radius:8px;font-size:.8rem;margin-bottom:10px;font-weight:600}.links{margin-top:12px;padding-top:12px;border-top:1px solid #e2e8f0;display:flex;justify-content:space-between;font-size:.78rem}.links a{color:#1e3a8a;font-weight:700;text-decoration:none}.links a:hover{text-decoration:underline}.accomplishments{display:flex;gap:10px;flex-wrap:wrap;max-width:860px;margin-top:24px}.acc-pill{background:rgba(15,23,42,.68);backdrop-filter:blur(8px);border:1px solid rgba(255,255,255,.18);padding:8px 14px;border-radius:10px;font-size:.8rem;color:#f8fafc}.acc-pill span{color:#fbbf24;font-weight:800;margin-right:6px}.gov-footer{background:#0b1324;border-top:3px solid #f59e0b;color:#cbd5e1}.tier1-grid{max-width:1240px;margin:0 auto;padding:28px 36px;display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:24px}.tier1-grid h4{margin:0 0 10px;font-size:.84rem;text-transform:uppercase;letter-spacing:.06em;color:#fbbf24}.tier1-grid p,.tier1-grid li{font-size:.78rem;line-height:1.6;color:#cbd5e1;margin:0 0 4px}.tier1-grid ul{list-style:none;padding:0;margin:0}.tier1-grid a{color:#e2e8f0;text-decoration:none}.tier1-grid a:hover{color:#fbbf24;text-decoration:underline}.agency-badge{display:flex;align-items:center;gap:10px;margin-bottom:8px}.agency-badge img,.agency-mini{width:38px;height:38px;border-radius:50%;object-fit:cover;border:1px solid #f59e0b;background:#1e3a8a;color:#fbbf24;display:inline-flex;align-items:center;justify-content:center;font-weight:800;font-size:.75rem}.social-row{display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap}.social-btn{display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:8px;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.2);color:#fff;font-size:.75rem;font-weight:800;text-decoration:none;transition:background .15s,transform .15s}.social-btn:hover{background:#f59e0b;color:#0f172a;transform:translateY(-2px)}.tier2-strip{background:#060a14;border-top:1px solid rgba(255,255,255,.12);padding:22px 36px}.tier2-grid{max-width:1240px;margin:0 auto;display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:24px;align-items:start}.rep-seal{display:flex;gap:12px;align-items:flex-start}.coat{width:46px;height:46px;border-radius:50%;border:2px solid #94a3b8;background:#0f172a;color:#f8fafc;display:flex;align-items:center;justify-content:center;font-weight:900;font-size:.72rem;flex-shrink:0}.tier2-grid h5{margin:0 0 8px;font-size:.8rem;text-transform:uppercase;letter-spacing:.05em;color:#f8fafc}.tier2-grid p,.tier2-grid li{font-size:.75rem;line-height:1.55;color:#94a3b8;margin:0 0 4px}.tier2-grid ul{list-style:none;padding:0;margin:0}.tier2-grid a{color:#94a3b8;text-decoration:none}.tier2-grid a:hover{color:#fff;text-decoration:underline}</style></head><body>
<div class="hero-stage">
  <div class="top-row">
    <div class="brand">
      {% if showcase and showcase.featured_photo_url %}<img src="{{ showcase.featured_photo_url }}" alt="Official Seal" class="seal">{% else %}<div class="seal-fallback">BIOAS</div>{% endif %}
      <div>
        <div class="gov-tag">Republic of the Philippines • Official LGU Command Portal</div>
        <h1>{{ brgy.name|default:"Barangay Lagare" }}</h1>
        <p>{{ showcase.hero_tagline|default:"Transparent, Fast & Citizen-Centered Digital Barangay Governance" }}</p>
      </div>
    </div>
    <div class="login-card">
      <h2>Authorized Sign In</h2>
      <p class="sub">Barangay, SK & LGU Operations Access</p>
      {% if error %}<div class="err">{{ error }}</div>{% endif %}
      <form method="post">{% csrf_token %}
        <label>Username</label><input name="username" placeholder="Enter official username" required autofocus>
        <label>Password</label><input type="password" name="password" placeholder="Enter password" required>
        <button type="submit">Log In</button>
      </form>
      <div class="recovery-row"><a href="/portal-info/#recovery">Forgot Password?</a> &nbsp;•&nbsp; <a href="/portal-info/#recovery">Forgot Username?</a></div>
      <div class="links"><a href="/portal/">Citizen Sign-Up</a><a href="/citizen-home/">Resident Self-Service</a></div>
    </div>
  </div>
  <div class="accomplishments">
    <div class="acc-pill"><span>✓</span>{{ showcase.accomplishment_1|default:"100% Digital Citizen 201 & QR ID Synchronization" }}</div>
    <div class="acc-pill"><span>✓</span>{{ showcase.accomplishment_2|default:"Zero-Backlog Barangay & Business Clearance Issuance" }}</div>
    <div class="acc-pill"><span>✓</span>{{ showcase.accomplishment_3|default:"COA & DILG Full Disclosure Policy Compliant" }}</div>
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
        <li><a href="/portal-info/#mandate">• Who We Are / Mandate</a></li>
        <li><a href="/portal-info/#officials">• Key Officials</a></li>
        <li><a href="/portal-info/#charter">• Citizen’s Charter</a></li>
        <li><a href="/portal-info/#transparency">• Transparency Seal</a></li>
      </ul>
    </div>
    <div>
      <h4>Help & Legal</h4>
      <ul>
        <li><a href="/portal-info/#guide">• User Guide / How to Register</a></li>
        <li><a href="/portal-info/#faqs">• FAQs</a></li>
        <li><a href="/portal-info/#contact">• Contact Us / Helpdesk</a></li>
        <li><a href="/portal-info/#privacy">• Data Privacy Notice (RA 10173)</a></li>
        <li><a href="/portal-info/#terms">• Terms of Use</a></li>
      </ul>
    </div>
    <div>
      <h4>Connect With Us</h4>
      <div class="social-row">


def staff_logout(request):
    logout(request)
    return redirect("/login/")


@login_required(login_url="/login/")
def command_dashboard(request):
    params = request.GET
    tier = params.get("tier", "BARANGAY").upper()
    module = params.get("module", "OVERVIEW").upper()

    province = Province.objects.first()
    city = CityMunicipality.objects.filter(province=province).first() if province else None
    barangays = BarangayTenant.objects.select_related("city_municipality__province").all()
    active_barangay = barangays.filter(tenant_code=params.get("tenant")).first() or barangays.first()

    theme = active_barangay.get_active_theme() if active_barangay else {
        "title": "BIOAS Command Portal", "banner_text": "Philippine Barangay Information & Operations System",
        "primary_color": "#1E3A8A", "secondary_color": "#F59E0B", "is_occasion": False,
    }

    citizens = CitizenProfile.objects.filter(barangay=active_barangay) if active_barangay else CitizenProfile.objects.none()
    households = Household.objects.filter(barangay=active_barangay) if active_barangay else Household.objects.none()
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
    audit_logs = SystemAuditLog.objects.filter(barangay=active_barangay)[:15] if active_barangay else SystemAuditLog.objects.none()
    dilg_reports = DILGComplianceReport.objects.filter(barangay=active_barangay) if active_barangay else DILGComplianceReport.objects.none()
    coa_audits = COAAuditCompliance.objects.filter(barangay=active_barangay) if active_barangay else COAAuditCompliance.objects.none()
    turnovers = OfficialTurnoverRecord.objects.filter(barangay=active_barangay) if active_barangay else OfficialTurnoverRecord.objects.none()

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

    suggestions = [
        "Barangay Clearance", "Certificate of Indigency", "First-Time Jobseeker Certification",
        "Bereavement Welfare Sheet", "Official Receipt (OR)", "Health Immunization", "Social Aid",
        "Senior Citizens Association", "COA Audit", "Governance Turnover (BGTT)", "RA 11261 Policy", "RA 9262 VAWC Policy",
        "Vehicle Trip Ticket", "Hazard Alert", "SK ABYIP Project", "Barangay Ordinance", "DILG Report",
    ] + [f"{c.full_name} [{c.citizen_qr_id}]" for c in citizens] + [f"{a.group_name} (Head: {a.display_head})" for a in associations]

    query = params.get("q", "").strip()
    search_results = [item for item in suggestions if query.lower() in item.lower()] if query else []
    city_barangays = BarangayTenant.objects.filter(city_municipality=city).annotate(subdivision_count=Count("subdivisions", distinct=True), structure_count=Count("structures", distinct=True)) if city else BarangayTenant.objects.none()
    province_cities = CityMunicipality.objects.filter(province=province).annotate(barangay_count=Count("barangays", distinct=True)) if province else CityMunicipality.objects.none()

    html_path = Path(__file__).resolve().parent.parent / "bioas_core" / "templates" / "governance" / "dashboard.html"
    template = engines["django"].from_string(html_path.read_text(encoding="utf-8"))
    return HttpResponse(template.render({
        "tier": tier, "module": module, "province": province, "city": city, "barangays": barangays, "active_barangay": active_barangay,
        "theme": theme, "citizens": citizens, "households": households, "citizen_reports": citizen_reports,
        "certificates": certificates, "pending_or_certs": pending_or_certs, "blotter_cases": blotter_cases,
        "receipts": receipts, "abuloy_sheets": abuloy_sheets, "total_collections": total_collections,
        "health_records": health_records, "medicines": medicines, "social_aids": social_aids, "associations": associations,
        "vehicles": vehicles, "trips": trips, "equipment_loans": equipment_loans,
        "hazards": hazards, "evac_centers": evac_centers, "kk_youth": kk_youth, "sk_projects": sk_projects,
        "measures": measures, "bdp_projects": bdp_projects, "audit_logs": audit_logs, "dilg_reports": dilg_reports, "coa_audits": coa_audits,
        "turnovers": turnovers, "turnover_summary": turnover_summary, "total_pending_turnover": total_pending_turnover,
        "city_barangays": city_barangays, "province_cities": province_cities,
        "query": query, "search_results": search_results, "suggestions_json": json.dumps(sorted(set(suggestions))),
    }, request))

@login_required(login_url="/login/")
def theme_settings(request):
    barangay = BarangayTenant.objects.first()
    User = get_user_model()
    u = request.user
    notice, error = "", ""

    if request.method == "POST":
        act = request.POST.get("action")
        if act == "UPDATE_THEME" and barangay:
            barangay.primary_color = request.POST.get("primary_color", "#1E3A8A").strip()
            barangay.secondary_color = request.POST.get("secondary_color", "#F59E0B").strip()
            barangay.save(update_fields=["primary_color", "secondary_color"])
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
            pw1, pw2 = request.POST.get("new_password", ""), request.POST.get("confirm_password", "")
            if len(pw1) < 6:
                error = "Password must be at least 6 characters."
            elif pw1 != pw2:
                error = "Passwords do not match."
            else:
                u.set_password(pw1)
                u.save()
                update_session_auth_hash(request, u)
                notice = "Password updated securely!"

    p_col = getattr(barangay, "primary_color", "#1E3A8A") if barangay else "#1E3A8A"
    s_col = getattr(barangay, "secondary_color", "#F59E0B") if barangay else "#F59E0B"
    tpl = """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Command Settings</title>
<style>*{box-sizing:border-box;font-family:system-ui,sans-serif}body{margin:0;background:#f3f4f6}.top{background:{{ p_col }};color:#fff;padding:14px 24px;display:flex;justify-content:space-between;border-bottom:4px solid {{ s_col }}}.top a{color:#fff;text-decoration:none;font-weight:700}.wrap{max-width:740px;margin:22px auto;padding:0 16px}.card{background:#fff;border-radius:10px;padding:18px;box-shadow:0 1px 4px rgba(0,0,0,.08);margin-bottom:16px}label{display:block;font-weight:700;font-size:.82rem;margin:8px 0 4px}input{width:100%;padding:8px;border:1px solid #d1d5db;border-radius:6px}button.save{margin-top:12px;padding:9px 15px;background:{{ p_col }};color:#fff;border:0;border-radius:6px;font-weight:700;cursor:pointer}.preset{padding:5px 9px;border:1px solid #d1d5db;border-radius:5px;background:#f9fafb;cursor:pointer;font-size:.78rem;font-weight:700;margin-right:6px}</style></head><body>
<div class="top"><strong>&#9881; Command Settings & Account</strong><a href="/">← Dashboard</a></div>
<div class="wrap">{% if notice %}<div class="card" style="background:#dcfce7;color:#166534;font-weight:700;">{{ notice }}</div>{% endif %}{% if error %}<div class="card" style="background:#fee2e2;color:#991b1b;font-weight:700;">{{ error }}</div>{% endif %}
<div class="card"><h3 style="margin-top:0;">1. Staff Profile</h3><form method="post">{% csrf_token %}<input type="hidden" name="action" value="UPDATE_PROFILE"><label>Username</label><input name="username" value="{{ u.username }}" required><label>Email</label><input type="email" name="email" value="{{ u.email }}"><label>First Name</label><input name="first_name" value="{{ u.first_name }}"><label>Last Name</label><input name="last_name" value="{{ u.last_name }}"><button type="submit" class="save">Save Profile</button></form></div>
<div class="card"><h3 style="margin-top:0;">2. Change Password</h3><form method="post">{% csrf_token %}<input type="hidden" name="action" value="UPDATE_PASSWORD"><label>New Password</label><input type="password" name="new_password" required><label>Confirm Password</label><input type="password" name="confirm_password" required><button type="submit" class="save">Update Password</button></form></div>
<div class="card"><h3 style="margin-top:0;">3. Barangay Colors</h3><div style="margin-bottom:8px;"><button type="button" class="preset" onclick="sc('#1E3A8A','#F59E0B')">DILG Navy & Gold</button><button type="button" class="preset" onclick="sc('#065F46','#FBBF24')">Emerald & Gold</button><button type="button" class="preset" onclick="sc('#7F1D1D','#F59E0B')">Maroon & Amber</button></div><form method="post">{% csrf_token %}<input type="hidden" name="action" value="UPDATE_THEME"><label>Primary Color</label><input type="color" id="p" name="primary_color" value="{{ p_col }}"><label>Accent Color</label><input type="color" id="s" name="secondary_color" value="{{ s_col }}"><button type="submit" class="save">Apply Colors</button></form></div></div>
<script>function sc(a,b){document.getElementById('p').value=a;document.getElementById('s').value=b;}</script></body></html>"""
    return HttpResponse(engines["django"].from_string(tpl).render({"u": u, "p_col": p_col, "s_col": s_col, "notice": notice, "error": error}, request))
def portal_info(request):
    brgy = BarangayTenant.objects.first()
    tpl = """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>Official Portal Information — {{ brgy.name|default:"Barangay Lagare" }}</title>
<style>*{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}body{margin:0;background:#f1f5f9;color:#0f172a}.top{background:#1e3a8a;color:#fff;padding:16px 28px;display:flex;justify-content:space-between;align-items:center;border-bottom:4px solid #f59e0b}.top a{color:#fff;text-decoration:none;font-weight:700;background:rgba(255,255,255,.15);padding:7px 14px;border-radius:8px}.wrap{max-width:920px;margin:24px auto;padding:0 16px}.card{background:#fff;border-radius:12px;padding:20px 24px;margin-bottom:16px;box-shadow:0 2px 8px rgba(15,23,42,.06);border-left:5px solid #1e3a8a}h2{margin:0 0 8px;color:#1e3a8a;font-size:1.15rem}p,li{font-size:.9rem;line-height:1.6;color:#334155}</style></head><body>
<div class="top"><strong>{{ brgy.name|default:"Barangay Lagare" }} — Official Public Information & Helpdesk</strong><a href="/login/">← Back to Sign In</a></div>
<div class="wrap">
  <div class="card" id="recovery"><h2>Account Recovery (Forgot Username or Password)</h2><p>For LGU security and audit compliance under RA 10173, Barangay and SK staff password resets are verified through the <strong>Punong Barangay (Captain)</strong> or <strong>System Administrator</strong> via the Official Roster module, or at the Barangay Secretariat Desk during office hours (Monday–Friday, 8:00 AM – 5:00 PM).</p></div>
  <div class="card" id="mandate"><h2>Who We Are / Mandate</h2><p>Pursuant to Republic Act No. 7160 (Local Government Code of 1991), <strong>{{ brgy.name|default:"Barangay Lagare" }}</strong> serves as the primary planning and implementing unit of government policies, plans, programs, projects, and activities in the community, and as a forum wherein the collective views of the people may be expressed, crystallized, and considered.</p></div>
  <div class="card" id="officials"><h2>Key Officials</h2><p>Led by the <strong>Punong Barangay</strong>, seven (7) <strong>Sangguniang Barangay Members (Kagawad)</strong>, the <strong>Sangguniang Kabataan (SK) Chairperson</strong> and seven (7) <strong>SK Councilors</strong>, supported by the <strong>Barangay Secretary</strong>, <strong>Barangay Treasurer</strong>, and <strong>Chief Tanod (Hepe)</strong>.</p></div>
  <div class="card" id="charter"><h2>Citizen’s Charter (RA 11032 Ease of Doing Business)</h2><ul><li><strong>Barangay Clearance / Residency / Good Moral:</strong> Same-day issuance upon 201 verification and Treasurer Official Receipt.</li><li><strong>Barangay Business Clearance:</strong> Same-day assessment and endorsement for local business permits.</li><li><strong>Certificate of Indigency & First-Time Job Seeker (RA 11261):</strong> Fee-exempt issuance upon documentary verification.</li></ul></div>
  <div class="card" id="transparency"><h2>Transparency Seal & Full Disclosure Policy</h2><p>In compliance with DILG Memorandum Circulars and COA rules, Barangay Budget Allocations, 20% Barangay Development Plan (BDP) utilization, and Official Receipt collections are logged with immutable audit trails.</p></div>
  <div class="card" id="guide"><h2>User Guide / How to Register</h2><p>Click <strong>Citizen Sign-Up</strong> on the main portal, complete your personal details, upload a valid supporting document (PDF, Word, or Photo), sign the RA 10173 electronic acknowledgement, and wait 24–48 hours for Barangay Secretary activation.</p></div>
  <div class="card" id="faqs"><h2>Frequently Asked Questions (FAQs)</h2><p><strong>How do I check my registration?</strong> Once approved by the Barangay Secretary, use your assigned Citizen QR ID on the <strong>Resident Self-Service</strong> page to request certificates or submit community reports.</p></div>
  <div class="card" id="contact"><h2>Contact Us / Helpdesk</h2><p><strong>Office Address:</strong> Barangay Hall, {{ brgy.name|default:"Barangay Lagare" }}, {{ brgy.city_municipality.name|default:"Cabanatuan City" }}, {{ brgy.city_municipality.province.name|default:"Nueva Ecija" }}, Philippines<br><strong>Email:</strong> info@barangaylagare.gov.ph &nbsp;|&nbsp; <strong>Tel:</strong> (044) 463-0000</p></div>
  <div class="card" id="privacy"><h2>Data Privacy Notice (Republic Act No. 10173)</h2><p>All personal information collected through the BIOAS Portal is processed strictly for lawful Barangay 201 Registry, civil documentation, social welfare, and public safety administration in accordance with the Data Privacy Act of 2012.</p></div>
  <div class="card" id="terms"><h2>Terms of Use</h2><p>Unauthorized access, falsification of resident records, or misuse of official QR verification credentials is punishable under applicable Philippine laws and LGU ordinances.</p></div>
</div></body></html>"""
    return HttpResponse(engines["django"].from_string(tpl).render({"brgy": brgy}, request))
