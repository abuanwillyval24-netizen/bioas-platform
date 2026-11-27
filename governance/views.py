from django.utils import timezone
import json
from pathlib import Path
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template import engines
from django.db.models import Count, Sum
from django.contrib.auth import authenticate, login, logout, get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
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


@never_cache
def staff_login(request):
    import hashlib, random, secrets, time
    from django.contrib.auth.hashers import check_password
    from django.core.cache import cache
    from .models import BarangayStaffProfile, TrustedLoginDevice
    for sp_u in BarangayStaffProfile.objects.filter(official_code__isnull=True):
        sp_u.save()
    if request.user.is_authenticated:
        return redirect('/')
    if request.session.get('citizen_auth_id') and not request.GET.get('logout'):
        return redirect('/citizen-home/')
    error, notice, otp_pending, otp_masked_email = '', '', False, ''
    role_type = (request.POST.get('role_type') or request.GET.get('role') or 'OFFICIAL').strip().upper()
    ref_code = (request.POST.get('ref_code') or '').strip().upper()
    username_in = (request.POST.get('username') or '').strip()
    brgy = BarangayTenant.objects.first()
    showcase = BarangayPortalShowcase.objects.filter(barangay=brgy).first() if brgy else None
    raw_tok = request.COOKIES.get('bioas_dev_tok', '')
    dev_tok = raw_tok or secrets.token_urlsafe(32)
    ua_str = request.META.get('HTTP_USER_AGENT', '')[:160]
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    client_ip = (xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR', '')) or '0.0.0.0'
    ip_prefix = '.'.join(client_ip.split('.')[:2]) if '.' in client_ip else client_ip[:24]
    dev_hash = hashlib.sha256(f'{dev_tok}|{ua_str[:80]}'.encode('utf-8')).hexdigest()
    bf_ip, bf_usr = f'bioas_bf_ip:{client_ip}', (f'bioas_bf_usr:{username_in.lower()}' if username_in else '')
    def _is_locked(): return (cache.get(bf_ip, 0) >= 5) or (bool(bf_usr) and cache.get(bf_usr, 0) >= 5)
    def _rec_fail(): cache.set(bf_ip, cache.get(bf_ip, 0) + 1, 900); bf_usr and cache.set(bf_usr, cache.get(bf_usr, 0) + 1, 900)
    def _clr_fail(): cache.delete(bf_ip); bf_usr and cache.delete(bf_usr)
    def _finish_login(acct_key, r_type, obj_id, approve_ws=False):
        _clr_fail()
        defs = {'device_label': ua_str, 'ip_prefix': ip_prefix}
        if approve_ws: defs['is_approved_workstation'] = True
        TrustedLoginDevice.objects.update_or_create(account_key=acct_key, device_token_hash=dev_hash, defaults=defs)
        if r_type == 'CITIZEN':
            request.session['citizen_auth_id'] = obj_id
            resp = redirect('/citizen-home/')
        else:
            u_obj = get_user_model().objects.filter(id=obj_id).first()
            if u_obj: login(request, u_obj)
            resp = redirect(request.GET.get('next') or '/')
        resp.set_cookie('bioas_dev_tok', dev_tok, max_age=7776000, httponly=True, samesite='Lax')
        return resp
    def _trigger_2fa(acct_key, r_type, obj_id, email_addr, disp_name, approve_ws=False):
        code = f'{random.SystemRandom().randint(100000, 999999)}'
        at_pos = email_addr.find('@') if '@' in email_addr else -1
        masked = (email_addr[:2] + '***' + email_addr[at_pos:]) if at_pos > 1 else ('***' + email_addr[at_pos:] if at_pos >= 0 else 'your email')
        request.session['bioas_2fa_pending'] = {'code': code, 'acct_key': acct_key, 'role_type': r_type, 'obj_id': obj_id, 'masked_email': masked, 'attempts': 0, 'expires_at': int(time.time()) + 300, 'approve_ws': approve_ws}
        if email_addr:
            try:
                from django.core.mail import send_mail
                from django.conf import settings as dj_settings
                send_mail(f'[{brgy.name if brgy else chr(66)+chr(73)+chr(79)+chr(65)+chr(83)}] Security OTP ({r_type})', f'Good day {disp_name}, new device ({client_ip}). Your 6-digit OTP is: {code} (valid 5 mins).', getattr(dj_settings, 'DEFAULT_FROM_EMAIL', None), [email_addr], fail_silently=False)
            except Exception as mail_err:
                print('BIOAS_2FA_EMAIL_ERROR:', repr(mail_err))
        return masked
    if request.method == 'POST':
        if request.POST.get('login_step') == 'VERIFY_LOGIN_OTP':
            pend = request.session.get('bioas_2fa_pending')
            if not pend or time.time() > pend.get('expires_at', 0):
                request.session.pop('bioas_2fa_pending', None)
                error = 'Your 6-digit OTP has expired (5-minute limit). Please sign in again.'
            elif request.POST.get('login_otp_code', '').strip() != pend.get('code'):
                pend['attempts'] = pend.get('attempts', 0) + 1
                if pend['attempts'] >= 3:
                    request.session.pop('bioas_2fa_pending', None)
                    error = 'Maximum 3 OTP attempts exceeded. Please sign in again.'
                else:
                    request.session['bioas_2fa_pending'] = pend
                    otp_pending, otp_masked_email = True, pend.get('masked_email', '')
                    error = f'Invalid 6-digit OTP ({3 - pend[chr(97)+chr(116)+chr(116)+chr(101)+chr(109)+chr(112)+chr(116)+chr(115)]} attempt(s) left).'
            else:
                request.session.pop('bioas_2fa_pending', None)
                return _finish_login(pend['acct_key'], pend['role_type'], pend['obj_id'], approve_ws=bool(pend.get('approve_ws')))
        elif _is_locked():
            error = 'Security Lockout: Too many failed sign-in attempts. Please wait 15 minutes before trying again.'
        elif role_type == 'CITIZEN':
            cand = CitizenProfile.objects.filter(citizen_qr_id__iexact=ref_code, portal_username__iexact=username_in).first() if (ref_code and username_in) else None
            if not cand or not cand.portal_password_hash or not check_password(request.POST.get('password', ''), cand.portal_password_hash):
                _rec_fail()
                error = 'Invalid Citizen Reference Number, Username, or Password.'
            else:
                acct_key = f'CIT:{cand.id}'
                tr = TrustedLoginDevice.objects.filter(account_key=acct_key, device_token_hash=dev_hash).first()
                if tr:
                    return _finish_login(acct_key, 'CITIZEN', cand.id)
                has_smtp = bool(getattr(__import__('django.conf', fromlist=['settings']).settings, 'EMAIL_HOST_USER', '').strip()) and bool(cand.email_address)
                if not has_smtp:
                    error = 'New device detected, but no verified email is configured on this account. Please visit the Barangay Hall Walk-In Desk to verify your identity and register an email address.'
                else:
                    otp_masked_email = _trigger_2fa(acct_key, 'CITIZEN', cand.id, cand.email_address or '', cand.full_name)
                    otp_pending, notice = True, f'New device detected. A 6-digit verification OTP has been sent to {otp_masked_email} (expires in 5 minutes).'
        elif any(m in ua_str.lower() for m in ('mobile', 'android', 'iphone', 'ipad', 'ipod', 'windows phone')):
            error = 'Security Policy: Barangay Official sign-in is blocked on mobile phones/tablets and restricted to approved Barangay Office Desktop/Laptop workstations only.'
        else:
            GENERIC_OFF_ERR = 'Invalid Barangay Official Unique Code, Username, or Password.'
            user = authenticate(request, username=username_in, password=request.POST.get('password', ''))
            if user is None:
                _rec_fail()
                error = GENERIC_OFF_ERR
            else:
                prof = getattr(user, 'staff_profile', None)
                if not user.is_superuser:
                    if not prof or not ref_code or (prof.official_code or '').upper() != ref_code:
                        _rec_fail()
                        error = GENERIC_OFF_ERR
                    elif not prof.is_term_active:
                        error = 'Your Official Term has ended and turnover is complete. Your Official Code is deactivated -- please select Login as: Citizen.'
                    elif prof.approval_status != 'ACTIVE':
                        error = f'Account status: {prof.get_approval_status_display()}. Punong Barangay approval is required before signing in.'
                elif prof and ref_code and (prof.official_code or '').upper() != ref_code:
                    _rec_fail()
                    error = GENERIC_OFF_ERR
                if not error:
                    acct_key = f'OFF:{user.id}'
                    tr = TrustedLoginDevice.objects.filter(account_key=acct_key, device_token_hash=dev_hash).first()
                    has_any_ws = TrustedLoginDevice.objects.filter(account_key=acct_key, is_approved_workstation=True).exists()
                    is_bootstrap_admin = bool(user.is_superuser or (prof and prof.role == 'CAPTAIN')) and not has_any_ws
                    if tr and tr.is_approved_workstation:
                        return _finish_login(acct_key, 'OFFICIAL', user.id, approve_ws=True)
                    if not is_bootstrap_admin:
                        TrustedLoginDevice.objects.update_or_create(account_key=acct_key, device_token_hash=dev_hash, defaults={'device_label': ua_str, 'ip_prefix': ip_prefix, 'is_approved_workstation': False})
                        error = 'Workstation Pre-Authorization Required: This browser/workstation is pending Punong Barangay / System Admin approval in Staff Roster. Mobile Desktop-Site spoofing is blocked.'
                    else:
                        em = (user.email or (prof.citizen.email_address if (prof and prof.citizen) else '') or '').strip()
                        has_smtp = bool(getattr(__import__('django.conf', fromlist=['settings']).settings, 'EMAIL_HOST_USER', '').strip()) and bool(em)
                        if not has_smtp:
                            return _finish_login(acct_key, 'OFFICIAL', user.id, approve_ws=True)
                        otp_masked_email = _trigger_2fa(acct_key, 'OFFICIAL', user.id, em, prof.full_name if prof else user.username, approve_ws=True)
                        otp_pending, notice = True, f'Bootstrap Office Workstation detected. A 6-digit verification OTP has been sent to {otp_masked_email} (expires in 5 minutes).'
    bg_css = f'background:linear-gradient(120deg,rgba(15,23,42,.82) 0%,rgba(15,23,42,.52) 55%,rgba(15,23,42,.75) 100%),url({q}{showcase.background_image_url}{q}) center/cover no-repeat fixed;' if (showcase and showcase.background_image_url) else 'background:radial-gradient(circle at 20% 25%,#1d4ed8 0%,#0f172a 55%,#090d16 100%);'
    tpl_str = (Path(__file__).resolve().parent.parent / 'bioas_core' / 'templates' / 'governance' / 'login.html').read_text(encoding='utf-8')
    resp_get = HttpResponse(engines['django'].from_string(tpl_str).render({'brgy': brgy, 'showcase': showcase, 'bg_css': bg_css, 'error': error, 'notice': notice, 'role_type': role_type, 'ref_code': ref_code, 'username_in': username_in, 'otp_pending': otp_pending, 'otp_masked_email': otp_masked_email}, request))
    if not raw_tok:
        resp_get.set_cookie('bioas_dev_tok', dev_tok, max_age=7776000, httponly=True, samesite='Lax')
    return resp_get


def staff_logout(request):
    logout(request)
    return redirect("/login/")


@never_cache
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
        for extra_sub in ("CITIZENS_INTAKE", "HOUSEHOLDS", "SHARED_GALLERY", "DOCS_REPO", "CITIZEN_REPORTS", "PHOTO_REVIEW", "REGISTRY_SERVICE", "INBOUND_DOCS", "INBOUND_LUPON", "INBOUND_SAFETY", "INBOUND_PROJECTS", "INBOUND_WELFARE", "INBOUND_FACILITY", "IT_ADMIN"):
            if extra_sub not in visible_modules:
                visible_modules.append(extra_sub)

    if tier == "BARANGAY" and module not in visible_modules:
        module = "OVERVIEW"

    actor_name = staff_profile.full_name if staff_profile else (request.user.get_full_name() or request.user.username)
    actor_role = staff_profile.get_role_display() if staff_profile else "System Administrator"

    action_notice = request.session.pop("bioas_flash_notice", "")
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
                        login_link = request.build_absolute_uri("/login/?role=CITIZEN")
                        uname_disp = target.portal_username or target.citizen_qr_id.lower()
                        send_mail(
                            subject=f"[{active_barangay.name}] Official 201 Account Approved & Activated - {target.citizen_qr_id}",
                            message=(
                                f"Good day {target.full_name},\n\n"
                                f"Congratulations! Your Barangay 201 Citizen Registration has been verified and officially APPROVED by {active_barangay.name}.\n\n"
                                f"========================================\n"
                                f"OFFICIAL CITIZEN SIGN-IN & REFERENCE DETAILS\n"
                                f"Citizen Unique Reference ID : {target.citizen_qr_id}\n"
                                f"Portal Sign-In Username     : {uname_disp}\n"
                                f"Account Status              : ACTIVE VERIFIED RESIDENT\n"
                                f"Unified Citizen Sign-In URL : {login_link}\n"
                                f"========================================\n"
                                f"HOW TO SIGN IN:\n"
                                f"1. Open {login_link}\n"
                                f"2. Enter your Portal Username ({uname_disp}) and your registered password.\n"
                                f"3. Keep your Citizen Unique Reference ID ({target.citizen_qr_id}) saved for Barangay Hall transactions, clearances, and account recovery.\n\n"
                                f"NEXT STEP - COMPLETE YOUR 201 PROFILE:\n"
                                f"Please sign in at {login_link} using your Portal Username ({uname_disp}) and password to complete your remaining 201 profile details and access Barangay certificates.\n\n"
                                f"Respectfully,\n"
                                f"Office of the Barangay Secretary\n"
                                f"{active_barangay.name}"
                            ),
                            from_email=getattr(dj_settings, "DEFAULT_FROM_EMAIL", None),
                            recipient_list=[target.email_address],
                            fail_silently=False,
                        )
                    except Exception as mail_err:
                        print("BIOAS_APPROVAL_EMAIL_ERROR:", repr(mail_err))
                action_notice = f"Approved {target.full_name} ({target.citizen_qr_id}) into 201 Master & 02E Gallery! Sent 'Complete your profile' notification."
        elif act == "REJECT_CITIZEN":
            target = CitizenProfile.objects.filter(id=request.POST.get("citizen_id"), barangay=active_barangay).first()
            reason = request.POST.get("reject_reason", "").strip() or "Incomplete or unverified supporting documents"
            if target:
                qr_ref = target.citizen_qr_id
                full_nm = target.full_name
                target.status = "REJECTED_RETURNED"
                target.rejection_reason = reason
                target.save(update_fields=["status", "rejection_reason"])
                if target.email_address:
                    try:
                        from django.core.mail import send_mail
                        from django.conf import settings as dj_settings
                        send_mail(
                            subject=f"[{active_barangay.name}] 201 Registration Returned for Revision",
                            message=(
                                f"Good day {full_nm},\n\n"
                                f"Your Barangay 201 registration ({qr_ref}) was returned for revision.\n"
                                f"Reason: {reason}\n\n"
                                f"Please log in at /citizen-home/ using your Portal Username ({target.portal_username or qr_ref}) to update your details or supporting documents and resubmit.\n\n"
                                f"-- {active_barangay.name} Office of the Barangay Secretary"
                            ),
                            from_email=getattr(dj_settings, "DEFAULT_FROM_EMAIL", None),
                            recipient_list=[target.email_address],
                            fail_silently=True,
                        )
                    except Exception:
                        pass
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
        elif act == "SET_CERT_HOLD_OR_DISPUTE_REPLY" and active_barangay:
            c_obj = CertificateRequest.objects.filter(barangay=active_barangay, control_number=request.POST.get("control_number", "").strip().upper()).first()
            if c_obj:
                mode = request.POST.get("resolution_mode", "HOLD")
                msg = request.POST.get("office_note", "").strip()
                if mode == "HOLD":
                    c_obj.status = "REJECTED_HOLD"
                    c_obj.hold_or_delay_reason = msg or "Additional verification required at Barangay Hall."
                else:
                    c_obj.dispute_status = "REISSUED_RESOLVED"
                    c_obj.office_dispute_reply = msg or "Verified & corrected for re-issuance."
                    if c_obj.status == "REJECTED_HOLD":
                        c_obj.status = "READY_TO_PRINT"
                c_obj.save()
                SystemAuditLog.objects.create(barangay=active_barangay, action_type="PORTAL_SYNC_APPROVED", actor_name=actor_name, actor_role=actor_role, reference_code=c_obj.control_number, details=f"Certificate {c_obj.control_number} updated ({mode}): {msg}")
                action_notice = f"Updated certificate {c_obj.control_number} ({mode})."
        elif act == "UPDATE_RESERVATION_STATUS" and active_barangay:
            from assets_fleet.models import FacilityEquipmentReservation
            rv = FacilityEquipmentReservation.objects.filter(barangay=active_barangay, id=request.POST.get("res_id")).first()
            st = request.POST.get("new_status", "APPROVED")
            if rv and st in ("APPROVED", "REJECTED", "COMPLETED"):
                rv.status = st
                rv.custodian_remarks = request.POST.get("remarks", "").strip()
                rv.save()
                SystemAuditLog.objects.create(barangay=active_barangay, action_type="PORTAL_SYNC_APPROVED", actor_name=actor_name, actor_role=actor_role, reference_code=rv.booking_code, details=f"Reservation {rv.booking_code} marked {st}.")
                action_notice = f"Reservation {rv.booking_code} updated to {rv.get_status_display()}."
        elif act == "ISSUE_LUPON_ESUMMON" and active_barangay:
            import secrets
            from blotter.models import LuponSummonNotice
            bc = BlotterCase.objects.filter(barangay=active_barangay, case_number=request.POST.get("case_number", "").strip().upper()).first()
            rc = CitizenProfile.objects.filter(barangay=active_barangay, citizen_qr_id=request.POST.get("recipient_qr", "").strip().upper(), is_archived=False).first()
            if not (bc and rc):
                action_notice = "Blocked: Valid Case Number and Resident Reference ID are required."
            else:
                try:
                    scode = f"SUM-{timezone.now().year}-{secrets.randbelow(90000)+10000}-{secrets.token_hex(2).upper()}"
                    LuponSummonNotice.objects.create(barangay=active_barangay, blotter_case=bc, recipient_citizen=rc, summon_code=scode, party_role=request.POST.get("party_role", "RESPONDENT"), hearing_date=request.POST.get("hearing_date"), hearing_time=request.POST.get("hearing_time"), venue=request.POST.get("venue", "Barangay Lupon Session Hall").strip(), issued_by=actor_name)
                    SystemAuditLog.objects.create(barangay=active_barangay, action_type="PORTAL_SYNC_APPROVED", actor_name=actor_name, actor_role=actor_role, reference_code=scode, details=f"Issued e-Summon {scode} to {rc.full_name} for {bc.case_number}.")
                    action_notice = f"Issued Verified e-Summon {scode} to {rc.full_name} ({rc.citizen_qr_id})."
                except Exception as sm_err:
                    action_notice = f"Blocked: {sm_err}"
        elif act == "CREATE_VAWC_BPO" and active_barangay and ("VAWC" in visible_modules):
            import secrets
            v_code = f"VAWC-{timezone.now().year}-{secrets.randbelow(9000)+1000}-{secrets.token_hex(2).upper()}"
            BlotterCase.objects.create(
                barangay=active_barangay, case_number=v_code, category="VAWC_RA9262", is_vawc_confidential=True,
                complainant_name=request.POST.get("victim_name", "").strip(),
                respondent_name=request.POST.get("respondent_name", "").strip(),
                incident_location=request.POST.get("incident_location", "").strip(),
                narrative_summary=request.POST.get("narrative", "").strip(),
                presiding_officer=actor_name,
            )
            SystemAuditLog.objects.create(barangay=active_barangay, action_type="PORTAL_SYNC_APPROVED", actor_name=actor_name, actor_role=actor_role, reference_code=v_code, details="Confidential RA 9262 VAWC / BPO case logged (identity sealed).")
            action_notice = f"Confidential RA 9262 VAWC / BPO Record {v_code} logged and sealed."
        elif act == "UPDATE_ANON_REPORT" and active_barangay:
            from .models import AnonymousCommunityReport
            ar = AnonymousCommunityReport.objects.filter(barangay=active_barangay, id=request.POST.get("anon_id")).first()
            if ar and (ar.report_type != "OFFICIAL_COMPLAINT" or (request.user.is_superuser or actor_role == 'CAPTAIN')):
                ar.status = request.POST.get("status", ar.status)
                ar.official_response = request.POST.get("official_response", "").strip()[:240]
                ar.save(update_fields=["status", "official_response"])
                action_notice = f"Updated Anonymous Report {ar.tracking_code}."
        elif act == "SAVE_COMMITTEE_ENTRY" and active_barangay:
            import secrets
            from .models import CommitteeModuleEntry
            m_code = request.POST.get("module_code", "").strip().upper()
            if m_code in ("BADAC", "BCPC", "BARC", "NUTRITION", "DAYCARE") and (m_code in visible_modules):
                ref = f"{m_code}-{timezone.now().year}-{secrets.randbelow(90000)+10000}-{secrets.token_hex(2).upper()}"
                CommitteeModuleEntry.objects.create(
                    barangay=active_barangay, module_code=m_code, reference_code=ref,
                    subject_or_beneficiary=request.POST.get("subject_or_beneficiary", "").strip(),
                    category_or_metric=request.POST.get("category_or_metric", "").strip(),
                    details=request.POST.get("details", "").strip(),
                    status=request.POST.get("status", "ACTIVE_MONITORED").strip(),
                    recorded_by=actor_name,
                )
                SystemAuditLog.objects.create(barangay=active_barangay, action_type="PORTAL_SYNC_APPROVED", actor_name=actor_name, actor_role=actor_role, reference_code=ref, details=f"Recorded {m_code} entry {ref}.")
                action_notice = f"Saved {m_code} record ({ref})."
        elif act == "PURGE_INCOMPLETE_SAMPLE_CITIZENS" and active_barangay and (request.user.is_superuser or actor_role == "CAPTAIN"):
            from django.db.models import Q
            from citizens.models import CitizenSupportingDocument
            stale_qs = CitizenProfile.objects.filter(barangay=active_barangay).filter(
                Q(citizen_qr_id__startswith="CIT-") | Q(encoded_by__icontains="Bulk") | Q(status__in=["PENDING_APPROVAL", "PENDING_PORTAL", "REJECTED_RETURNED"])
            )
            docs_qs = CitizenSupportingDocument.objects.filter(citizen__in=stale_qs)
            for d in docs_qs:
                if d.file:
                    d.file.delete(save=False)
            d_cnt = docs_qs.delete()
            CertificateRequest.objects.filter(citizen__in=stale_qs).delete()
            c_cnt = stale_qs.delete()
            SystemAuditLog.objects.create(barangay=active_barangay, action_type="PORTAL_SYNC_APPROVED", actor_name=actor_name, actor_role=actor_role, reference_code="PURGE-BULK-201", details=f"Hard-purged {c_cnt} incomplete/bulk sample citizens and {d_cnt} supporting documents.")
            action_notice = f"Hard-purged {c_cnt} incomplete/bulk sample citizens and {d_cnt} supporting documents from database."
        elif act == "CONSOLIDATE_DUPLICATE_STAGING" and active_barangay:
            seen, wiped = {}, 0
            for c in CitizenProfile.objects.filter(barangay=active_barangay, status="PENDING_APPROVAL").order_by("id"):
                k = (c.first_name.strip().lower(), c.last_name.strip().lower(), c.birth_date)
                if k not in seen:
                    seen[k] = c
                else:
                    prim = seen[k]
                    c.photo_data_uri = ""
                    c.supporting_doc_data_uri = ""
                    if c.photo: c.photo.delete(save=False)
                    if c.supporting_document: c.supporting_document.delete(save=False)
                    for rd in c.repository_docs.all():
                        rd.file_data_uri = ""
                        if rd.file: rd.file.delete(save=False)
                        rd.save(update_fields=["file", "file_data_uri"])
                    c.status = "REJECTED_RETURNED"
                    c.rejection_remarks = f"[ZERO-DELETION AUDIT ARCHIVE] Duplicate submission consolidated into primary record {prim.citizen_qr_id}; all duplicate attachments wiped."
                    c.save()
                    wiped += 1
            SystemAuditLog.objects.create(barangay=active_barangay, action_type="PORTAL_SYNC_APPROVED", actor_name=actor_name, actor_role=actor_role, reference_code="DEDUP-WIPE", details=f"Consolidated {wiped} duplicate pending record(s) with zero row deletion and wiped duplicate attachments.")
            action_notice = f"Zero-Deletion Cleanup Complete: Retained primary record(s) and wiped attachments on {wiped} duplicate audit stub(s)."
        elif act == "CREATE_WALKIN_ICN" and active_barangay:
            import secrets
            from .models import WalkInIncidentTicket
            icode = f"ICN-{timezone.now().year}-{secrets.randbelow(90000)+10000}-{secrets.token_hex(2).upper()}"
            WalkInIncidentTicket.objects.create(barangay=active_barangay, icn_code=icode, category=request.POST.get("category", "WALKIN_201_SIGNUP"), description=request.POST.get("description", "").strip(), created_by_name=actor_name, created_by_role=actor_role)
            SystemAuditLog.objects.create(barangay=active_barangay, action_type="PORTAL_SYNC_APPROVED", actor_name=actor_name, actor_role=actor_role, reference_code=icode, details=f"Opened Walk-In Incident {icode}.")
            action_notice = f"Created Incident Control Number {icode} in your Open ICN Bucket."
        elif act == "CLOSE_WALKIN_ICN" and active_barangay:
            from .models import WalkInIncidentTicket
            tkt = WalkInIncidentTicket.objects.filter(barangay=active_barangay, id=request.POST.get("icn_id")).first()
            if tkt:
                tkt.status = "CLOSED_ARCHIVED"
                tkt.closed_at = timezone.now()
                tkt.resolution_note = request.POST.get("resolution_note", "Resolved & Closed by Officer").strip()[:240]
                tkt.save(update_fields=["status", "closed_at", "resolution_note"])
                action_notice = f"Incident {tkt.icn_code} closed and archived."
        elif act == "ASSIGN_STAFF_MODULES" and active_barangay and (request.user.is_superuser or (staff_profile and staff_profile.role == "CAPTAIN")):
            sp = BarangayStaffProfile.objects.filter(barangay=active_barangay, id=request.POST.get("staff_id")).first()
            if sp:
                picked = request.POST.getlist("assigned_modules")
                sp.allowed_modules = picked if picked else ["OVERVIEW"]
                sp.save(update_fields=["allowed_modules"])
                action_notice = f"Updated module access for {sp.full_name} ({sp.get_role_display()})."
        elif act == "ASSIGN_STAFF_MODULES" and active_barangay and (request.user.is_superuser or (staff_profile and staff_profile.role == "CAPTAIN")):
            sp = BarangayStaffProfile.objects.filter(barangay=active_barangay, id=request.POST.get("staff_id")).first()
            if sp:
                picked = request.POST.getlist("assigned_modules")
                sp.allowed_modules = picked if picked else ["OVERVIEW"]
                sp.save(update_fields=["allowed_modules"])
                action_notice = f"Updated module access for {sp.full_name} ({sp.get_role_display()})."
        elif act == "ISSUE_WALKIN_CERT" and active_barangay:
            import secrets
            q_ref = request.POST.get("citizen_ref", "").strip()
            cit = CitizenProfile.objects.filter(barangay=active_barangay).filter(Q(citizen_qr_id__iexact=q_ref) | Q(full_name__icontains=q_ref)).first()
            if not cit:
                action_notice = f"Resident not found for: {q_ref}. Verify 201 Master Record first."
            else:
                ctype = request.POST.get("cert_type", "BARANGAY_CLEARANCE")
                exempt = ctype in ("INDIGENCY", "FIRST_TIME_JOBSEEKER") or request.POST.get("fee_mode") == "EXEMPT"
                or_num = request.POST.get("official_receipt_number", "").strip()
                has_derog = BlotterCase.objects.filter(barangay=active_barangay, blocks_clearance=True, respondent_name__icontains=cit.last_name).exists()
                if has_derog and ctype in ("BARANGAY_CLEARANCE", "GOOD_MORAL", "BUSINESS_CLEARANCE"):
                    action_notice = f"DEROGATORY HOLD: {cit.full_name} has an active blocking Blotter/Lupon case. Clearance blocked."
                else:
                    st = "READY_TO_PRINT" if (exempt or or_num or not active_barangay.fee_collection_enabled) else "PENDING_OR"
                    c_new = CertificateRequest.objects.create(
                        barangay=active_barangay, citizen=cit,
                        control_number=f"CERT-{uuid.uuid4().hex[:6].upper()}-{secrets.token_hex(2).upper()}",
                        cert_type=ctype, purpose=request.POST.get("purpose", "General Requirement").strip(),
                        is_fee_exempt=exempt, fee_amount=0.00 if exempt else float(getattr(active_barangay, "default_clearance_fee", 50.00) if active_barangay.fee_collection_enabled else 0.00),
                        official_receipt_number=or_num, or_date=timezone.localdate() if or_num else None,
                        status=st
                    )
                    action_notice = f"Certificate {c_new.control_number} created for {cit.full_name} ({c_new.get_status_display()})."
        elif act == "UPDATE_SOCIAL_AID_STATUS" and active_barangay:
            sa_obj = SocialAidDistribution.objects.filter(barangay=active_barangay, id=request.POST.get("aid_id")).first()
            new_st = request.POST.get("new_status", "VERIFIED_ELIGIBLE")
            if sa_obj and new_st in ("VERIFIED_ELIGIBLE", "RELEASED_CLAIMED", "UNCLAIMED_RETURNED"):
                sa_obj.status = new_st
                sa_obj.released_by = actor_name
                if new_st == "RELEASED_CLAIMED":
                    sa_obj.released_date = timezone.localdate()
                sa_obj.save(update_fields=["status", "released_by", "released_date"])
                action_notice = f"Social Aid for {sa_obj.citizen.full_name} updated to {sa_obj.get_status_display()} — mirrored live to Citizen Portal."
        elif act == "ROUTE_CERT_FROM_SECRETARY" and active_barangay:
            c_obj = CertificateRequest.objects.filter(barangay=active_barangay, id=request.POST.get("cert_id")).first()
            if c_obj:
                has_derog = BlotterCase.objects.filter(barangay=active_barangay, blocks_clearance=True, respondent_name__icontains=c_obj.citizen.last_name).exists()
                if has_derog and c_obj.cert_type in ("BARANGAY_CLEARANCE", "GOOD_MORAL", "BUSINESS_CLEARANCE"):
                    c_obj.status = "REJECTED_HOLD"
                    c_obj.hold_or_delay_reason = "Active Derogatory / Lupon Record Hold"
                    c_obj.save(update_fields=["status", "hold_or_delay_reason"])
                    action_notice = f"DEROGATORY HOLD: {c_obj.control_number} placed on Hold due to active Blotter/Lupon record."
                else:
                    cid = request.POST.get("assigned_councilor_id", "").strip()
                    c_staff = BarangayStaffProfile.objects.filter(barangay=active_barangay, id=cid).first() if cid else None
                    c_obj.assigned_councilor = c_staff
                    try:
                        f_val = float(request.POST.get("fee_amount", c_obj.fee_amount) or 0)
                    except ValueError:
                        f_val = float(c_obj.fee_amount or 0)
                    if c_obj.is_fee_exempt or f_val <= 0:
                        c_obj.fee_amount = 0.00
                        c_obj.status = "PENDING_COUNCILOR"
                        nxt_lbl = f"Purok Councilor ({c_staff.full_name})" if c_staff else "Purok Councilor Approval Module"
                    else:
                        c_obj.fee_amount = f_val
                        c_obj.status = "PENDING_OR"
                        nxt_lbl = "Barangay Treasurer for OR Payment (auto-routes to Purok Councilor after OR)"
                    c_obj.save(update_fields=["assigned_councilor", "fee_amount", "status"])
                    action_notice = f"Certificate {c_obj.control_number} forwarded directly to {nxt_lbl}!"
        elif act == "TREASURER_APPROVE_OR_FORWARD" and active_barangay:
            c_obj = CertificateRequest.objects.filter(barangay=active_barangay, id=request.POST.get("cert_id")).first()
            or_no = request.POST.get("official_receipt_number", "").strip()
            if c_obj and or_no:
                c_obj.official_receipt_number = or_no
                c_obj.or_date = timezone.localdate()
                c_obj.status = "PENDING_COUNCILOR"
                c_obj.save(update_fields=["official_receipt_number", "or_date", "status"])
                c_lbl = c_obj.assigned_councilor.full_name if c_obj.assigned_councilor else "Assigned Purok Councilor"
                action_notice = f"OR #{or_no} approved for {c_obj.control_number}! Forwarded straight to {c_lbl} (no return to Secretary)."
        elif act == "COUNCILOR_ENDORSE_CERT" and active_barangay:
            c_obj = CertificateRequest.objects.filter(barangay=active_barangay, id=request.POST.get("cert_id")).first()
            if c_obj:
                c_obj.councilor_endorsed_by = actor_name
                c_obj.status = "PENDING_CAPTAIN"
                c_obj.save(update_fields=["councilor_endorsed_by", "status"])
                action_notice = f"Purok Councilor endorsement recorded for {c_obj.control_number}! Forwarded to Punong Barangay for Final Approval."
        elif act == "CAPTAIN_APPROVE_CERT" and active_barangay and (request.user.is_superuser or (staff_profile and staff_profile.role == "CAPTAIN")):
            c_obj = CertificateRequest.objects.filter(barangay=active_barangay, id=request.POST.get("cert_id")).first()
            if c_obj:
                c_obj.captain_approved_by = actor_name
                c_obj.signatory_name = active_barangay.get_active_signatory()
                c_obj.status = "READY_TO_PRINT"
                c_obj.save(update_fields=["captain_approved_by", "signatory_name", "status"])
                action_notice = f"Punong Barangay Final Approval granted for {c_obj.control_number}! Returned to Releasing Desk for Printing & Dry Seal."
                if getattr(c_obj.citizen, "email_address", ""):
                    try:
                        send_mail(subject=f"[{active_barangay.name}] Approved & Ready: {c_obj.get_cert_type_display()} ({c_obj.control_number})", message=f"Dear {c_obj.citizen.full_name},\n\nYour request for {c_obj.get_cert_type_display()} (Control No. {c_obj.control_number}) has received Final Approval from {c_obj.signatory_name} and is now ready for Dry Seal & Release at {active_barangay.name}.\n\nYou may also view/print your verified copy in your BIOAS Citizen Portal.\n\nThank you.", from_email=getattr(dj_settings, "DEFAULT_FROM_EMAIL", None), recipient_list=[c_obj.citizen.email_address], fail_silently=True)
                    except Exception:
                        pass
        elif act == "MARK_CERT_ISSUED" and active_barangay:
            c_obj = CertificateRequest.objects.filter(barangay=active_barangay, id=request.POST.get("cert_id")).first()
            if c_obj:
                c_obj.status = "ISSUED_PRINTED"
                c_obj.issued_date = timezone.localdate()
                c_obj.save(update_fields=["status", "issued_date"])
                action_notice = f"Certificate {c_obj.control_number} marked Issued & Released and mirrored to Citizen Portal."
        elif act == "RUN_IT_CONFIG_WIZARD" and active_barangay and (request.user.is_superuser or (staff_profile and staff_profile.role == "CAPTAIN")):
            from .models import TrustedLoginDevice, WalkInIncidentTicket
            sc = request.POST.get("it_scenario", "CHANGE_ISP")
            sp_id = request.POST.get("target_staff_id", "").strip()
            isp_note = request.POST.get("isp_or_pc_label", "").strip() or "Primary Barangay Workstation / ISP"
            sp_t = BarangayStaffProfile.objects.filter(barangay=active_barangay, id=sp_id).first() if sp_id else None
            purged = 0
            if sp_t and sp_t.user and sc in ("REPLACE_WORKSTATION", "EMERGENCY_LOCKOUT"):
                qs_d = TrustedLoginDevice.objects.filter(account_key=f"OFF:{sp_t.user.id}")
                purged = qs_d.count()
                qs_d.delete()
            rep_code = f"IT-{uuid.uuid4().hex[:6].upper()}"
            t_lbl = sp_t.full_name if sp_t else "All Barangay Workstations"
            summary_txt = f"Scenario: {sc} | Target: {t_lbl} | Note: {isp_note} | Revoked Old Tokens: {purged}"
            WalkInIncidentTicket.objects.create(barangay=active_barangay, icn_code=rep_code, category="IT_SYSTEM_CONFIG", description=summary_txt, created_by_name=actor_name, created_by_role=actor_role, status="CLOSED_ARCHIVED", resolution_note="Verified & Certified by IT/Admin Wizard", closed_at=timezone.now())
            request.session["bioas_it_report"] = {"code": rep_code, "scenario": sc, "target": t_lbl, "label": isp_note, "purged": purged, "by": actor_name, "at": timezone.localtime().strftime('%Y-%m-%d %I:%M %p'), "trusted_count": TrustedLoginDevice.objects.count()}
            action_notice = f"IT Configuration {rep_code} completed! Printable report ready below."
        elif act == "RUN_IT_CONFIG_WIZARD" and active_barangay and (request.user.is_superuser or (staff_profile and staff_profile.role == "CAPTAIN")):
            from .models import TrustedLoginDevice, WalkInIncidentTicket
            sc = request.POST.get("it_scenario", "CHANGE_ISP")
            sp_id = request.POST.get("target_staff_id", "").strip()
            isp_note = request.POST.get("isp_or_pc_label", "").strip() or "Primary Barangay Workstation / ISP"
            sp_t = BarangayStaffProfile.objects.filter(barangay=active_barangay, id=sp_id).first() if sp_id else None
            purged = 0
            if sp_t and sp_t.user and sc in ("REPLACE_WORKSTATION", "EMERGENCY_LOCKOUT"):
                qs_d = TrustedLoginDevice.objects.filter(account_key=f"OFF:{sp_t.user.id}")
                purged = qs_d.count()
                qs_d.delete()
            rep_code = f"IT-{uuid.uuid4().hex[:6].upper()}"
            t_lbl = sp_t.full_name if sp_t else "All Barangay Workstations"
            summary_txt = f"Scenario: {sc} | Target: {t_lbl} | Note: {isp_note} | Revoked Old Tokens: {purged}"
            WalkInIncidentTicket.objects.create(barangay=active_barangay, icn_code=rep_code, category="IT_SYSTEM_CONFIG", description=summary_txt, created_by_name=actor_name, created_by_role=actor_role, status="CLOSED_ARCHIVED", resolution_note="Verified & Certified by IT/Admin Wizard", closed_at=timezone.now())
            request.session["bioas_it_report"] = {"code": rep_code, "scenario": sc, "target": t_lbl, "label": isp_note, "purged": purged, "by": actor_name, "at": timezone.localtime().strftime("%Y-%m-%d %I:%M %p"), "trusted_count": TrustedLoginDevice.objects.count()}
            action_notice = f"IT Configuration {rep_code} completed! Printable report ready below."
        elif act == "UPDATE_SERVICE_TICKET" and active_barangay:
            from .models import CitizenServiceTicket
            stkt = CitizenServiceTicket.objects.filter(barangay=active_barangay, id=request.POST.get("ticket_id")).first()
            if stkt:
                stkt.status = request.POST.get("status", stkt.status)
                rep_txt = request.POST.get("office_reply", "").strip()
                if rep_txt:
                    stkt.office_reply = rep_txt
                stkt.handled_by = actor_name
                stkt.save(update_fields=["status", "office_reply", "handled_by", "updated_at"])
                action_notice = f"Ticket {stkt.ticket_code} updated ({stkt.get_status_display()}) and mirrored to Citizen Portal."
        elif act == "SAVE_CITIZEN_201":
            action_error = "Data Sovereignty Lock: Citizen 201 Master Files are owned and edited exclusively by the Citizen via their Citizen Portal."
        elif act == "DISABLED_SAVE_CITIZEN_201":
            edit_qr = request.POST.get("edit_qr_id", "").strip().upper()
            cit = CitizenProfile.objects.filter(barangay=active_barangay, citizen_qr_id=edit_qr).first() if edit_qr else None
            is_new = cit is None
            if is_new:
                from django.utils import timezone as dj_tz
                yr_now = dj_tz.now().year
                p_code = "".join(ch for ch in active_barangay.city_municipality.province.name.upper() if ch.isalpha())[:3] or "NUE"
                m_code = "".join(ch for ch in active_barangay.city_municipality.name.upper() if ch.isalpha())[:3] or "CAB"
                b_code = "".join(ch for ch in active_barangay.name.replace("Barangay", "").strip().upper() if ch.isalpha())[:3] or "LAG"
                seq_num = CitizenProfile.objects.filter(barangay=active_barangay).count() + 1
                gen_ref = f"{p_code}-{m_code}-{b_code}-{yr_now}-{seq_num:05d}"
                while CitizenProfile.objects.filter(citizen_qr_id=gen_ref).exists():
                    seq_num += 1
                    gen_ref = f"{p_code}-{m_code}-{b_code}-{yr_now}-{seq_num:05d}"
                cit = CitizenProfile(barangay=active_barangay, citizen_qr_id=gen_ref)
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

            cit.alias_nickname = request.POST.get("alias_nickname", "").strip()
            cit.data_privacy_consent = True
            cit.gender_identity = request.POST.get("gender_identity", cit.sex)
            cit.religion = request.POST.get("religion", "").strip()
            cit.blood_type = request.POST.get("blood_type", "").strip()
            cit.height = request.POST.get("height", "").strip()
            cit.weight = request.POST.get("weight", "").strip()
            cit.complexion = request.POST.get("complexion", "").strip()
            cit.current_address = request.POST.get("current_address", "").strip() or cit.address_line
            cit.father_name = request.POST.get("father_name", "").strip()
            cit.mother_maiden_name = request.POST.get("mother_maiden_name", "").strip()
            cit.spouse_name = request.POST.get("spouse_name", "").strip()
            try:
                cit.years_in_barangay = max(0, int(request.POST.get("years_in_barangay", 1) or 1))
            except ValueError:
                pass
            from django.contrib.auth.hashers import make_password
            w_uname = request.POST.get("portal_username", "").strip().lower()
            w_temp_pw = (request.POST.get("portal_password") or request.POST.get("temp_password") or "").strip()
            if is_new and not w_uname:
                base_u = "".join(c for c in cit.last_name.lower() if c.isalnum()) or "resident"
                w_uname = f"{base_u}{cit.id or CitizenProfile.objects.count()+1}"
            if w_uname and not CitizenProfile.objects.exclude(id=cit.id).filter(portal_username__iexact=w_uname).exists():
                cit.portal_username = w_uname
            if is_new and not w_temp_pw:
                w_temp_pw = f"Bioas@{uuid.uuid4().hex[:5].upper()}"
            if w_temp_pw:
                cit.portal_password_hash = make_password(w_temp_pw)
            cit.save()
            from citizens.views import save_standardized_citizen_files
            save_standardized_citizen_files(
                cit,
                photo_file=request.FILES.get("photo"),
                doc_files=request.FILES.getlist("supporting_document"),
                source_channel="WALKIN_DESK",
                uploaded_by=actor_name,
            )
            if is_new and cit.email_address and w_temp_pw:
                try:
                    from django.core.mail import send_mail
                    from django.conf import settings as dj_settings
                    login_link = request.build_absolute_uri("/login/?role=CITIZEN")
                    send_mail(
                        subject=f"[{active_barangay.name}] Walk-In 201 Registration & Portal Account - {cit.citizen_qr_id}",
                        message=(
                            f"Good day {cit.full_name},\n\n"
                            f"Your Walk-In Barangay 201 Citizen Registration at {active_barangay.name} has been encoded and activated.\n\n"
                            f"Citizen Unique Reference ID : {cit.citizen_qr_id}\n"
                            f"Portal Sign-In Username     : {cit.portal_username}\n"
                            f"Temporary Portal Password   : {w_temp_pw}\n"
                            f"Unified Citizen Sign-In URL : {login_link}\n\n"
                            f"Please sign in and update your password under Account & Theme Settings."
                        ),
                        from_email=getattr(dj_settings, "DEFAULT_FROM_EMAIL", None),
                        recipient_list=[cit.email_address],
                        fail_silently=True,
                    )
                except Exception:
                    pass
            SystemAuditLog.objects.create(
                barangay=active_barangay,
                action_type="PORTAL_SYNC_APPROVED",
                actor_name=actor_name,
                actor_role=actor_role,
                reference_code=cit.citizen_qr_id,
                details=f"{'Encoded walk-in' if is_new else 'Updated'} 201 Master Record for {cit.full_name} ({cit.citizen_qr_id}).",
            )
            cred_note = f" | Portal Username: {cit.portal_username} | Temp Password: {w_temp_pw}" if (is_new and w_temp_pw) else ""
            action_notice = f"{'Encoded new' if is_new else 'Updated'} 201 Master Record: {cit.full_name} ({cit.citizen_qr_id}){cred_note}"
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
                    if not cit.portal_username or not cit.portal_password_hash:
                        import random, secrets
                        from django.contrib.auth.hashers import make_password
                        from django.core.mail import send_mail
                        from django.conf import settings as dj_settings
                        t_pw = f"Bioas@{secrets.randbelow(9000)+1000}!"
                        t_otp = f"{random.randint(100000, 999999)}"
                        cit.portal_username = cit.portal_username or cit.citizen_qr_id.lower()
                        cit.portal_password_hash = make_password(t_pw)
                        cit.save(update_fields=["portal_username", "portal_password_hash"])
                        if cit.email_address:
                            try:
                                send_mail(
                                    subject=f"[{active_barangay.name}] Staged 201 Portal Credentials & Initial OTP - {cit.citizen_qr_id}",
                                    message=f"Good day {cit.full_name},\n\nYour 201 record has been staged for Barangay verification.\nReference Citizen ID : {cit.citizen_qr_id}\nPortal Username      : {cit.portal_username}\nTemporary Password   : {t_pw}\n6-Digit Initial OTP  : {t_otp}\n\nYou will receive an activation notice once approved by the Barangay Secretary.",
                                    from_email=getattr(dj_settings, "DEFAULT_FROM_EMAIL", None),
                                    recipient_list=[cit.email_address],
                                    fail_silently=True,
                                )
                            except Exception:
                                pass
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
            import random, secrets
            from django.contrib.auth.hashers import make_password
            from django.core.mail import send_mail
            from django.conf import settings as dj_settings
            selected_ids = request.POST.getlist("pending_ids")
            qs_pend = CitizenProfile.objects.filter(barangay=active_barangay, status="PENDING_APPROVAL")
            if selected_ids:
                qs_pend = qs_pend.filter(id__in=selected_ids)
            login_link = request.build_absolute_uri("/login/?role=CITIZEN")
            approved_total, emailed_total = 0, 0
            for c_item in qs_pend:
                upd = ["status"]
                c_item.status = "ACTIVE_RESIDENT"
                extra_cred = ""
                if not c_item.portal_username:
                    c_item.portal_username = c_item.citizen_qr_id.lower()
                    upd.append("portal_username")
                if not c_item.portal_password_hash:
                    t_pw = f"Bioas@{secrets.randbelow(9000)+1000}!"
                    c_item.portal_password_hash = make_password(t_pw)
                    upd.append("portal_password_hash")
                    extra_cred = f"Temporary Password   : {t_pw}\nInitial 6-Digit OTP  : {random.randint(100000, 999999)}\n"
                c_item.save(update_fields=upd)
                approved_total += 1
                if c_item.email_address:
                    try:
                        send_mail(
                            subject=f"[{active_barangay.name}] Official 201 Account Approved & Activated - {c_item.citizen_qr_id}",
                            message=f"Good day {c_item.full_name},\n\nYour Barangay 201 Citizen Registration has been officially APPROVED by {active_barangay.name}.\n\nReference Citizen ID : {c_item.citizen_qr_id}\nPortal Username      : {c_item.portal_username}\n{extra_cred}Resident Portal Link : {login_link}\n\nPlease sign in at {login_link} to complete your remaining 201 profile details.\n\nRespectfully,\nOffice of the Barangay Secretary\n{active_barangay.name}",
                            from_email=getattr(dj_settings, "DEFAULT_FROM_EMAIL", None),
                            recipient_list=[c_item.email_address],
                            fail_silently=True,
                        )
                        emailed_total += 1
                    except Exception:
                        pass
            if approved_total > 0:
                SystemAuditLog.objects.create(
                    barangay=active_barangay,
                    action_type="PORTAL_SYNC_APPROVED",
                    actor_name=actor_name,
                    actor_role=actor_role,
                    reference_code=f"MASS-201-{approved_total}",
                    details=f"Verified and mass-approved {approved_total} pending citizen record(s) into 201 Master; emailed {emailed_total} activation notice(s).",
                )
                action_notice = f"Verified & activated {approved_total} citizen record(s) into 201 Master and emailed {emailed_total} activation credential notice(s)!"
            else:
                action_notice = "No pending citizen records were selected for approval."
        elif act == "MASS_REJECT_INDIVIDUAL":
            from django.core.mail import send_mail
            from django.conf import settings as dj_settings
            selected_ids = request.POST.getlist("pending_ids")
            qs_rej = CitizenProfile.objects.filter(barangay=active_barangay, status="PENDING_APPROVAL", id__in=selected_ids)
            login_link = request.build_absolute_uri("/login/?role=CITIZEN")
            rej_total = 0
            for c_item in qs_rej:
                indiv_note = (request.POST.get(f"remark_{c_item.id}") or "").strip() or "Incomplete or unverified supporting documents."
                c_item.status = "REJECTED_RETURNED"
                c_item.rejection_reason = indiv_note
                c_item.save(update_fields=["status", "rejection_reason", "updated_at"])
                rej_total += 1
                if c_item.email_address:
                    try:
                        send_mail(
                            subject=f"[{active_barangay.name}] 201 Registration Returned for Revision - {c_item.citizen_qr_id}",
                            message=f"Good day {c_item.full_name},\n\nYour Barangay 201 registration ({c_item.citizen_qr_id}) was returned for revision.\nIndividual Remarks: {indiv_note}\n\nPlease sign in at {login_link} using your Portal Username ({c_item.portal_username or c_item.citizen_qr_id.lower()}) to update your details or documents and resubmit.\n\n-- {active_barangay.name} Office of the Barangay Secretary",
                            from_email=getattr(dj_settings, "DEFAULT_FROM_EMAIL", None),
                            recipient_list=[c_item.email_address],
                            fail_silently=True,
                        )
                    except Exception:
                        pass
            if rej_total > 0:
                SystemAuditLog.objects.create(barangay=active_barangay, action_type="PORTAL_SYNC_APPROVED", actor_name=actor_name, actor_role=actor_role, reference_code=f"REJ-201-{rej_total}", details=f"Returned {rej_total} citizen application(s) with individual per-resident remarks.")
                action_notice = f"Returned {rej_total} citizen application(s) with individual remarks and sent individualized emails!"
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
        elif act == "APPROVE_WALKIN_RECOVERY":
            from .models import WalkInRecoveryRequest
            if request.user.is_superuser or (staff_profile and staff_profile.role == "CAPTAIN"):
                req_obj = WalkInRecoveryRequest.objects.select_related("citizen").filter(id=request.POST.get("recovery_id"), barangay=active_barangay, status="PENDING_CAPTAIN").first()
                if req_obj:
                    cit = req_obj.citizen
                    cit.portal_username = req_obj.requested_username
                    cit.portal_password_hash = req_obj.pending_password_hash
                    cit.save(update_fields=["portal_username", "portal_password_hash"])
                    req_obj.status = "APPROVED"
                    req_obj.reviewed_by_name = actor_name
                    req_obj.save(update_fields=["status", "reviewed_by_name"])
                    SystemAuditLog.objects.create(barangay=active_barangay, action_type="PORTAL_SYNC_APPROVED", actor_name=actor_name, actor_role=actor_role, reference_code=cit.citizen_qr_id, details=f"Punong Barangay approved Walk-In Account Recovery for {cit.full_name} ({cit.citizen_qr_id}). Activated username: {cit.portal_username}.")
                    action_notice = f"Approved Walk-In Account Recovery for {cit.full_name} ({cit.citizen_qr_id})! New credentials are now active."
        elif act == "REJECT_WALKIN_RECOVERY":
            from .models import WalkInRecoveryRequest
            if request.user.is_superuser or (staff_profile and staff_profile.role == "CAPTAIN"):
                req_obj = WalkInRecoveryRequest.objects.select_related("citizen").filter(id=request.POST.get("recovery_id"), barangay=active_barangay, status="PENDING_CAPTAIN").first()
                if req_obj:
                    req_obj.status = "REJECTED"
                    req_obj.reviewed_by_name = actor_name
                    req_obj.save(update_fields=["status", "reviewed_by_name"])
                    action_notice = f"Rejected Walk-In Account Recovery request for {req_obj.citizen.full_name}."
        elif act == "SAVE_FORM_TEMPLATE":
            from .models import OfficialFormTemplate
            import base64
            tpl_id = request.POST.get("template_id")
            obj = OfficialFormTemplate.objects.filter(id=tpl_id, barangay=active_barangay).first() if tpl_id else OfficialFormTemplate(barangay=active_barangay)
            if obj:
                obj.category = request.POST.get("category", "COMPLETION_REPORT")
                obj.title = request.POST.get("title", "").strip() or "Official Barangay Form"
                obj.form_code = request.POST.get("form_code", "").strip()
                obj.description = request.POST.get("description", "").strip()
                obj.body_template = request.POST.get("body_template", "").strip()
                obj.updated_by = actor_name
                if request.POST.get("clear_existing_file") == "1":
                    obj.file_data_uri = ""
                    obj.file_name = ""
                up_f = request.FILES.get("template_file")
                if up_f:
                    ext = ("." + up_f.name.rsplit(".", 1)[-1].lower()) if "." in up_f.name else ""
                    if ext not in (".doc", ".docx", ".xls", ".xlsx", ".csv"):
                        action_notice = "Upload blocked: Only editable MS Word (.doc, .docx) or MS Excel (.xls, .xlsx) files are allowed."
                        request.session["bioas_flash_notice"] = action_notice
                        return redirect(request.get_full_path())
                    b64 = base64.b64encode(up_f.read()).decode("ascii")
                    obj.file_data_uri = f"data:{up_f.content_type or 'application/octet-stream'};base64,{b64}"
                    obj.file_name = up_f.name[:150]
                if obj.category == "DATA_PRIVACY_POLICY":
                    if not obj.pk:
                        obj.save()
                    obj.has_pending_approval = True
                    obj.pending_title = request.POST.get("title", "").strip() or obj.title
                    obj.pending_body_template = request.POST.get("body_template", "").strip()
                    obj.pending_submitted_by = actor_name
                    obj.save()
                    SystemAuditLog.objects.create(barangay=active_barangay, action_type="PORTAL_SYNC_APPROVED", actor_name=actor_name, actor_role=actor_role, reference_code=obj.form_code or "BIOAS-PRIV-01", details=f"Submitted proposed revision to Barangay Data Privacy Policy & Terms of Use -> Pending Punong Barangay Approval.")
                    action_notice = "Subject for Punong Barangay (Captain) Approval: Proposed changes to the Barangay Data Privacy Policy & Terms of Use have been queued for Captain sign-off before going live."
                else:
                    obj.save()
                    action_notice = f"Acknowledgement: Official Form Template '{obj.title}' has been successfully saved and replaced!"
        elif act == "APPROVE_POLICY_TEMPLATE":
            from .models import OfficialFormTemplate
            if request.user.is_superuser or (staff_profile and staff_profile.role == "CAPTAIN"):
                pol_obj = OfficialFormTemplate.objects.filter(id=request.POST.get("template_id"), barangay=active_barangay, has_pending_approval=True).first()
                if pol_obj:
                    pol_obj.title = pol_obj.pending_title or pol_obj.title
                    pol_obj.body_template = pol_obj.pending_body_template or pol_obj.body_template
                    pol_obj.has_pending_approval = False
                    pol_obj.pending_title = ""
                    pol_obj.pending_body_template = ""
                    pol_obj.updated_by = actor_name
                    pol_obj.save()
                    SystemAuditLog.objects.create(barangay=active_barangay, action_type="PORTAL_SYNC_APPROVED", actor_name=actor_name, actor_role=actor_role, reference_code=pol_obj.form_code or "BIOAS-PRIV-01", details=f"Punong Barangay approved & published updated Barangay Data Privacy Policy & Terms of Use.")
                    action_notice = "Approved & Published: Updated Barangay Data Privacy Policy & Terms of Use (RA 10173) is now live on the Citizen Sign-Up portal!"
        elif act == "POST_BLAST_ADVISORY":
            from .models import BarangayBlastAdvisory
            from django.core.mail import send_mail
            from django.conf import settings as dj_settings
            b_title = request.POST.get("blast_title", "").strip()
            b_msg = request.POST.get("blast_message", "").strip()
            b_cat = request.POST.get("blast_category", "GENERAL_ADVISORY")
            b_purok = request.POST.get("target_purok", "ALL").strip() or "ALL"
            b_urg = bool(request.POST.get("is_urgent"))
            if active_barangay and b_title and b_msg:
                import base64
                b_photo_uri = ""
                pf = request.FILES.get("blast_photo")
                if pf:
                    b_photo_uri = f"data:{pf.content_type or 'image/jpeg'};base64," + base64.b64encode(pf.read()).decode("ascii")
                adv = BarangayBlastAdvisory.objects.create(
                    barangay=active_barangay,
                    category=b_cat,
                    title=b_title,
                    message=b_msg,
                    target_purok=b_purok,
                    is_urgent=b_urg,
                    photo_data_uri=b_photo_uri,
                    posted_by_name=actor_name,
                    posted_by_role=actor_role,
                )
                emailed_n = 0
                if request.POST.get("send_email_blast"):
                    qs_em = CitizenProfile.objects.filter(barangay=active_barangay, status="ACTIVE_RESIDENT").exclude(email_address="")
                    if b_purok != "ALL":
                        qs_em = qs_em.filter(purok__iexact=b_purok)
                    recips = list(qs_em.values_list("email_address", flat=True).distinct())
                    if recips:
                        try:
                            send_mail(
                                subject=f"[{active_barangay.name}] {adv.get_category_display()}: {b_title}",
                                message=f"OFFICIAL BARANGAY ADVISORY ({active_barangay.name})\nCategory: {adv.get_category_display()}\nAudience: {b_purok}\n\n{b_msg}\n\nIssued By: {actor_name} ({actor_role})",
                                from_email=getattr(dj_settings, "DEFAULT_FROM_EMAIL", None),
                                recipient_list=recips,
                                fail_silently=True,
                            )
                            emailed_n = len(recips)
                        except Exception:
                            pass
                SystemAuditLog.objects.create(barangay=active_barangay, action_type="PORTAL_SYNC_APPROVED", actor_name=actor_name, actor_role=actor_role, reference_code=f"BLAST-{adv.id}", details=f"Broadcasted '{b_title}' ({adv.get_category_display()}) to {b_purok}; emailed {emailed_n} resident(s).")
                action_notice = f"Broadcasted Official Advisory '{b_title}' to all Citizen Dashboards ({b_purok}) and emailed {emailed_n} resident(s)!"
        elif act == "REJECT_POLICY_TEMPLATE":
            from .models import OfficialFormTemplate
            if request.user.is_superuser or (staff_profile and staff_profile.role == "CAPTAIN"):
                pol_obj = OfficialFormTemplate.objects.filter(id=request.POST.get("template_id"), barangay=active_barangay, has_pending_approval=True).first()
                if pol_obj:
                    pol_obj.has_pending_approval = False
                    pol_obj.pending_title = ""
                    pol_obj.pending_body_template = ""
                    pol_obj.save()
                    action_notice = "Rejected proposed revision to Barangay Data Privacy Policy; active policy remains unchanged."
        if action_notice:
            request.session["bioas_flash_notice"] = action_notice
        return redirect(request.get_full_path())


    theme = active_barangay.get_active_theme() if active_barangay else {
        "title": "BIOAS Command Portal", "banner_text": "Philippine Barangay Information & Operations System",
        "primary_color": "#1E3A8A", "secondary_color": "#F59E0B", "is_occasion": False,
    }

    from citizens.models import CitizenSupportingDocument
    citizens = CitizenProfile.objects.select_related("household").defer("supporting_doc_data_uri").filter(barangay=active_barangay) if active_barangay else CitizenProfile.objects.none()
    pending_photo_citizens = list(CitizenProfile.objects.filter(barangay=active_barangay, photo_review_status="PENDING").exclude(pending_photo_data_uri="")) if active_barangay else []
    all_repo_docs = CitizenSupportingDocument.objects.select_related("citizen").defer("file_data_uri", "citizen__supporting_doc_data_uri", "citizen__pending_photo_data_uri").filter(citizen__barangay=active_barangay) if active_barangay else CitizenSupportingDocument.objects.none()
    _src_map = {"PORTAL_SIGNUP": "Online Citizen Portal Sign-Up", "SELF_PORTAL": "Online Citizen Self-Portal", "WALKIN_DESK": "Barangay Hall Walk-In / Desk Encoding", "CERTIFICATE_REQ": "Certificate Attachment", "STAFF_REPOSITORY": "Direct Staff Repository Upload"}
    _vmap = {}
    for _d in all_repo_docs:
        _cid = _d.citizen_id
        _lbl = _src_map.get(_d.source_channel, _d.get_source_channel_display() or "Online Citizen Self-Portal")
        if _cid not in _vmap:
            _vmap[_cid] = {"citizen": _d.citizen, "latest_at": _d.uploaded_at, "latest_channel": _lbl, "latest_code": ("PORTAL_SIGNUP" if _d.source_channel == "SELF_PORTAL" else _d.source_channel), "latest_by": _d.uploaded_by or _d.citizen.full_name, "titles": [_d.document_title], "count": 1}
        else:
            _vmap[_cid]["count"] += 1
            if _d.document_title not in _vmap[_cid]["titles"]:
                _vmap[_cid]["titles"].append(_d.document_title)
    unified_citizen_vaults = list(_vmap.values())
    households = Household.objects.prefetch_related("members").filter(barangay=active_barangay) if active_barangay else Household.objects.none()
    citizen_reports = CitizenCommunityReport.objects.filter(barangay=active_barangay) if active_barangay else CitizenCommunityReport.objects.none()
    councilor_staff_list = list(BarangayStaffProfile.objects.filter(barangay=active_barangay, role="COUNCILOR", approval_status="ACTIVE").order_by("full_name")) if active_barangay else []
    certificates = list(CertificateRequest.objects.select_related("citizen", "assigned_councilor").filter(barangay=active_barangay)[:60]) if active_barangay else []
    for _c in certificates:
        _p = (_c.citizen.purok or "").strip().lower()
        _det = _c.assigned_councilor
        if not _det and _p:
            for _sp in councilor_staff_list:
                if _p in (_sp.assigned_purok or "").lower() or _p in (_sp.committee_assignment or "").lower():
                    _det = _sp
                    break
        if not _det and councilor_staff_list:
            _det = councilor_staff_list
        _c.detected_councilor = _det
    pending_or_certs = [c for c in certificates if c.status == "PENDING_OR"]
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
    if active_barangay:
        CitizenProfile.objects.filter(barangay=active_barangay, purok__iexact="Puro VI").update(purok="Purok VI")
        CitizenProfile.objects.filter(barangay=active_barangay, purok__iexact="Purok VII").update(purok="Purok VI")
        for _ac in active_citizens:
            if (_ac.purok or "").strip().lower() in ("puro vi", "purok vii"):
                _ac.purok = "Purok VI"
    purok_names = ["Purok I", "Purok II", "Purok III", "Purok IV", "Purok V", "Purok VI"]
    for c in active_citizens:
        _pn = (c.purok or "").strip()
        if _pn and _pn not in purok_names:
            purok_names.append(_pn)
    purok_rows = [{"name": p, "count": sum(1 for c in active_citizens if (c.purok or "Purok I") == p)} for p in purok_names]

    import json as _json
    import json as _json
    children_list = [c for c in active_citizens if c.relationship_to_head == 'CHILD' or c.age < 18]
    _tot_res = len(active_citizens)
    _hh_ids = set(c.household_id for c in active_citizens if c.household_id)
    _hh_count = max(len(_hh_ids), households.count() if hasattr(households, 'count') else len(households))
    _avg_hh = round(_tot_res / _hh_count, 2) if _hh_count else 0.0
    _cb = {}
    for _sp in councilor_staff_list:
        for _pk in purok_names:
            if _pk.lower() in (_sp.assigned_purok or '').lower() or _pk.lower() in (_sp.committee_assignment or '').lower(): _cb.setdefault(_pk, f'Hon. {_sp.full_name}')
    purok_rows = []
    for p in purok_names:
        _pm = [c for c in active_citizens if (c.purok or 'Purok I') == p]
        _phh = len(set(c.household_id for c in _pm if c.household_id))
        _pv = sum(1 for c in _pm if c.is_registered_voter)
        _psp = sum(1 for c in _pm if c.is_senior_citizen or c.age >= 60 or c.is_pwd)
        _pi = sum(1 for c in _pm if getattr(c, 'socioeconomic_tier', '') in ('SUBSISTENCE', 'LOW_INCOME') or getattr(c, 'is_4ps_beneficiary', False))
        purok_rows.append({'name': p, 'councilor': _cb.get(p, 'Unassigned (Set in Staff)'), 'households': _phh, 'count': len(_pm), 'voters': _pv, 'sen_pwd': _psp, 'indigent': _pi, 'pct': round((len(_pm)/_tot_res)*100, 1) if _tot_res else 0.0})
    _emp = sum(1 for c in active_citizens if (c.occupation or '').strip() and (c.occupation or '').strip().lower() not in ('none','unemployed','student','n/a','not declared'))
    _stu = sum(1 for c in active_citizens if getattr(c, 'currently_attending_school', False) or 'student' in (c.occupation or '').lower())
    _unemp = sum(1 for c in active_citizens if 15 <= c.age <= 64 and not getattr(c, 'currently_attending_school', False) and (not (c.occupation or '').strip() or (c.occupation or '').strip().lower() in ('none','unemployed','n/a','not declared')))
    _osy = sum(1 for c in active_citizens if 15 <= c.age <= 30 and not getattr(c, 'currently_attending_school', False) and (not (c.occupation or '').strip() or (c.occupation or '').strip().lower() in ('none','unemployed','n/a','not declared')))
    _ind = sum(1 for c in active_citizens if getattr(c, 'socioeconomic_tier', '') in ('SUBSISTENCE','LOW_INCOME') or getattr(c, 'is_4ps_beneficiary', False))
    _fps = sum(1 for c in active_citizens if getattr(c, 'is_4ps_beneficiary', False))
    _sk = sum(1 for c in active_citizens if 15 <= c.age <= 30)
    pop_citizens_json = _json.dumps([{'id':c.id,'qr':c.citizen_qr_id,'name':c.full_name,'purok':c.purok or 'Purok I','sex':c.sex,'age':c.age,'voter':bool(c.is_registered_voter),'senior':bool(c.is_senior_citizen or c.age>=60),'pwd':bool(c.is_pwd),'solo':bool(c.is_solo_parent),'pregnant':bool(c.is_pregnant),'indigent':bool(getattr(c,'socioeconomic_tier','') in ('SUBSISTENCE','LOW_INCOME') or getattr(c,'is_4ps_beneficiary',False)),'four_ps':bool(getattr(c,'is_4ps_beneficiary',False)),'civil':c.civil_status,'residency':c.residency_status,'hh':c.household_id or 0,'occ':(c.occupation or '').strip(),'school':bool(getattr(c,'currently_attending_school',False)),'portal':bool(c.portal_username),'philsys':bool(c.philsys_id),'mobile':bool(c.mobile_number)} for c in active_citizens])
    pop_stats = {'total_residents':_tot_res,'household_count':_hh_count,'avg_hh_size':_avg_hh,'male_count':sum(1 for c in active_citizens if c.sex=='MALE'),'female_count':sum(1 for c in active_citizens if c.sex=='FEMALE'),'registered_voters':sum(1 for c in active_citizens if c.is_registered_voter),'non_voters':sum(1 for c in active_citizens if not c.is_registered_voter),'indigent_count':_ind,'four_ps_count':_fps,'sk_youth_count':_sk,'employed_count':_emp,'unemployed_count':_unemp,'student_count':_stu,'osy_count':_osy,'age_0_4':sum(1 for c in active_citizens if 0<=c.age<=4),'age_5_14':sum(1 for c in active_citizens if 5<=c.age<=14),'age_15_30':_sk,'age_31_59':sum(1 for c in active_citizens if 31<=c.age<=59),'age_60_plus':sum(1 for c in active_citizens if c.age>=60),'purok_rows':purok_rows,'children_total':len(children_list),'single_count':sum(1 for c in active_citizens if c.civil_status=='SINGLE'),'married_count':sum(1 for c in active_citizens if c.civil_status=='MARRIED'),'widowed_count':sum(1 for c in active_citizens if c.civil_status=='WIDOWED'),'separated_count':sum(1 for c in active_citizens if c.civil_status=='SEPARATED'),'res_permanent':sum(1 for c in active_citizens if c.residency_status=='PERMANENT'),'res_renter':sum(1 for c in active_citizens if c.residency_status=='RENTER'),'res_sharer':sum(1 for c in active_citizens if c.residency_status=='SHARER'),'res_transient':sum(1 for c in active_citizens if c.residency_status=='TRANSIENT'),'portal_activated':sum(1 for c in active_citizens if c.portal_username),'walkin_only':sum(1 for c in active_citizens if not c.portal_username),'missing_philsys':sum(1 for c in active_citizens if not c.philsys_id),'missing_mobile':sum(1 for c in active_citizens if not c.mobile_number),'unmarried_children':sum(1 for c in children_list if c.civil_status=='SINGLE'),'married_children':sum(1 for c in children_list if c.civil_status=='MARRIED'),'senior_count':sum(1 for c in active_citizens if c.is_senior_citizen or c.age>=60),'pwd_count':sum(1 for c in active_citizens if c.is_pwd),'solo_parent_count':sum(1 for c in active_citizens if c.is_solo_parent),'pregnant_count':sum(1 for c in active_citizens if c.is_pregnant),'recent_births_count':sum(1 for c in active_citizens if c.age==0 or (c.birth_registered_date and c.birth_registered_date>=one_year_ago)),'deaths_count':citizens.filter(status='DECEASED').count(),'pop_citizens_json':pop_citizens_json}
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
        "pending_or_certs": len(pending_or_certs),
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

    if active_barangay:
        from .models import OfficialFormTemplate
        if not OfficialFormTemplate.objects.filter(barangay=active_barangay, category="DATA_PRIVACY_POLICY").exists():
            OfficialFormTemplate.objects.create(
                barangay=active_barangay,
                category="DATA_PRIVACY_POLICY",
                form_code="BIOAS-PRIV-01",
                title="Barangay Data Privacy Policy & Terms of Use (RA 10173)",
                description="Displayed in the Citizen Sign-Up consent pop-up window (Requires Captain approval to modify).",
                body_template="REPUBLIC OF THE PHILIPPINES\nBARANGAY " + active_barangay.name.upper() + "\n\nDATA PRIVACY NOTICE & BARANGAY PURPOSE (RA 10173)\n\n1. Purpose of Collection: Your personal information, 2x2 photo, and supporting residency documents are collected exclusively for maintaining the official Registry of Barangay Inhabitants (RBI / 201 Master File), issuing Barangay Clearances/Certificates, health & social welfare delivery, and disaster response.\n2. Data Protection & Access: Records are protected under the Data Privacy Act of 2012 (RA 10173) and accessible only to authorized Barangay Officials.\n3. Resident Declaration: I certify that all information and documents submitted are true, accurate, and genuine.",
                updated_by="System Default",
            )
        if not OfficialFormTemplate.objects.filter(barangay=active_barangay).exclude(category="DATA_PRIVACY_POLICY").exists():
            for cat, code, ttl, desc, body in [
                ("COMPLETION_REPORT", "BIOAS-FRM-01", "Certificate of Project / Work Completion Report", "Official Barangay engineering & infrastructure project completion sign-off form.", "REPUBLIC OF THE PHILIPPINES\nBARANGAY " + active_barangay.name.upper() + "\n\nCERTIFICATE OF COMPLETION REPORT\nProject Title: ___________________________\nLocation / Purok: ________________________\nContractor / Implementing Unit: __________\nDate Completed: __________________________\n\nCertified Correct:\nBarangay Secretary / Project Engineer\n\nApproved By:\nPunong Barangay"),
                ("ACCEPTANCE_REPORT", "BIOAS-FRM-02", "Inspection & Final Acceptance Report (IAR)", "COA-compliant property, equipment, and project final acceptance form.", "REPUBLIC OF THE PHILIPPINES\nBARANGAY " + active_barangay.name.upper() + "\n\nFINAL ACCEPTANCE REPORT\nPO / Work Order No.: ____________________\nSupplier / Contractor: ___________________\nTotal Contract Amount: ___________________\nCondition Upon Acceptance: [ ] Complete & Functional\n\nAccepted By:\nProperty Custodian / Barangay Treasurer\n\nNoted By:\nPunong Barangay"),
                ("INSPECTION_REPORT", "BIOAS-FRM-03", "Pre-Repair / Site & Equipment Inspection Report", "Field inspection checklist prior to work order issuance or liquidation.", "REPUBLIC OF THE PHILIPPINES\nBARANGAY " + active_barangay.name.upper() + "\n\nTECHNICAL INSPECTION REPORT\nAsset / Facility Inspected: ______________\nFindings / Defects Observed: _____________\nRecommended Action: ______________________\n\nInspected By: ____________________________\nDate: ____________________________________"),
                ("ASSET_PROFILE", "BIOAS-FRM-04", "Barangay Property & Asset Profile Sheet", "Individual accountability & lifecycle registry profile for LGU assets and vehicles.", "REPUBLIC OF THE PHILIPPINES\nBARANGAY " + active_barangay.name.upper() + "\n\nOFFICIAL ASSET PROFILE RECORD\nAsset Tag / Plate No.: ___________________\nItem Description & Serial No.: ___________\nAcquisition Date & Cost: _________________\nAssigned Accountable Officer: ____________\nCurrent Condition: _______________________"),
                ("WORK_ORDER", "BIOAS-FRM-05", "Barangay Maintenance & Dispatch Work Order", "Official job order for utility, tanod, engineering, or equipment repairs.", "REPUBLIC OF THE PHILIPPINES\nBARANGAY " + active_barangay.name.upper() + "\n\nOFFICIAL BARANGAY WORK ORDER\nWork Order No.: __________________________\nRequested By / Purok: ____________________\nScope of Work: ___________________________\nTarget Completion Date: __________________\n\nIssued By: Barangay Secretary\nApproved By: Punong Barangay"),
                ("WALKIN_RECOVERY_LETTER", "BIOAS-FRM-06", "Sworn Walk-In Account Recovery Request Letter", "Mandatory signed request letter for residents requesting manual credential reset.", "REPUBLIC OF THE PHILIPPINES\nBARANGAY " + active_barangay.name.upper() + "\n\nREQUEST FOR WALK-IN PORTAL ACCOUNT RECOVERY\nDate: ____________________________________\n\nTo: The Punong Barangay\nThru: Office of the Barangay Secretary\n\nI, __________________________, of legal age, resident of Purok _____, with Citizen Reference ID __________________, respectfully request manual reset of my BIOAS Resident Portal credentials due to loss of access to my registered email/device. Attached is a photocopy of my valid government ID.\n\n______________________________\nSignature Over Printed Name of Resident"),
            ]:
                OfficialFormTemplate.objects.create(barangay=active_barangay, category=cat, form_code=code, title=ttl, description=desc, body_template=body, updated_by="System Default")
        if not OfficialFormTemplate.objects.filter(barangay=active_barangay, category="DATA_PRIVACY_POLICY").exists():
            OfficialFormTemplate.objects.create(
                barangay=active_barangay,
                category="DATA_PRIVACY_POLICY",
                form_code="BIOAS-PRIV-01",
                title="Barangay Data Privacy Policy & Terms of Use (RA 10173)",
                description="Displayed in the Citizen Sign-Up consent pop-up window.",
                body_template="REPUBLIC OF THE PHILIPPINES\nBARANGAY " + active_barangay.name.upper() + "\n\nDATA PRIVACY NOTICE & BARANGAY PURPOSE (RA 10173)\n\n1. Purpose of Collection: Your personal information, 2x2 photo, and supporting residency documents are collected exclusively for maintaining the official Registry of Barangay Inhabitants (RBI / 201 Master File), issuing Barangay Clearances/Certificates, health & social welfare delivery, and disaster response.\n2. Data Protection & Access: Records are protected under the Data Privacy Act of 2012 (RA 10173) and accessible only to authorized Barangay Officials.\n3. Resident Declaration: I certify that all information and documents submitted are true, accurate, and genuine.",
                updated_by="System Default",
            )
    html_path = Path(__file__).resolve().parent.parent / "bioas_core" / "templates" / "governance" / "dashboard.html"
    template = engines["django"].from_string(html_path.read_text(encoding="utf-8"))
    return HttpResponse(template.render({
        "tier": tier, "module": module, "province": province, "city": city, "barangays": barangays, "active_barangay": active_barangay,
        "theme": theme, "citizens": citizens, "all_repo_docs": all_repo_docs, "unified_citizen_vaults": unified_citizen_vaults, "pending_photo_citizens": pending_photo_citizens, "households": households, "citizen_reports": citizen_reports, "barangay_staff_list": (list(BarangayStaffProfile.objects.filter(barangay=active_barangay).order_by("role", "full_name")) if active_barangay else []), "all_module_choices": BarangayStaffProfile.ALL_MODULE_CHOICES, "barangay_staff_list": (list(BarangayStaffProfile.objects.filter(barangay=active_barangay).order_by("role", "full_name")) if active_barangay else []), "all_module_choices": BarangayStaffProfile.ALL_MODULE_CHOICES, "councilor_staff_list": councilor_staff_list, "it_last_report": request.session.get("bioas_it_report"), "trusted_device_count": __import__("governance.models", fromlist=["TrustedLoginDevice"]).TrustedLoginDevice.objects.count(), "citizen_service_tickets": list(__import__("governance.models", fromlist=["CitizenServiceTicket"]).CitizenServiceTicket.objects.select_related("citizen").filter(barangay=active_barangay)[:60]) if active_barangay else [],
        "certificates": certificates, "cert_type_choices": __import__("documents.models", fromlist=["CertificateRequest"]).CertificateRequest.CERT_TYPES, "pending_or_certs": pending_or_certs, "blotter_cases": blotter_cases,
        "committee_entries": list(__import__("governance.models", fromlist=["CommitteeModuleEntry"]).CommitteeModuleEntry.objects.filter(barangay=active_barangay, module_code__in=visible_modules)[:60]) if active_barangay else [],
        "open_icns": list(__import__("governance.models", fromlist=["WalkInIncidentTicket"]).WalkInIncidentTicket.objects.filter(barangay=active_barangay, status="OPEN")[:30]) if active_barangay else [],
        "archived_icns": list(__import__("governance.models", fromlist=["WalkInIncidentTicket"]).WalkInIncidentTicket.objects.filter(barangay=active_barangay, status="CLOSED_ARCHIVED")[:30]) if active_barangay else [],
        "vawc_cases": list(__import__("blotter.models", fromlist=["BlotterCase"]).BlotterCase.objects.filter(barangay=active_barangay, is_vawc_confidential=True)[:25]) if (active_barangay and "VAWC" in visible_modules) else [],
        "anon_reports": list(__import__("governance.models", fromlist=["AnonymousCommunityReport"]).AnonymousCommunityReport.objects.filter(barangay=active_barangay).exclude(**({} if (request.user.is_superuser or actor_role == 'CAPTAIN') else {"report_type": "OFFICIAL_COMPLAINT"}))[:25]) if active_barangay else [],
        "qr_feedbacks": list(__import__("governance.models", fromlist=["ServiceEventQRFeedback"]).ServiceEventQRFeedback.objects.filter(barangay=active_barangay).order_by("-created_at")[:20]) if active_barangay else [], "lupon_summons": list(__import__("blotter.models", fromlist=["LuponSummonNotice"]).LuponSummonNotice.objects.select_related("blotter_case", "recipient_citizen").filter(barangay=active_barangay).order_by("-created_at")[:20]) if active_barangay else [],
        "receipts": receipts, "abuloy_sheets": abuloy_sheets, "total_collections": total_collections,
        "health_records": health_records, "medicines": medicines, "social_aids": social_aids, "rejected_citizens": list(citizens.filter(status="REJECTED_RETURNED").order_by("updated_at")), "associations": associations,
        "socio_counts": {
            "subsistence": citizens.filter(status="ACTIVE_RESIDENT", socioeconomic_tier="SUBSISTENCE").count(),
            "low_income": citizens.filter(status="ACTIVE_RESIDENT", socioeconomic_tier="LOW_INCOME").count(),
            "lower_middle": citizens.filter(status="ACTIVE_RESIDENT", socioeconomic_tier="LOWER_MIDDLE").count(),
            "self_sustaining": citizens.filter(status="ACTIVE_RESIDENT", socioeconomic_tier="SELF_SUSTAINING").count(),
        },
        "vehicles": vehicles, "reservations": list(__import__("assets_fleet.models", fromlist=["FacilityEquipmentReservation"]).FacilityEquipmentReservation.objects.select_related("citizen").filter(barangay=active_barangay).order_by("-reservation_date")[:25]) if active_barangay else [], "trips": trips, "equipment_loans": equipment_loans,
        "hazards": hazards, "evac_centers": evac_centers, "kk_youth": kk_youth, "sk_projects": sk_projects,
        "measures": measures, "bdp_projects": bdp_projects, "audit_logs": audit_logs, "dilg_reports": dilg_reports, "coa_audits": coa_audits,
        "turnovers": turnovers, "turnover_summary": turnover_summary, "total_pending_turnover": total_pending_turnover,
        "city_barangays": city_barangays, "province_cities": province_cities,
        "query": query, "search_results": search_results, "suggestions_json": json.dumps(sorted(set(suggestions))), "search_index_json": json.dumps(search_index),
        "pop_stats": pop_stats, "household_rows": household_rows, "action_notice": action_notice,
        "visible_modules": visible_modules, "staff_profile": staff_profile,
        "is_captain_or_admin": bool(request.user.is_superuser or (staff_profile and staff_profile.role == "CAPTAIN")),
        "pending_recoveries": list(__import__("governance.models", fromlist=["WalkInRecoveryRequest"]).WalkInRecoveryRequest.objects.select_related("citizen").filter(barangay=active_barangay, status="PENDING_CAPTAIN")) if active_barangay else [],
        "pending_policy_updates": list(__import__("governance.models", fromlist=["OfficialFormTemplate"]).OfficialFormTemplate.objects.filter(barangay=active_barangay, has_pending_approval=True)) if active_barangay else [],
        "blast_advisories": list(__import__("governance.models", fromlist=["BarangayBlastAdvisory"]).BarangayBlastAdvisory.objects.filter(barangay=active_barangay)[:20]) if active_barangay else [],
        "form_templates": list(__import__("governance.models", fromlist=["OfficialFormTemplate"]).OfficialFormTemplate.objects.filter(barangay=active_barangay)) if active_barangay else [],
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
            elif role == "BARANGAY_TANOD" and barangay.barangay_classification == "RURAL" and BarangayStaffProfile.objects.filter(barangay=barangay, role="BARANGAY_TANOD", is_term_active=True).exclude(approval_status="SUSPENDED").count() >= 19:
                error = "Rural Barangay Limit Reached: Maximum 19 Barangay Tanods (20 total with Chief Tanod / Hepe) allowed under Rural classification."
            elif role in ("VAW_OFFICER", "BARC", "BNS") and BarangayStaffProfile.objects.filter(barangay=barangay, role=role, is_term_active=True).exclude(approval_status="SUSPENDED").exists():
                error = f"Only 1 active {role} holder is allowed per Barangay. Attach the module to an existing officer instead."
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
                chosen_mods = [m for m in (request.POST.getlist("modules") or ["OVERVIEW", "POLICY"]) if not (sp.role == "LUPON" and m == "VAWC")]
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
<div class="card"><h3 style="margin-top:0;">4. Barangay Colors</h3><div style="margin-bottom:8px;"><button type="button" class="preset" onclick="sc('#1E3A8A','#F59E0B')">DILG Navy &amp; Gold</button><button type="button" class="preset" onclick="sc('#065F46','#FBBF24')">Emerald &amp; Gold</button><button type="button" class="preset" onclick="sc('#7F1D1D','#F59E0B')">Maroon &amp; Amber</button><button type="button" class="preset" onclick="sc('#0D2D8A','#F5B800')">Civic Royal, Crimson &amp; Gold</button></div><form method="post">{% csrf_token %}<input type="hidden" name="action" value="UPDATE_THEME"><label>Primary Color</label><input type="color" id="p" name="primary_color" value="{{ p_col }}"><label>Accent Color</label><input type="color" id="s" name="secondary_color" value="{{ s_col }}"><button type="submit" class="save">Apply Colors</button></form></div>
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


def public_anonymous_report(request):
    import secrets
    from .models import BarangayTenant, AnonymousCommunityReport, ServiceEventQRFeedback
    barangays = BarangayTenant.objects.filter(status__in=["TRIAL_ACTIVE", "FULL_ACTIVE"]).order_by("name")
    active_brgy = barangays.first()
    created_code, lookup_rep, fb_notice, error = "", None, "", ""
    event_label = request.GET.get("event", "").strip() or "Barangay Service / Community Event"

    if request.method == "POST":
        act = request.POST.get("action", "")
        b_id = request.POST.get("barangay_id")
        target_brgy = barangays.filter(id=b_id).first() or active_brgy
        if act == "SUBMIT_ANON_REPORT":
            rtype = request.POST.get("report_type", "PUBLIC_HAZARD")
            loc = request.POST.get("location_landmark", "").strip()
            det = request.POST.get("details", "").strip()
            against = request.POST.get("against_official_name", "").strip()
            if not (target_brgy and loc and det):
                error = "Barangay, location landmark, and details are required."
            else:
                code = f"ACR-{timezone.now().year}-{secrets.randbelow(90000)+10000}-{secrets.token_hex(2).upper()}"
                AnonymousCommunityReport.objects.create(
                    barangay=target_brgy, tracking_code=code, report_type=rtype,
                    location_landmark=loc, details=det, against_official_name=against,
                )
                created_code = code
        elif act == "CHECK_ANON_STATUS":
            q_code = request.POST.get("lookup_code", "").strip().upper()
            lookup_rep = AnonymousCommunityReport.objects.filter(tracking_code=q_code).first()
            if not lookup_rep:
                error = f"Tracking code '{q_code}' was not found."
        elif act == "SUBMIT_QR_FEEDBACK":
            rat = request.POST.get("rating", "GOOD")
            ev = request.POST.get("event_or_service", event_label).strip() or event_label
            cm = request.POST.get("comment", "").strip()[:240]
            if target_brgy and rat in ("GOOD", "FAIR", "BAD"):
                ServiceEventQRFeedback.objects.create(barangay=target_brgy, event_or_service=ev, rating=rat, comment=cm)
                fb_notice = "Thank you! Your anonymous service/event rating has been recorded."

    return render(request, "governance/anonymous_report.html", {
        "barangays": barangays, "active_brgy": active_brgy, "event_label": event_label,
        "created_code": created_code, "lookup_rep": lookup_rep, "fb_notice": fb_notice, "error": error,
    })
