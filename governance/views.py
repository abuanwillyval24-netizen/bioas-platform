import json
from pathlib import Path
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template import engines
from django.db.models import Count, Sum
from django.contrib.auth import authenticate, login, logout, get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from .models import Province, CityMunicipality, BarangayTenant, OfficialTurnoverRecord
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
    barangay = BarangayTenant.objects.first()
    p_col = getattr(barangay, "primary_color", "#1E3A8A") if barangay else "#1E3A8A"
    s_col = getattr(barangay, "secondary_color", "#F59E0B") if barangay else "#F59E0B"
    error = ""

    if request.method == "POST":
        user = authenticate(request, username=request.POST.get("username", "").strip(), password=request.POST.get("password", ""))
        if user is not None:
            login(request, user)
            if barangay:
                SystemAuditLog.objects.create(
                    barangay=barangay, action_type="STAFF_LOGIN", actor_name=user.username,
                    actor_role="Command Staff", reference_code=f"LOGIN-{user.id}", details="Signed in to BIOAS Command Portal.",
                )
            return redirect(request.GET.get("next") or "/")
        error = "Invalid staff username or password."

    tpl = """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>BIOAS Staff Login — {{ barangay.name|default:"Command Portal" }}</title>
<style>*{box-sizing:border-box;font-family:system-ui,sans-serif}body{margin:0;background:#f3f4f6;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:16px}.box{background:#fff;max-width:410px;width:100%;border-radius:12px;overflow:hidden;box-shadow:0 4px 16px rgba(0,0,0,.12)}.hdr{background:{{ p_col }};color:#fff;padding:20px;text-align:center;border-bottom:4px solid {{ s_col }}}.body{padding:22px}label{display:block;font-weight:700;font-size:.82rem;margin:10px 0 4px;color:#374151}input{width:100%;padding:10px;border:1px solid #d1d5db;border-radius:6px}button{margin-top:16px;width:100%;padding:11px;background:{{ p_col }};color:#fff;border:0;border-radius:6px;font-weight:700;cursor:pointer}.err{background:#fee2e2;color:#991b1b;padding:9px;border-radius:6px;font-size:.84rem;font-weight:700;margin-bottom:10px}.links{margin-top:16px;text-align:center;font-size:.82rem;border-top:1px solid #e5e7eb;padding-top:12px}.links a{color:{{ p_col }};font-weight:700;text-decoration:none;margin:0 8px}</style></head><body>
<div class="box"><div class="hdr"><h2 style="margin:0 0 4px;font-size:1.15rem;">{{ barangay.name|default:"BIOAS Command Portal" }}</h2><small>Authorized Barangay & LGU Officials Login</small></div>
<div class="body">{% if error %}<div class="err">{{ error }}</div>{% endif %}
<form method="post">{% csrf_token %}<label>Staff Username</label><input type="text" name="username" required autofocus /><label>Password</label><input type="password" name="password" required /><button type="submit">Sign In to Command Dashboard →</button></form>
<div class="links">Resident Services: <a href="/portal/">New Sign-Up</a> | <a href="/citizen-home/">Citizen Login</a></div>
</div></div></body></html>"""
    return HttpResponse(engines["django"].from_string(tpl).render({"barangay": barangay, "p_col": p_col, "s_col": s_col, "error": error}, request))


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
