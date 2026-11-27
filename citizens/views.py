from django.views.decorators.clickjacking import xframe_options_sameorigin
import base64
from io import BytesIO
import os
import re
import uuid
import qrcode
from datetime import date
from pathlib import Path
from PIL import Image
from django.core.files.base import ContentFile
from django.http import HttpResponse
from django.template import engines
from governance.models import BarangayTenant
from documents.models import CertificateRequest
from .models import CitizenProfile, Household, CitizenCommunityReport, CitizenSupportingDocument


def make_citizen_qr_uri(payload):
    qr = qrcode.QRCode(box_size=4, border=1)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#111827", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _geo_code(raw_name, fallback="GEN"):
    cleaned = re.sub(r"^(barangay|brgy\.?|city of|municipality of|province of)\s+", "", str(raw_name or "").strip(), flags=re.I)
    words = [w for w in re.split(r"[^A-Za-z0-9]+", cleaned) if w]
    if not words:
        return fallback
    if len(words) >= 2 and len(words.__getitem__(0)) <= 4:
        return "".join(w.__getitem__(0) for w in words[:3]).upper()
    return words.__getitem__(0)[:3].upper()


def generate_national_citizen_id(barangay):
    city = getattr(barangay, "city_municipality", None)
    prov = getattr(city, "province", None)
    p_code = _geo_code(getattr(prov, "name", ""), "NE")
    c_code = _geo_code(getattr(city, "name", ""), "CAB")
    b_code = _geo_code(getattr(barangay, "name", ""), "LAG")
    yr = date.today().year
    prefix = f"{p_code}-{c_code}-{b_code}-{yr}-"
    existing_ids = CitizenProfile.objects.filter(
        barangay=barangay,
        citizen_qr_id__startswith=prefix,
    ).values_list("citizen_qr_id", flat=True)
    max_seq = 0
    import secrets
    for cid in existing_ids:
        tail = cid.replace(prefix, "").strip().split("-")[0]
        if tail.isdigit():
            max_seq = max(max_seq, int(tail))
    chk = secrets.token_hex(2).upper()
    return f"{prefix}{max_seq + 1:05d}-{chk}"


def _compress_under_300kb(raw_bytes, max_bytes=295000):
    if not raw_bytes or len(raw_bytes) <= max_bytes:
        return raw_bytes, None
    im = Image.open(BytesIO(raw_bytes)).convert("RGB")
    im.thumbnail((1280, 1280))
    out = raw_bytes
    for q in (82, 70, 58, 45, 35):
        buf = BytesIO()
        im.save(buf, format="JPEG", quality=q, optimize=True)
        out = buf.getvalue()
        if len(out) <= max_bytes:
            return out, ".jpg"
    return out, ".jpg"


def save_standardized_citizen_files(cit, photo_file=None, doc_files=None, source_channel="SELF_PORTAL", uploaded_by=""):
    cid = cit.citizen_qr_id.strip().upper()
    if photo_file:
        ext = os.path.splitext(photo_file.name).__getitem__(1).lower() or ".png"
        if ext not in (".png", ".jpg", ".jpeg", ".webp"):
            ext = ".png"
        mime = "image/jpeg" if ext in (".jpg", ".jpeg") else ("image/webp" if ext == ".webp" else "image/png")
        photo_bytes, forced_ext = _compress_under_300kb(photo_file.read())
        if forced_ext:
            ext, mime = ".jpg", "image/jpeg"
        if photo_bytes:
            photo_name = f"{cid}_2x2{ext}"
            cit.photo.save(photo_name, ContentFile(photo_bytes), save=False)
            cit.photo_data_uri = f"data:{mime};base64," + base64.b64encode(photo_bytes).decode("ascii")
            cit.save(update_fields=["photo", "photo_data_uri"])

    valid_docs = [f for f in (doc_files or []) if f]
    if valid_docs and (cit.supporting_doc_data_uri or cit.supporting_document):
        for fobj in valid_docs:
            lbl = os.path.splitext(fobj.name).__getitem__(0).replace("_", " ").title() or "Additional Supporting Document"
            append_to_citizen_master_pdf(cit, lbl, fobj, uploader=uploaded_by or cit.full_name, source_channel=source_channel)
        return
    if valid_docs:
        pdf_bytes = None
        img_pages = []
        for fobj in valid_docs:
            fn_low = fobj.name.lower()
            raw = fobj.read()
            if not raw:
                continue
            if fn_low.endswith(".pdf"):
                pdf_bytes = raw
                break
            else:
                try:
                    c_raw, _ = _compress_under_300kb(raw)
                    im = Image.open(BytesIO(c_raw)).convert("RGB")
                    img_pages.append(im)
                except Exception:
                    continue
        if pdf_bytes is None and img_pages:
            out_buf = BytesIO()
            first_im = img_pages.__getitem__(0)
            rest_ims = img_pages.__getitem__(slice(1, None))
            first_im.save(out_buf, format="PDF", resolution=96.0, save_all=True, append_images=rest_ims)
            pdf_bytes = out_buf.getvalue()
        if pdf_bytes:
            std_pdf_name = f"{cid}_supporting_doc.pdf"
            pdf_uri = "data:application/pdf;base64," + base64.b64encode(pdf_bytes).decode("ascii")
            cit.supporting_document.save(std_pdf_name, ContentFile(pdf_bytes), save=False)
            cit.supporting_doc_data_uri = pdf_uri
            cit.save(update_fields=["supporting_document", "supporting_doc_data_uri"])
            CitizenSupportingDocument.objects.create(
                citizen=cit,
                document_title=f"Standardized Supporting Proof ({std_pdf_name})",
                file=ContentFile(pdf_bytes, name=std_pdf_name),
                file_data_uri="",
                source_channel=source_channel,
                uploaded_by=uploaded_by or cit.full_name,
            )

def save_shared_201_fields(citizen, post_data):
    str_fields = (
        "relationship_to_head", "alias_nickname", "gender_identity", "civil_status", "birth_place",
        "citizenship", "religion", "blood_type", "height_cm", "weight_kg", "complexion",
        "house_lot_no", "street_name", "address_line", "current_address", "purok", "residency_status",
        "mobile_number", "email_address", "emergency_contact_name", "emergency_contact_phone", "emergency_contact_relationship",
        "inhabitant_type", "household_head_name", "father_name", "mother_maiden_name", "spouse_name", "education_level", "school_or_course", "grade_year_level",
        "employment_status", "occupation", "secondary_livelihood", "employer_or_business", "employer_address", "monthly_income",
        "philsys_id", "precinct_number", "philhealth_number", "sss_gsis_number", "tin_number", "pagibig_number",
        "osca_id_number", "pwd_id_number", "pwd_disability_type", "solo_parent_id_number", "four_ps_household_id",
        "ofw_country", "ip_group_tribe",
    )
    for f in str_fields:
        if f in post_data:
            setattr(citizen, f, post_data.get(f, "").strip())
    if "years_in_barangay" in post_data:
        try:
            citizen.years_in_barangay = max(0, int(post_data.get("years_in_barangay") or 0))
        except ValueError:
            pass
    bool_fields = (
        "currently_attending_school", "is_registered_voter", "is_senior_citizen", "is_pwd",
        "is_solo_parent", "is_4ps_beneficiary", "is_first_time_jobseeker", "is_ofw", "is_osy_osc",
        "is_indigenous_people", "is_pregnant",
    )
    if "total_household_members" in post_data:
        try: citizen.total_household_members = max(1, int(post_data.get("total_household_members") or 1))
        except ValueError: pass
    if "date_moved_in" in post_data:
        dmi = post_data.get("date_moved_in", "").strip()
        try: citizen.date_moved_in = date.fromisoformat(dmi) if dmi else None
        except ValueError: pass
    import re as _re
    if citizen.street_name:
        citizen.street_name = _re.sub(r",?\s*(Barangay\s+Lagare|Lagare|Cabanatuan\s+City|Nueva\s+Ecija|Philippines|3111).*$", "", citizen.street_name, flags=_re.I).strip(" ,-")
    for mf in ("mobile_number", "emergency_contact_phone"):
        digs = "".join(c for c in (getattr(citizen, mf) or "") if c.isdigit())
        if digs.startswith("63") and len(digs)==12: digs = "0" + digs[2:]
        elif len(digs)==10 and digs.startswith("9"): digs = "0" + digs
        if len(digs)==11: setattr(citizen, mf, f"{digs[:4]}-{digs[4:7]}-{digs[7:11]}")
    if "household_code" in post_data:
        from citizens.models import Household
        hc = post_data.get("household_code", "").strip().upper()
        if hc:
            hh_obj, _ = Household.objects.get_or_create(barangay=citizen.barangay, household_code=hc, defaults={"household_head_name": citizen.household_head_name or citizen.full_name, "purok": citizen.purok or "Purok I", "address_line": citizen.address_line or ""})
            citizen.household = hh_obj
        else:
            citizen.household = None
    if not citizen.household:
        from citizens.models import Household
        hh = None
        if citizen.household_head_name:
            hh = Household.objects.filter(barangay=citizen.barangay, household_head_name__icontains=citizen.household_head_name.strip()).first()
        if not hh and citizen.shared_contact_matches:
            for m in citizen.shared_contact_matches:
                if m.household:
                    hh = m.household; break
        if hh:
            citizen.household = hh
    if citizen.sex == "MALE": citizen.is_pregnant = False
    for bf in bool_fields:
        setattr(citizen, bf, post_data.get(bf) in ("1", "on", "true", "True"))


from django.views.decorators.cache import never_cache


@never_cache
def citizen_portal(request):
    if request.session.get("citizen_auth_id") and not request.GET.get("logout"):
        return redirect("/citizen-home/")
    import random, re
    from django.http import JsonResponse
    from django.contrib.auth.hashers import make_password
    from django.core.mail import send_mail
    from django.conf import settings as dj_settings

    if request.GET.get("check_username") is not None:
        u_q = request.GET.get("check_username", "").strip().lower()
        if len(u_q) < 4 or not re.match(r"^[a-z][a-z0-9._]{3,29}$", u_q):
            return JsonResponse({"available": False, "message": "Must start with a letter (4-30 chars: letters, numbers, . or _ only)."})
        taken = CitizenProfile.objects.filter(portal_username__iexact=u_q).exists()
        return JsonResponse({"available": not taken, "message": "Username is already taken." if taken else "Username is available!"})

    if request.GET.get("icn"):
        request.session["bioas_walkin_icn"] = request.GET.get("icn", "").strip().upper()
    if request.GET.get("icn"):
        request.session["bioas_walkin_icn"] = request.GET.get("icn", "").strip().upper()
    barangays = BarangayTenant.objects.select_related("city_municipality__province").all()
    active_barangay = barangays.first()
    submitted_citizen = None
    submitted_email = ""
    wizard_step = "STEP1"
    error, ack_notice = "", ""
    draft = request.session.get("bioas_signup_draft") or {}

    if request.method == "POST" and active_barangay:
        w_act = request.POST.get("wizard_action", "STEP1_SEND_OTP")
        if w_act == "STEP1_BACK":
            wizard_step = "STEP1"
        elif w_act == "STEP1_SEND_OTP":
            b_id = request.POST.get("barangay_id") or str(active_barangay.id)
            target_brgy = barangays.filter(id=b_id).first() or active_barangay
            uname = request.POST.get("portal_username", "").strip().lower()
            pw1 = request.POST.get("portal_password", "")
            pw2 = request.POST.get("confirm_password", "")
            em = request.POST.get("email_address", "").strip()
            mob_raw = request.POST.get("mobile_number", "").strip()
            mob_d = "".join(c for c in mob_raw if c.isdigit())
            if mob_d.startswith("63") and len(mob_d)==12: mob_d = "0" + mob_d[2:]
            elif len(mob_d)==10 and mob_d.startswith("9"): mob_d = "0" + mob_d
            from django.utils import timezone as _tz
            from datetime import timedelta as _td
            is_walkin = bool(request.session.get("bioas_walkin_icn") or request.POST.get("icn_code"))
            em_cnt = CitizenProfile.objects.filter(email_address__iexact=em).count() if em else 0
            mob_cnt = CitizenProfile.objects.filter(mobile_number__icontains=mob_d[-9:]).count() if len(mob_d)>=9 else 0
            day_cnt = CitizenProfile.objects.filter(created_at__gte=_tz.now()-_td(hours=24), email_address__iexact=em).count() if em else 0
            if not is_walkin and (em_cnt >= 5 or mob_cnt >= 5):
                error = "Shared Household Contact Limit (Max 5 family members per email/mobile) reached. For additional household members, please visit the Barangay Hall Walk-In Desk."
            elif not is_walkin and (day_cnt >= 2 or len([x for x in request.session.get("bioas_24h_signups", []) if x > _tz.now().timestamp() - 86400]) >= 2):
                error = "Anti-Spam Security Limit: Maximum of 2 online self-registrations allowed per contact/device within 24 hours. Please try again tomorrow or visit the Barangay Hall."
            if error:
                return render(request, "governance/citizen_portal.html", {"barangays": barangays, "active_barangay": target_brgy, "error": error, "wizard_step": "STEP1", "draft": request.POST})
            draft = {
                "barangay_id": target_brgy.id,
                "last_name": request.POST.get("last_name", "").strip(),
                "first_name": request.POST.get("first_name", "").strip(),
                "middle_name": request.POST.get("middle_name", "").strip(),
                "suffix": request.POST.get("suffix", "").strip(),
                "alias_nickname": request.POST.get("alias_nickname", "").strip(),
                "sex": request.POST.get("sex", "").strip(),
                "civil_status": request.POST.get("civil_status", "SINGLE").strip(),
                "birth_date": request.POST.get("birth_date", "").strip(),
                "purok": request.POST.get("purok", "").strip(),
                "address_line": request.POST.get("address_line", "").strip(), "current_address": request.POST.get("current_address", "").strip(),
                "email_address": em,
                "mobile_number": request.POST.get("mobile_number", "").strip(),
                "portal_username": uname,
                "agree_terms": bool(request.POST.get("agree_terms_privacy")),
            }
            if not (draft["last_name"] and draft["first_name"] and draft["birth_date"] and draft["purok"] and draft["address_line"] and em and draft["mobile_number"]):
                error = "Please complete all required personal and contact fields."
            elif len(uname) < 4 or CitizenProfile.objects.filter(portal_username__iexact=uname).exists():
                error = "Please choose a valid, available Portal Username (at least 4 characters)."
            elif not re.match(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*[0-9])(?=.*[^A-Za-z0-9]).{8,}$", pw1):
                error = "Password must be at least 8 characters with 1 uppercase letter, 1 lowercase letter, 1 number, and 1 special character."
            elif pw1 != pw2:
                error = "Password and Confirm Password do not match."
            elif not draft["agree_terms"]:
                error = "You must agree to the Data Privacy Policy and Terms of Use before proceeding."
            else:
                otp_code = f"{random.randint(100000, 999999)}"
                draft["password_hash"] = make_password(pw1)
                draft["otp_code"] = otp_code
                draft["otp_verified"] = False
                request.session["bioas_signup_draft"] = draft
                try:
                    send_mail(
                        subject=f"[{target_brgy.name}] Citizen Registration 6-Digit Verification OTP",
                        message=f"Good day {draft['first_name']} {draft['last_name']},\n\nYour 6-digit One-Time Password (OTP) to verify your email for BIOAS Citizen Registration is:\n\n{otp_code}\n\nEnter this code on the verification screen to continue.",
                        from_email=getattr(dj_settings, "DEFAULT_FROM_EMAIL", None),
                        recipient_list=[em],
                        fail_silently=False,
                    )
                except Exception as mail_err:
                    print("BIOAS_SIGNUP_OTP_EMAIL_ERROR:", repr(mail_err))
                wizard_step = "STEP2A"
                ack_notice = f"A 6-digit verification OTP has been sent to {em}. Please enter it below to verify your email."
        elif w_act == "STEP2A_RESEND_OTP" and draft:
            otp_code = f"{random.randint(100000, 999999)}"
            draft["otp_code"] = otp_code
            request.session["bioas_signup_draft"] = draft
            target_brgy = barangays.filter(id=draft.get("barangay_id")).first() or active_barangay
            try:
                send_mail(
                    subject=f"[{target_brgy.name}] New 6-Digit Verification OTP",
                    message=f"Good day {draft.get('first_name', '')},\n\nYour new 6-digit verification OTP is: {otp_code}",
                    from_email=getattr(dj_settings, "DEFAULT_FROM_EMAIL", None),
                    recipient_list=[draft.get("email_address", "")],
                    fail_silently=False,
                )
            except Exception as mail_err:
                print("BIOAS_SIGNUP_RESEND_OTP_ERROR:", repr(mail_err))
            wizard_step = "STEP2A"
            ack_notice = f"A fresh 6-digit verification OTP has been resent to {draft.get('email_address', '')}."
        elif w_act == "STEP2A_VERIFY_OTP" and draft:
            entered = request.POST.get("otp_code", "").strip()
            if not entered or entered != draft.get("otp_code"):
                error = "Invalid 6-digit OTP code. Please check your email or click Resend Code."
                wizard_step = "STEP2A"
            else:
                draft["otp_verified"] = True
                request.session["bioas_signup_draft"] = draft
                wizard_step = "STEP2B"
                ack_notice = "Email verified successfully! Please upload your 2x2 Official Photo and Supporting Document to finish."
        elif w_act == "STEP2B_COMPLETE_SIGNUP" and draft and draft.get("otp_verified"):
            target_brgy = barangays.filter(id=draft.get("barangay_id")).first() or active_barangay
            if CitizenProfile.objects.filter(barangay=target_brgy, status="PENDING_APPROVAL", is_archived=False).count() >= 150:
                error = "The Barangay online verification queue is temporarily full (150 pending applications). Please visit the Barangay Hall Walk-In Desk."
                return render(request, "governance/citizen_portal.html", {"barangays": barangays, "active_barangay": active_barangay, "wizard_step": "STEP2", "draft": draft, "error": error})
            raw_sex = draft.get("sex", "MALE").upper()
            norm_sex = "FEMALE" if ("FEMALE" in raw_sex or raw_sex.startswith("F")) else "MALE"
            g_id = raw_sex if raw_sex in ("LGBTQ_MALE", "LGBTQ_FEMALE") else norm_sex
            from django.db import transaction
            submitted_email = draft.get("email_address", "")
            dup_exists = CitizenProfile.objects.filter(barangay=target_brgy, first_name__iexact=draft["first_name"].strip(), last_name__iexact=draft["last_name"].strip(), birth_date=date.fromisoformat(draft["birth_date"])).exists() or CitizenProfile.objects.filter(portal_username__iexact=draft["portal_username"].strip()).exists()
            if dup_exists:
                error = "Duplicate registration blocked: A citizen profile with the same Full Name & Birthdate or Username already exists in the registry."
                wizard_step = "STEP2B"
            else:
              with transaction.atomic():
                    submitted_citizen = CitizenProfile.objects.create(
                        barangay=target_brgy,
                        citizen_qr_id=generate_national_citizen_id(target_brgy),
                        last_name=draft["last_name"],
                        first_name=draft["first_name"],
                        middle_name=draft.get("middle_name", ""),
                        suffix=draft.get("suffix", ""),
                        alias_nickname=draft.get("alias_nickname", ""),
                        sex=norm_sex,
                        gender_identity=g_id,
                        birth_date=date.fromisoformat(draft["birth_date"]),
                        civil_status=draft.get("civil_status", "SINGLE"),
                        address_line=draft["address_line"], current_address=draft.get("current_address", "") or draft["address_line"],
                        purok=draft["purok"],
                        mobile_number=draft["mobile_number"],
                        email_address=submitted_email,
                        data_privacy_consent=True,
                        portal_username=draft["portal_username"],
                        portal_password_hash=draft["password_hash"],
                        encoded_by="Citizen Self-Registration Portal",
                        status="PENDING_APPROVAL",
                    )
                    save_standardized_citizen_files(
                        submitted_citizen,
                        photo_file=request.FILES.get("photo"),
                        doc_files=request.FILES.getlist("supporting_document"),
                        source_channel="PORTAL_SIGNUP",
                        uploaded_by=submitted_citizen.full_name,
                    )
                    if submitted_email:
                        try:
                            send_mail(
                                subject=f"[{target_brgy.name}] BIOAS Registration Received ? Ref ID: {submitted_citizen.citizen_qr_id}",
                                message=(
                                    f"Mabuhay {submitted_citizen.full_name}!\n\n"
                                    f"Your Citizen 201 Registration for {target_brgy.name} has been received and is currently PENDING OFFICIAL BARANGAY VERIFICATION.\n\n"
                                    f"Please save your permanent Citizen Reference Number for future sign-ins and Barangay transactions:\n"
                                    f"? Reference ID: {submitted_citizen.citizen_qr_id}\n"
                                    f"? Portal Username: {submitted_citizen.portal_username}\n"
                                    f"? Status: Pending Official Barangay Verification\n\n"
                                    f"You can sign in anytime at the BIOAS Portal using your Reference ID, Username, and Password to check your verification status or update your documents.\n\n"
                                    f"? {target_brgy.name} Digital Governance Desk"
                                ),
                                from_email=getattr(dj_settings, "DEFAULT_FROM_EMAIL", "noreply@bioas.gov.ph"),
                                recipient_list=[submitted_email],
                                fail_silently=True,
                            )
                        except Exception:
                            pass
                    icn_val = (request.POST.get("icn_code") or request.session.pop("bioas_walkin_icn", "")).strip().upper()
                    if icn_val:
                        from governance.models import WalkInIncidentTicket; from audit_analytics.models import SystemAuditLog
                        tkt = WalkInIncidentTicket.objects.filter(icn_code=icn_val, status="OPEN").first()
                        if tkt:
                            tkt.linked_citizen_qr = submitted_citizen.citizen_qr_id
                            tkt.save(update_fields=["linked_citizen_qr"])
                            submitted_citizen.encoded_by = f"Walk-In Desk (ICN: {icn_val}) ? Facilitated by {tkt.created_by_name}"
                            submitted_citizen.save(update_fields=["encoded_by"])
                            SystemAuditLog.objects.create(barangay=target_brgy, action_type="PORTAL_SYNC_APPROVED", actor_name=tkt.created_by_name, actor_role=tkt.created_by_role or "OFFICIAL", reference_code=submitted_citizen.citizen_qr_id, details=f"Walk-In registration completed under {icn_val} for {submitted_citizen.full_name}.")
                    request.session.pop("bioas_signup_draft", None)
                    wizard_step = "STEP2C"
                    ack_notice = f"Registration submitted! Your Reference Citizen ID ({submitted_citizen.citizen_qr_id}) is now staged for Barangay 201 Verification."

    html_path = Path(__file__).resolve().parent.parent / "bioas_core" / "templates" / "governance" / "portal.html"
    template = engines["django"].from_string(html_path.read_text(encoding="utf-8"))
    return HttpResponse(template.render({
        "barangays": barangays,
        "active_barangay": active_barangay,
        "submitted_citizen": submitted_citizen,
        "submitted_email": submitted_email,
        "privacy_policy_tpl": __import__("governance.models", fromlist=["OfficialFormTemplate"]).OfficialFormTemplate.objects.filter(barangay=active_barangay, category="DATA_PRIVACY_POLICY").first() if active_barangay else None,
        "wizard_step": wizard_step,
        "draft": draft,
        "error": error,
        "ack_notice": ack_notice,
    }, request))


@never_cache
def citizen_home(request):
    from django.contrib.auth.hashers import check_password, make_password
    import random
    qr_id = (request.POST.get("qr_id") or request.GET.get("qr_id") or "").strip().upper()
    login_username = (request.POST.get("portal_username") or "").strip().lower()
    rec_qr_id = (request.POST.get("rec_qr_id") or "").strip().upper()
    rec_email = (request.POST.get("rec_email") or "").strip()
    otp_stage, notice, error, citizen = "", "", "", None
    if request.session.get("citizen_auth_id") and not request.GET.get("logout"):
        citizen = CitizenProfile.objects.select_related("barangay", "household").filter(id=request.session["citizen_auth_id"]).first()
        for k in list(request.session.keys()):
            if "otp" in k.lower():
                request.session.pop(k, None)
    top_act = request.POST.get("action") if request.method == "POST" else ""
    if top_act == "CITIZEN_LOGIN":
        cand = CitizenProfile.objects.select_related("barangay", "household").filter(portal_username__iexact=login_username).first() if login_username else None
        if not cand or not cand.portal_password_hash or not check_password(request.POST.get("portal_password", ""), cand.portal_password_hash):
            error = "Invalid Portal Username or Password. Try again or use Forgot Password below."
        else:
            request.session["citizen_auth_id"] = cand.id
            citizen = cand
    elif top_act == "SEND_RECOVERY_OTP":
        cand = CitizenProfile.objects.filter(email_address__iexact=rec_email).order_by("-id").first() if rec_email else None
        if not cand:
            otp_stage = "VERIFY"
            notice = "If an account is registered under that email address, your Citizen Reference ID, Username, and 6-digit OTP have been sent discreetly to your email inbox."
        else:
            code = f"{random.randint(100000, 999999)}"
            request.session["citizen_otp_code"], request.session["citizen_otp_cid"], otp_stage = code, cand.id, "VERIFY"
            try:
                from django.core.mail import send_mail
                from django.conf import settings as dj_settings
                send_mail(
                    subject=f"[{cand.barangay.name}] Reference ID, Username & Password Reset OTP",
                    message=(
                        f"Good day {cand.full_name},\n\n"
                        f"Your Citizen Reference ID: {cand.citizen_qr_id}\n"
                        f"Your Portal Username: {cand.portal_username or '(Not set yet)'}\n"
                        f"Your 6-digit Password Reset OTP: {code}\n\n"
                        f"Enter this 6-digit OTP on /citizen-home/ to set a new password."
                    ),
                    from_email=getattr(dj_settings, "DEFAULT_FROM_EMAIL", None),
                    recipient_list=[cand.email_address],
                    fail_silently=False,
                )
            except Exception as mail_err:
                print("BIOAS_EMAIL_DELIVERY_ERROR:", repr(mail_err))
            notice = "If an account is registered under that email address, your Citizen Reference ID, Username, and 6-digit OTP have been sent discreetly to your email inbox."
    elif top_act == "RESET_PASSWORD_OTP":
        if not request.session.get("citizen_otp_code") or request.POST.get("otp_code", "").strip() != request.session.get("citizen_otp_code"):
            error, otp_stage = "Invalid or expired 6-digit OTP code.", "VERIFY"
        elif not __import__("re").match(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$", request.POST.get("new_password", "").strip()):
            error, otp_stage = "Password must be at least 8 characters and include Uppercase, Lowercase, Number, and Special Character.", "VERIFY"
        else:
            cand = CitizenProfile.objects.filter(id=request.session.get("citizen_otp_cid")).first()
            if cand:
                cand.portal_password_hash = make_password(request.POST.get("new_password", "").strip())
                cand.save(update_fields=["portal_password_hash"])
                request.session.pop("citizen_otp_code", None)
                request.session["citizen_auth_id"] = cand.id
                citizen, notice = cand, f"Password updated! Signed in as {cand.portal_username or cand.citizen_qr_id}."
    else:
        if request.GET.get("logout") == "1":
            request.session.pop("citizen_auth_id", None)
            return redirect("/login/?role=CITIZEN")
        auth_cid = request.session.get("citizen_auth_id")
        if auth_cid:
            citizen = CitizenProfile.objects.select_related("barangay", "household").filter(id=auth_cid, is_archived=False).first()

    if not citizen and not otp_stage and request.method == "GET" and request.GET.get("recover") != "1":
        return redirect("/login/?role=CITIZEN")
    if qr_id and not citizen:
        error = f"Citizen QR ID '{qr_id}' not found."
    elif citizen and citizen.status == "PENDING_APPROVAL":
        error = "Account Status: Pending Administrator Approval. You will receive access within 24 hours once verified by the Barangay Secretary."
        citizen = None
    elif citizen and citizen.status == "REJECTED_RETURNED":
        error = f"Application Returned for Revision ? Reason: {citizen.rejection_reason or 'Incomplete or unverified supporting documents'}. Please fix your details or re-upload a clear 2x2 Photo / Supporting Document below and click Save to resubmit for 201 verification."
    elif citizen and citizen.status != "ACTIVE_RESIDENT":
        error = f"Account Status: {citizen.get_status_display()}."
        citizen = None


    if request.method == "POST" and citizen:
        if citizen.status != "ACTIVE_RESIDENT" and request.POST.get("action") not in ("UNLOCK_STAGING_EDIT", "RESUBMIT_201_APPLICATION", "CHANGE_PASSWORD"):
            return redirect("/citizen-home/")
        act = request.POST.get("action")
        if act == "UNLOCK_STAGING_EDIT" and citizen.status == "REJECTED_RETURNED":
            from django.contrib.auth.hashers import check_password
            if check_password(request.POST.get("verify_password", ""), citizen.portal_password_hash):
                request.session[f"stg_unlocked_{citizen.id}"] = True
                notice = "Security verified! Your 201 revision fields and attachments are now unlocked for editing."
            else:
                error = "Incorrect password. Please re-enter your portal password to unlock editing."
        elif act == "RESUBMIT_201_APPLICATION" and citizen.status == "REJECTED_RETURNED":
            from django.core.mail import send_mail
            from django.conf import settings as dj_settings
            if not request.session.get(f"stg_unlocked_{citizen.id}"):
                error = "Security lock active: Click 'Edit My Profile' and verify your password first."
            elif request.POST.get("privacy_agree") != "1":
                error = "Please check the Data Privacy Agreement (RA 10173) box before submitting."
            else:
                for fld in ("last_name", "first_name", "middle_name", "suffix", "sex", "civil_status", "purok", "address_line", "current_address", "mobile_number", "email_address", "occupation"):
                    val = request.POST.get(fld, "").strip()
                    if val or fld in ("middle_name", "suffix", "current_address", "occupation"):
                        setattr(citizen, fld, val)
                if request.POST.get("birth_date"):
                    citizen.birth_date = date.fromisoformat(request.POST.get("birth_date"))
                if request.POST.get("clear_photo") == "1":
                    citizen.photo_data_uri = ""
                    if citizen.photo:
                        citizen.photo.delete(save=False)
                if request.POST.get("clear_supporting_doc") == "1":
                    citizen.supporting_doc_data_uri = ""
                    if citizen.supporting_document:
                        citizen.supporting_document.delete(save=False)
                    citizen.repository_docs.all().delete()
                citizen.status = "PENDING_APPROVAL"
                citizen.rejection_remarks = ""
                citizen.save()
                save_standardized_citizen_files(citizen, photo_file=request.FILES.get("photo"), doc_files=request.FILES.getlist("supporting_document"), source_channel="PORTAL_RESUBMIT", uploaded_by=citizen.full_name)
                request.session.pop(f"stg_unlocked_{citizen.id}", None)
                if citizen.email_address:
                    try:
                        send_mail(subject=f"[{citizen.barangay.name}] Revised 201 Application Resubmitted ? Ref: {citizen.citizen_qr_id}", message=f"Mabuhay {citizen.full_name}!\n\nYour revised 201 registration ({citizen.citizen_qr_id}) has been resubmitted and is now WAITING FOR OFFICIAL BARANGAY APPROVAL.\n\nYou will be notified once verified.\n? {citizen.barangay.name}", from_email=getattr(dj_settings, "DEFAULT_FROM_EMAIL", "noreply@bioas.gov.ph"), recipient_list=[citizen.email_address], fail_silently=True)
                    except Exception:
                        pass
                notice = f"Application ({citizen.citizen_qr_id}) resubmitted! Confirmation email sent. Your account is now locked in Waiting for Approval mode until verified by the Barangay Secretary."
        if act == "UPDATE_201_PROFILE":
            save_shared_201_fields(citizen, request.POST)
            citizen.save()
            ph_f = request.FILES.get("photo")
            up_docs = [f for f in request.FILES.getlist("supporting_document") if f]
            msgs = ["201 Master File Updated!"]
            if ph_f:
                if not citizen.can_change_photo_now:
                    from django.utils import timezone
                    lk_dt = timezone.localtime(citizen.next_allowed_photo_change).strftime("%B %d, %Y")
                    error = f"Your official 2x2 photo is locked until {lk_dt} (1 change allowed per quarter)."
                else:
                    try:
                        normalize_official_2x2_photo(citizen, ph_f)
                        msgs.append("Your 2x2 photo has been submitted and is now pending Barangay Secretary approval.")
                    except Exception as pe:
                        error = f"2x2 Photo Error: {pe}"
            if up_docs and not error:
                d_cat = request.POST.get("doc_category", "").strip() or "Supporting Document"
                d_lbl = request.POST.get("doc_label", "").strip()
                if not d_lbl:
                    error = "Please enter a Document Label / Description before uploading supporting files."
                else:
                    for df in up_docs:
                        pg_n, tot_n = append_to_citizen_master_pdf(citizen, f"{d_cat} — {d_lbl}", df, uploader=citizen.full_name, source_channel="SELF_PORTAL")
                    msgs.append(f"Document '{d_cat} — {d_lbl}' uploaded and merged into your Barangay Vault (Page {pg_n} of {tot_n}).")
            if not error:
                notice = " ".join(msgs)
        elif act == "LEGACY_UPDATE_201_PROFILE":
            citizen.birth_place = request.POST.get("birth_place", citizen.birth_place).strip()
            citizen.religion = request.POST.get("religion", citizen.religion).strip()
            citizen.blood_type = request.POST.get("blood_type", citizen.blood_type).strip()
            citizen.height_cm = request.POST.get("height_cm", citizen.height_cm).strip()
            citizen.weight_kg = request.POST.get("weight_kg", citizen.weight_kg).strip()
            citizen.complexion = request.POST.get("complexion", citizen.complexion).strip()
            g_self = request.POST.get("gender_identity", citizen.gender_identity).strip()
            if g_self in ("MALE", "FEMALE", "LGBTQ_MALE", "LGBTQ_FEMALE", "NON_BINARY"):
                citizen.gender_identity = g_self
            citizen.civil_status = request.POST.get("civil_status", citizen.civil_status)
            citizen.address_line = request.POST.get("address_line", citizen.address_line).strip()
            citizen.current_address = request.POST.get("current_address", citizen.current_address).strip()
            citizen.purok = request.POST.get("purok", citizen.purok).strip() or "Purok I"
            citizen.residency_status = request.POST.get("residency_status", citizen.residency_status)
            try:
                citizen.years_in_barangay = max(0, int(request.POST.get("years_in_barangay", citizen.years_in_barangay) or 0))
            except ValueError:
                pass
            citizen.mobile_number = request.POST.get("mobile_number", citizen.mobile_number).strip()
            citizen.email_address = request.POST.get("email_address", citizen.email_address).strip()
            citizen.emergency_contact_name = request.POST.get("emergency_contact_name", citizen.emergency_contact_name).strip()
            citizen.emergency_contact_phone = request.POST.get("emergency_contact_phone", citizen.emergency_contact_phone).strip()
            citizen.emergency_contact_relationship = request.POST.get("emergency_contact_relationship", citizen.emergency_contact_relationship).strip()
            citizen.employer_address = request.POST.get("employer_address", citizen.employer_address).strip()
            citizen.philhealth_number = request.POST.get("philhealth_number", citizen.philhealth_number).strip()
            citizen.sss_gsis_number = request.POST.get("sss_gsis_number", citizen.sss_gsis_number).strip()
            citizen.tin_number = request.POST.get("tin_number", citizen.tin_number).strip()
            citizen.pagibig_number = request.POST.get("pagibig_number", citizen.pagibig_number).strip()
            citizen.is_senior_citizen = bool(request.POST.get("is_senior_citizen"))
            citizen.is_pwd = bool(request.POST.get("is_pwd"))
            citizen.is_solo_parent = bool(request.POST.get("is_solo_parent"))
            citizen.is_4ps_beneficiary = bool(request.POST.get("is_4ps_beneficiary"))
            citizen.is_first_time_jobseeker = bool(request.POST.get("is_first_time_jobseeker"))
            citizen.father_name = request.POST.get("father_name", citizen.father_name).strip()
            citizen.mother_maiden_name = request.POST.get("mother_maiden_name", citizen.mother_maiden_name).strip()
            citizen.spouse_name = request.POST.get("spouse_name", citizen.spouse_name).strip()
            citizen.education_level = request.POST.get("education_level", citizen.education_level)
            citizen.school_or_course = request.POST.get("school_or_course", citizen.school_or_course).strip()
            citizen.occupation = request.POST.get("occupation", citizen.occupation).strip()
            citizen.employer_or_business = request.POST.get("employer_or_business", citizen.employer_or_business).strip()
            citizen.monthly_income = request.POST.get("monthly_income", citizen.monthly_income).strip()
            citizen.philsys_id = request.POST.get("philsys_id", citizen.philsys_id).strip()
            citizen.precinct_number = request.POST.get("precinct_number", citizen.precinct_number).strip()
            citizen.osca_id_number = request.POST.get("osca_id_number", citizen.osca_id_number).strip()
            citizen.pwd_id_number = request.POST.get("pwd_id_number", citizen.pwd_id_number).strip()
            citizen.pwd_disability_type = request.POST.get("pwd_disability_type", citizen.pwd_disability_type).strip()
            citizen.solo_parent_id_number = request.POST.get("solo_parent_id_number", citizen.solo_parent_id_number).strip()
            citizen.four_ps_household_id = request.POST.get("four_ps_household_id", citizen.four_ps_household_id).strip()
            citizen.is_ofw = bool(request.POST.get("is_ofw"))
            citizen.is_pregnant = bool(request.POST.get("is_pregnant"))
            hh_code = request.POST.get("household_code", "").strip().upper()
            if hh_code:
                hh = Household.objects.filter(barangay=citizen.barangay, household_code=hh_code).first()
                if not hh:
                    hh = Household.objects.create(
                        barangay=citizen.barangay,
                        household_code=hh_code,
                        household_head_name=citizen.full_name,
                        purok=citizen.purok,
                        address_line=citizen.address_line,
                    )
                citizen.household = hh
                citizen.relationship_to_head = request.POST.get("relationship_to_head", citizen.relationship_to_head)
            was_returned = (citizen.status == "REJECTED_RETURNED")
            if was_returned:
                citizen.status = "PENDING_APPROVAL"
                citizen.rejection_reason = ""
            citizen.save()
            save_standardized_citizen_files(
                citizen,
                photo_file=request.FILES.get("photo"),
                doc_files=request.FILES.getlist("supporting_document"),
                source_channel="SELF_PORTAL",
                uploaded_by=citizen.full_name,
            )
            if was_returned:
                notice = "Your corrected 201 profile and supporting documents have been resubmitted to the Barangay Secretary for verification!"
                citizen = None

        elif act == "SUBMIT_REPORT":
            rep = CitizenCommunityReport.objects.create(
                barangay=citizen.barangay,
                citizen=citizen,
                tracking_code=f"RPT-{uuid.uuid4().hex[:6].upper()}",
                category=request.POST["category"],
                location_landmark=request.POST["location_landmark"].strip(),
                description=request.POST["description"].strip(),
            )
            notice = f"Report Submitted! Tracking Code: {rep.tracking_code}."

        elif act == "TOGGLE_ADV_LIKE":
            from governance.models import BarangayBlastAdvisory
            adv = BarangayBlastAdvisory.objects.filter(id=request.POST.get("advisory_id"), barangay=citizen.barangay).first()
            if adv:
                ids = adv.like_ids_list
                cid_s = str(citizen.id)
                if cid_s in ids:
                    ids.remove(cid_s)
                else:
                    ids.append(cid_s)
                adv.liked_citizen_ids = ",".join(ids)
                adv.save(update_fields=["liked_citizen_ids"])
        elif act == "CHANGE_CITIZEN_PASSWORD":
            from django.contrib.auth.hashers import check_password, make_password
            cur_pw = request.POST.get("current_password", "")
            new_pw = request.POST.get("new_password", "")
            conf_pw = request.POST.get("confirm_password", "")
            if not check_password(cur_pw, citizen.portal_password_hash or ""):
                error = "Current password is incorrect."
            elif len(new_pw) < 8 or new_pw != conf_pw:
                error = "New password must be at least 8 characters and match confirmation."
            else:
                citizen.portal_password_hash = make_password(new_pw)
                citizen.save(update_fields=["portal_password_hash"])
                notice = "Your Citizen Portal password has been updated successfully!"
        elif act == "POST_ADV_COMMENT":
            from governance.models import BarangayBlastAdvisory, BarangayAdvisoryComment
            adv = BarangayBlastAdvisory.objects.filter(id=request.POST.get("advisory_id"), barangay=citizen.barangay).first()
            c_txt = request.POST.get("comment_text", "").strip()
            if adv and c_txt:
                BarangayAdvisoryComment.objects.create(advisory=adv, citizen=citizen, comment_text=c_txt)
                notice = "Your question / comment has been posted to the Barangay Office!"
        elif act == "SUBMIT_CERT_DISPUTE":
            c_obj = CertificateRequest.objects.filter(id=request.POST.get("cert_id"), citizen=citizen).first()
            d_note = request.POST.get("dispute_note", "").strip()
            if c_obj and d_note:
                c_obj.citizen_dispute_note = d_note
                c_obj.dispute_status = "DISPUTE_OPEN"
                c_obj.save(update_fields=["citizen_dispute_note", "dispute_status"])
                notice = f"Dispute / Hold inquiry logged for {c_obj.control_number}. The Barangay Secretary has been notified."
        elif act == "BOOK_FACILITY_EQUIPMENT":
            import secrets
            from assets_fleet.models import FacilityEquipmentReservation
            try:
                b_code = f"RES-{uuid.uuid4().hex[:6].upper()}-{secrets.token_hex(2).upper()}"
                r_from = request.POST.get("reservation_date")
                r_to = (request.POST.get("end_date") or "").strip() or r_from
                FacilityEquipmentReservation.objects.create(
                    barangay=citizen.barangay, citizen=citizen, booking_code=b_code,
                    facility_or_item=request.POST.get("facility_or_item", "COVERED_COURT"),
                    schedule_pattern=request.POST.get("schedule_pattern", "SINGLE_DAY"),
                    quantity_note=(request.POST.get("quantity_note") or "").strip() or "1 Unit / Full Facility",
                    reservation_date=r_from, end_date=r_to,
                    start_time=request.POST.get("start_time"), end_time=request.POST.get("end_time"),
                    purpose=request.POST.get("purpose", "").strip(),
                )
                notice = f"Reservation {b_code} submitted and time-slot locked! Pending Property Custodian approval."
            except Exception as res_err:
                error = str(res_err)
        elif act == "ACKNOWLEDGE_SUMMON":
            from blotter.models import LuponSummonNotice
            sm = LuponSummonNotice.objects.filter(id=request.POST.get("summon_id"), recipient_citizen=citizen).first()
            if sm:
                sm.status = "ACKNOWLEDGED"
                sm.acknowledged_at = timezone.now()
                sm.citizen_note = request.POST.get("citizen_note", "").strip()[:200]
                sm.save(update_fields=["status", "acknowledged_at", "citizen_note"])
                notice = f"e-Summon {sm.summon_code} digitally acknowledged. Please appear on {sm.hearing_date} at {sm.hearing_time.strftime('%H:%M')}."
        elif act == "REQUEST_WELFARE_AID":
            from social_welfare.models import SocialAidDistribution
            pcat = request.POST.get("program_category", "BURIAL_AICS_ENDORSEMENT")
            rsn = request.POST.get("aid_reason", "").strip()
            cyc = f"PORTAL-{timezone.localdate().strftime('%Y-%m')}-{uuid.uuid4().hex[:4].upper()}"
            SocialAidDistribution.objects.create(
                barangay=citizen.barangay, citizen=citizen, program_category=pcat,
                distribution_cycle=cyc, item_description=rsn[:140] or "Citizen Portal Assistance Request",
                status="PENDING_REVIEW", remarks=f"Citizen Portal Request: {rsn[:210]}"
            )
            notice = f"Social Assistance Application ({cyc}) submitted to Barangay Social Welfare & Ayuda!"
        elif act == "SUBMIT_SERVICE_TICKET":
            from governance.models import CitizenServiceTicket
            is_anon = request.POST.get("is_anonymous") == "1"
            tkt = CitizenServiceTicket.objects.create(
                barangay=citizen.barangay,
                citizen=None if is_anon else citizen,
                ticket_code=f"TKT-{uuid.uuid4().hex[:6].upper()}",
                service_group=request.POST.get("service_group", "REGISTRY_ACCOUNT"),
                ticket_type=request.POST.get("ticket_type", "General Inquiry")[:64],
                subject=request.POST.get("subject", "").strip()[:160],
                details=request.POST.get("details", "").strip(),
                location_or_ref=request.POST.get("location_or_ref", "").strip()[:160],
                supporting_file=request.FILES.get("supporting_file"),
                is_anonymous=is_anon,
                allow_recognition=(not is_anon and request.POST.get("allow_recognition") == "1"),
            )
            notice = f"Service Ticket {tkt.ticket_code} logged with {citizen.barangay.name}! Save this code to trace official action."
        elif act == "REPLY_SERVICE_TICKET":
            from governance.models import CitizenServiceTicket
            tkt = CitizenServiceTicket.objects.filter(id=request.POST.get("ticket_id"), citizen=citizen).first()
            msg = request.POST.get("followup_note", "").strip()
            up_f = request.FILES.get("followup_file")
            if tkt and (msg or up_f):
                if msg:
                    tkt.details = f"{tkt.details}\n[Citizen Follow-Up {timezone.localdate()}]: {msg}"
                if up_f:
                    tkt.supporting_file = up_f
                if tkt.status == "NEEDS_INFO":
                    tkt.status = "SUBMITTED"
                tkt.save()
                notice = f"Follow-up / requirement attached to {tkt.ticket_code} for Barangay review."
        elif act == "VERIFY_201_PASSWORD":
            from django.contrib.auth.hashers import check_password
            pw = request.POST.get("verify_201_password", "")
            if check_password(pw, citizen.portal_password_hash or ""):
                request.session["bioas_201_unlocked"] = True
                notice = "201 Master Profile verified and unlocked for this session."
            else:
                error = "Incorrect password. Please enter your Citizen Portal password to access your 201 Profile."
        elif act == "REQUEST_CERT":
            ctype = request.POST["cert_type"]
            exempt = ctype in ("INDIGENCY", "FIRST_TIME_JOBSEEKER")
            cert = CertificateRequest.objects.create(
                barangay=citizen.barangay,
                citizen=citizen,
                control_number=f"CERT-{uuid.uuid4().hex[:6].upper()}-{__import__('secrets').token_hex(2).upper()}",
                cert_type=ctype,
                purpose=request.POST["purpose"].strip(),
                is_fee_exempt=exempt,
                fee_amount=0.00 if exempt else float(getattr(citizen.barangay, "default_clearance_fee", 50.00) if citizen.barangay.fee_collection_enabled else 0.00),
                status="READY_TO_PRINT" if (exempt or not citizen.barangay.fee_collection_enabled) else "PENDING_OR",
            )
            notice = f"Certificate Requested! Control No.: {cert.control_number} ({cert.get_status_display()})."

    if request.method == "POST" and notice:
        request.session["bioas_cit_notice"] = notice
        return redirect("/citizen-home/")
    if request.method == "GET" and not notice:
        notice = request.session.pop("bioas_cit_notice", "")
    citizen_qr_uri = make_citizen_qr_uri(request.build_absolute_uri(f"/citizen-home/?qr_id={citizen.citizen_qr_id}")) if citizen else ""
    family_members = citizen.household.members.all() if (citizen and citizen.household) else []
    recent_certs = CertificateRequest.objects.filter(citizen=citizen)[:5] if citizen else []
    recent_reports = CitizenCommunityReport.objects.filter(citizen=citizen)[:5] if citizen else []

    html_path = Path(__file__).resolve().parent.parent / "bioas_core" / "templates" / "governance" / "citizen_home.html"
    tpl = engines["django"].from_string(html_path.read_text(encoding="utf-8"))
    resp = HttpResponse(tpl.render({
        "citizen": citizen, "qr_id": qr_id, "notice": notice, "error": error,
        "citizen_qr_uri": citizen_qr_uri, "family_members": family_members,
        "recent_certs": recent_certs, "recent_reports": recent_reports, "my_service_tickets": (list(__import__("governance.models", fromlist=["CitizenServiceTicket"]).CitizenServiceTicket.objects.filter(citizen=citizen)[:25]) if citizen else []), "profile_201_unlocked": bool(request.session.get("bioas_201_unlocked")), "staging_unlocked": bool(request.session.get(f"stg_unlocked_{citizen.id}")) if citizen else False, "my_summons": list(citizen.received_summons.select_related("blotter_case").all()[:15]) if citizen else [], "my_reservations": list(citizen.facility_reservations.all()[:15]) if citizen else [], "active_sk_seat": __import__("sk_youth.models", fromlist=["SKOfficialSeat"]).SKOfficialSeat.objects.filter(citizen=citizen, term_status="ACTIVE").first() if citizen else None, "social_assistance_records": next((list(m.objects.filter(citizen=citizen).order_by("-id")[:15]) for m in __import__("django.apps", fromlist=["apps"]).apps.get_models() if "Social" in m.__name__ or "Aid" in m.__name__ or "Welfare" in m.__name__), []) if citizen else [], "blast_advisories": list(__import__("governance.models", fromlist=["BarangayBlastAdvisory"]).BarangayBlastAdvisory.objects.filter(barangay=citizen.barangay, target_purok__in=["ALL", citizen.purok])[:15]) if citizen else [], "login_username": login_username, "rec_qr_id": rec_qr_id, "rec_email": rec_email, "otp_stage": otp_stage,
    }, request))
    resp["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp["Pragma"] = "no-cache"
    return resp

from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required


def normalize_official_2x2_photo(cit, photo_file):
    im = Image.open(photo_file).convert("RGB")
    w, h = im.size
    if w < 120 or h < 120:
        raise ValueError("Photo resolution is too low. Please upload a clear head-and-shoulders photo.")
    side = min(w, h)
    left = max(0, (w - side) // 2)
    top = max(0, int((h - side) * 0.18)) if h > w else 0
    im = im.crop((left, top, left + side, top + side)).resize((600, 600), Image.Resampling.LANCZOS)
    buf = BytesIO()
    im.save(buf, format="JPEG", quality=88, dpi=(300, 300), optimize=True)
    uri_val = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    CitizenProfile.objects.filter(id=cit.id).update(pending_photo_data_uri=uri_val, photo_review_status="PENDING", photo_rejection_reason="")
    cit.pending_photo_data_uri = uri_val
    cit.photo_review_status = "PENDING"
    cit.photo_rejection_reason = ""
    try:
        cit.user = None
        CitizenSupportingDocument.objects.create(citizen=cit, document_title="2x2 Official ID Photo Submission (Pending Secretary Approval)", source_channel="SELF_PORTAL", uploaded_by=cit.full_name)
    except Exception:
        pass


@login_required(login_url="/login/")
def review_citizen_photo(request, citizen_id):
    from datetime import timedelta
    from django.utils import timezone
    cit = get_object_or_404(CitizenProfile, id=citizen_id)
    if request.method == "POST":
        dec = request.POST.get("decision", "").strip().upper()
        if dec == "APPROVE" and cit.pending_photo_data_uri:
            cit.photo_data_uri = cit.pending_photo_data_uri
            cit.pending_photo_data_uri = ""
            cit.photo_review_status = "APPROVED"
            cit.photo_rejection_reason = ""
            now_dt = timezone.now()
            cit.photo_approved_at = now_dt
            cit.next_allowed_photo_change = now_dt + timedelta(days=90)
            CitizenProfile.objects.filter(id=cit.id).update(photo_data_uri=cit.photo_data_uri, pending_photo_data_uri="", photo_review_status="APPROVED", photo_rejection_reason="", photo_approved_at=now_dt, next_allowed_photo_change=now_dt + timedelta(days=90))
            try:
                cit.user = None
                CitizenSupportingDocument.objects.create(citizen=cit, document_title="2x2 Official ID Photo Approved (600x600px — Locked 90 Days)", source_channel="STAFF_REPOSITORY", uploaded_by=request.user.username)
            except Exception:
                pass
        elif dec == "REJECT":
            rsn = request.POST.get("rejection_reason", "").strip() or "Informal selfie, plain background required, or face obscured."
            CitizenProfile.objects.filter(id=cit.id).update(pending_photo_data_uri="", photo_review_status="REJECTED", photo_rejection_reason=rsn)
    return redirect(request.POST.get("next") or f"/citizen-inspect/{cit.id}/")


@login_required(login_url="/login/")
def approve_citizen(request, citizen_id):
    citizen = get_object_or_404(CitizenProfile, id=citizen_id)
    citizen.status = "ACTIVE_RESIDENT"
    citizen.save()
    return redirect("/?tier=BARANGAY&module=CITIZENS")


def append_to_citizen_master_pdf(cit, doc_title, uploaded_file, uploader="", source_channel="SELF_PORTAL"):
    from django.utils import timezone
    from PIL import ImageDraw
    from pypdf import PdfReader, PdfWriter
    cid = cit.citizen_qr_id.strip().upper()
    std_name = f"{cid}_supporting_doc.pdf"
    writer = PdfWriter()
    existing_bytes = None
    if cit.supporting_doc_data_uri and "," in cit.supporting_doc_data_uri:
        try: existing_bytes = base64.b64decode(cit.supporting_doc_data_uri.split(",", 1).__getitem__(1))
        except Exception: existing_bytes = None
    if not existing_bytes and cit.supporting_document:
        try:
            with cit.supporting_document.open("rb") as f: existing_bytes = f.read()
        except Exception: existing_bytes = None
    if existing_bytes:
        try:
            for pg in PdfReader(BytesIO(existing_bytes)).pages: writer.add_page(pg)
        except Exception: pass
    start_pg = len(writer.pages) + 1
    ts_str = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %I:%M %p")
    raw = uploaded_file.read()
    fn_low = (uploaded_file.name or "").lower()
    if fn_low.endswith(".pdf"):
        from PIL import ImageFont
        try:
            f_lg = ImageFont.load_default(size=14)
            f_sm = ImageFont.load_default(size=11)
        except TypeError:
            f_lg = f_sm = ImageFont.load_default()
        for idx_p, pg in enumerate(PdfReader(BytesIO(raw)).pages, start=start_pg):
            pw, ph = int(float(pg.mediabox.width)), int(float(pg.mediabox.height))
            banner_im = Image.new("RGB", (max(pw, 400), 46), "#1e3a8a")
            drw = ImageDraw.Draw(banner_im)
            drw.text((14, 7), f"PAGE {idx_p}  |  {doc_title}", fill="#ffffff", font=f_lg)
            drw.text((14, 26), f"Uploaded: {ts_str}  |  By: {uploader or cit.full_name}  |  ID: {cid}", fill="#fde68a", font=f_sm)
            b_buf = BytesIO(); banner_im.save(b_buf, format="PDF", resolution=72.0)
            b_pg = PdfReader(BytesIO(b_buf.getvalue())).pages.__getitem__(0)
            writer.add_page(pg)
            ap = writer.pages.__getitem__(-1)
            ap.mediabox.upper_right = (pw, ph + 46)
            ap.cropbox.upper_right = (pw, ph + 46)
            ap.merge_transformed_page(b_pg, (1, 0, 0, 1, 0, ph))
    else:
        c_raw, _ = _compress_under_300kb(raw)
        im = Image.open(BytesIO(c_raw)).convert("RGB")
        w, h = im.size
        canvas = Image.new("RGB", (w, h + 74), "#ffffff")
        canvas.paste(im, (0, 74))
        from PIL import ImageFont
        try:
            fs_lg = ImageFont.load_default(size=max(20, w // 36))
            fs_sm = ImageFont.load_default(size=max(15, w // 48))
            bh = max(78, fs_lg.size + fs_sm.size + 28)
        except TypeError:
            fs_lg = fs_sm = ImageFont.load_default()
            bh = 76
        canvas = Image.new("RGB", (w, h + bh), "#ffffff")
        canvas.paste(im, (0, bh))
        drw = ImageDraw.Draw(canvas)
        drw.rectangle([0, 0, w, bh - 4], fill="#1e3a8a")
        drw.text((18, 10), f"PAGE {start_pg}  |  {doc_title}", fill="#ffffff", font=fs_lg)
        drw.text((18, fs_lg.size + 18), f"Uploaded: {ts_str}  |  By: {uploader or cit.full_name}  |  ID: {cid}", fill="#fde68a", font=fs_sm)
        nb = BytesIO(); canvas.save(nb, format="PDF", resolution=96.0)
        for pg in PdfReader(BytesIO(nb.getvalue())).pages: writer.add_page(pg)
    out = BytesIO(); writer.write(out); merged_bytes = out.getvalue()
    merged_uri = "data:application/pdf;base64," + base64.b64encode(merged_bytes).decode("ascii")
    try:
        cit.supporting_document.save(std_name, ContentFile(merged_bytes), save=False)
    except Exception:
        pass
    cit.supporting_doc_data_uri = merged_uri
    cit.save(update_fields=["supporting_document", "supporting_doc_data_uri"])
    CitizenSupportingDocument.objects.filter(citizen=cit).update(file_data_uri="")
    CitizenSupportingDocument.objects.create(citizen=cit, document_title=f"Page {start_pg}: {doc_title} ({ts_str})", file_data_uri="", source_channel=source_channel, uploaded_by=uploader or cit.full_name)
    return start_pg, len(writer.pages)


@login_required(login_url="/login/")
def update_report_status(request, report_id, new_status):
    report = get_object_or_404(CitizenCommunityReport, id=report_id)
    if new_status in ("SUBMITTED_OPEN", "DISPATCHED_TANOD_WO", "RESOLVED_CLOSED"):
        report.status = new_status
        report.save(update_fields=["status"])
    return redirect("/?tier=BARANGAY&module=CITIZENS")
@never_cache
def citizen_docs_repository(request, qr_id):
    from django.http import HttpResponseForbidden
    from .models import CitizenSupportingDocument

    citizen = get_object_or_404(CitizenProfile, citizen_qr_id=qr_id.strip().upper())
    is_official = bool(request.user.is_authenticated)
    is_owner = (request.session.get("citizen_auth_id") == citizen.id)
    if not is_official and not is_owner:
        return HttpResponseForbidden("403 Forbidden: Unauthorized access to another resident's 201 documents.")
    if (citizen.supporting_doc_data_uri or citizen.supporting_document) and not CitizenSupportingDocument.objects.filter(citizen=citizen).exists():
        CitizenSupportingDocument.objects.create(citizen=citizen, document_title=f"Page 1: Initial 201 Supporting Document ({citizen.full_name})", source_channel="SELF_PORTAL", file_data_uri=citizen.supporting_doc_data_uri or "", uploaded_by=citizen.full_name)

    notice, error = "", ""
    if request.method == "POST":
        if request.POST.get("repo_action") == "DELETE_REPO_DOC":
            doc_obj = CitizenSupportingDocument.objects.filter(id=request.POST.get("doc_id"), citizen=citizen).first()
            if doc_obj:
                d_lbl = doc_obj.document_title
                import re as _re
                m_pg = _re.match(r"^Page\s+(\d+):", d_lbl or "")
                if m_pg and int(m_pg.group(1)) > 1 and citizen.supporting_doc_data_uri and "," in citizen.supporting_doc_data_uri:
                    try:
                        from pypdf import PdfReader, PdfWriter
                        raw_b = base64.b64decode(citizen.supporting_doc_data_uri.split(",", 1).__getitem__(1))
                        rdr = PdfReader(BytesIO(raw_b))
                        rm_idx = int(m_pg.group(1)) - 1
                        if 0 < rm_idx < len(rdr.pages):
                            wr = PdfWriter()
                            for pi, pg in enumerate(rdr.pages):
                                if pi != rm_idx: wr.add_page(pg)
                            ob = BytesIO(); wr.write(ob); nb = ob.getvalue()
                            n_uri = "data:application/pdf;base64," + base64.b64encode(nb).decode("ascii")
                            citizen.supporting_doc_data_uri = n_uri
                            citizen.save(update_fields=["supporting_doc_data_uri"])
                            CitizenSupportingDocument.objects.filter(citizen=citizen).update(file_data_uri=n_uri)
                    except Exception: pass
                doc_obj.delete()
                notice = f"Removed '{d_lbl}' from {citizen.full_name}'s repository. You can now attach a replacement file."
        else:
            error = "Read-Only Citizen Document Vault: Barangay officials cannot upload or alter resident supporting documents here."

    repo_docs = list(citizen.repository_docs.all())
    cert_docs = [c for c in citizen.certificates.all() if getattr(c, "supporting_document", None)]
    p_col = citizen.barangay.default_primary_color if citizen.barangay else "#1E3A8A"
    s_col = citizen.barangay.default_secondary_color if citizen.barangay else "#F59E0B"

    tpl = """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Supporting Docs Repository — {{ citizen.full_name }}</title>
<style>
*{box-sizing:border-box;font-family:system-ui,sans-serif}body{margin:0;background:#f1f5f9;color:#0f172a}
.top{background:{{ p_col }};color:#fff;padding:14px 24px;display:flex;justify-content:space-between;align-items:center;border-bottom:4px solid {{ s_col }}}
.wrap{max-width:980px;margin:22px auto;padding:0 16px}
.card{background:#fff;border-radius:10px;padding:18px;box-shadow:0 1px 4px rgba(0,0,0,.08);margin-bottom:16px}
.badge{background:#dbeafe;color:#1e40af;padding:3px 9px;border-radius:999px;font-size:.74rem;font-weight:700}
table{width:100%;border-collapse:collapse}th,td{padding:10px 12px;border-bottom:1px solid #e2e8f0;text-align:left;font-size:.85rem}
th{background:#f8fafc;color:#475569;font-size:.74rem;text-transform:uppercase}
input{width:100%;padding:8px;border:1px solid #cbd5e1;border-radius:6px}
button{background:{{ p_col }};color:#fff;border:0;padding:9px 16px;border-radius:6px;font-weight:700;cursor:pointer}
.x-del-btn{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:999px;background:#fee2e2;color:#b91c1c;border:1px solid #fca5a5;font-size:.76rem;font-weight:900;cursor:pointer;transition:all .16s ease;margin-left:6px;padding:0;vertical-align:middle}.x-del-btn:hover{background:#dc2626;color:#fff;transform:scale(1.14);box-shadow:0 3px 8px rgba(220,38,38,.32)}
</style></head><body>
<div class="top">
  <div><strong>201 Supporting Documents Repository</strong> &mdash; {{ citizen.barangay.name }}</div>
  <button type="button" onclick="window.close()" style="background:rgba(255,255,255,.18);">Close Tab &#10005;</button>
</div>
<div class="wrap">
  {% if notice %}<div class="card" style="background:#dcfce7;color:#166534;font-weight:700;">{{ notice }}</div>{% endif %}
  {% if error %}<div class="card" style="background:#fee2e2;color:#991b1b;font-weight:700;">{{ error }}</div>{% endif %}

  <div class="card" style="display:flex;gap:16px;align-items:center;flex-wrap:wrap;border-top:4px solid {{ p_col }};">
    {% if citizen.photo_data_uri or citizen.photo %}
      <img id="repo2x2Img" onclick="document.getElementById('repoZoomModal').style.display='flex'" title="Click to enlarge 2x2 photo" src="{% if citizen.photo_data_uri %}{{ citizen.photo_data_uri }}{% else %}{{ citizen.photo.url }}{% endif %}" alt="2x2 Photo" style="width:76px;height:76px;object-fit:cover;border-radius:8px;border:2px solid {{ s_col }};cursor:zoom-in;">
    {% else %}
      <div style="width:76px;height:76px;background:#e2e8f0;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:.72rem;font-weight:700;color:#475569;text-align:center;">No 2x2 Photo</div>
    {% endif %}
    <div style="flex:1;min-width:220px;">
      <div style="font-size:1.15rem;font-weight:800;">{{ citizen.full_name }} <span class="badge">{{ citizen.citizen_qr_id }}</span></div>
      <div style="font-size:.84rem;color:#475569;margin-top:3px;">{{ citizen.purok }} &bull; {{ citizen.address_line|default:"No street address" }} &bull; Age {{ citizen.age }} ({{ citizen.get_sex_display }})</div>
      <div style="font-size:.8rem;color:#166534;font-weight:700;margin-top:3px;">Status: {{ citizen.get_status_display }} {% if citizen.photo_data_uri or citizen.photo %}&bull; <a href="javascript:void(0)" onclick="document.getElementById('repoZoomModal').style.display='flex'" style="color:#1e3a8a;">Open Full 2x2 Photo &nearr;</a>{% endif %}</div>
    </div>
  </div>



  <div class="card">
    <h3 style="margin-top:0;">Attached Supporting Documents ({{ repo_docs|length }} Files)</h3>
    <table><thead><tr><th>Document Title</th><th>Submission Source</th><th>Uploaded By</th><th>Date &amp; Time</th><th>Action</th></tr></thead><tbody>
      {% for d in repo_docs %}
      <tr>
        <td><strong>{{ d.document_title }}</strong></td>
        <td><span class="badge">{{ d.get_source_channel_display }}</span></td>
        <td>{{ d.uploaded_by|default:"System" }}</td>
        <td style="white-space:nowrap;">{{ d.uploaded_at|date:"Y-m-d H:i" }}</td>
        <td><a href="javascript:void(0)" onclick="openRepoDoc('{% if d.file_data_uri %}{{ d.file_data_uri }}{% else %}/citizen-proof/{{ citizen.id }}/{% endif %}','{{ d.document_title|escapejs }}')" style="display:inline-block;white-space:nowrap;background:#1e3a8a;color:#fff;padding:5px 11px;border-radius:5px;text-decoration:none;font-size:.76rem;font-weight:700;">View / Download &nearr;</a></td>
      </tr>
      {% empty %}
      <tr><td colspan="5" style="color:#64748b;">No supporting documents uploaded for this citizen yet.</td></tr>
      {% endfor %}
      {% for cd in cert_docs %}
      <tr>
        <td><strong>Certificate Attachment ({{ cd.control_number }})</strong></td>
        <td><span class="badge">Certificate Request</span></td>
        <td>{{ citizen.full_name }}</td>
        <td style="white-space:nowrap;">{{ cd.requested_at|date:"Y-m-d H:i" }}</td>
        <td><a href="{{ cd.supporting_document.url }}" target="_blank" style="background:#1e3a8a;color:#fff;padding:5px 11px;border-radius:5px;text-decoration:none;font-size:.76rem;font-weight:700;">View / Download &nearr;</a></td>
      </tr>
      {% endfor %}
    </tbody></table>
  </div>
</div><div id="repoZoomModal" onclick="if(event.target===this)this.style.display='none'" style="display:none;position:fixed;inset:0;background:rgba(15,23,42,.75);z-index:9999;align-items:center;justify-content:center;padding:16px;"><div style="background:#fff;border-radius:14px;padding:16px;max-width:380px;width:100%;text-align:center;"><img src="{% if citizen.photo_data_uri %}{{ citizen.photo_data_uri }}{% elif citizen.photo %}{{ citizen.photo.url }}{% endif %}" style="width:100%;max-height:340px;object-fit:contain;border-radius:10px;"><button type="button" onclick="document.getElementById('repoZoomModal').style.display='none'" style="margin-top:12px;width:100%;background:#1e3a8a;color:#fff;border:0;padding:9px;border-radius:8px;font-weight:800;cursor:pointer;">Close Preview</button></div></div><div id="repoDocModal" onclick="if(event.target===this)this.style.display='none'" style="display:none;position:fixed;inset:0;background:rgba(15,23,42,.75);z-index:9999;align-items:center;justify-content:center;padding:16px;"><div style="background:#fff;border-radius:14px;padding:16px;max-width:860px;width:100%;max-height:90vh;display:flex;flex-direction:column;"><div style="display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:10px;"><strong id="repoDocTitle" style="font-size:.95rem;color:#0f172a;">Document Preview</strong><div style="display:flex;gap:8px;"><a id="repoDocDlBtn" href="#" download="document.pdf" style="background:#16a34a;color:#fff;text-decoration:none;padding:6px 12px;border-radius:7px;font-size:.78rem;font-weight:800;">&darr; Download</a><button type="button" onclick="document.getElementById('repoDocModal').style.display='none'" style="background:#e2e8f0;color:#0f172a;border:0;padding:6px 12px;border-radius:7px;font-weight:800;cursor:pointer;">Close</button></div></div><iframe id="repoDocFrame" style="width:100%;height:72vh;border:1px solid #cbd5e1;border-radius:9px;"></iframe></div></div><div id="repoDelConfirmModal" onclick="if(event.target===this)this.style.display='none'" style="display:none;position:fixed;inset:0;background:rgba(15,23,42,.65);z-index:10000;align-items:center;justify-content:center;padding:16px;"><div style="background:#fff;border-radius:14px;padding:22px;max-width:420px;width:100%;border-top:5px solid #dc2626;text-align:center;"><h3 style="margin:0 0 8px;color:#991b1b;">Clear Selected File?</h3><p id="repoDelMsg" style="margin:0 0 16px;font-size:.85rem;color:#475569;line-height:1.5;"></p><form method="post" style="display:flex;gap:8px;justify-content:center;">{% csrf_token %}<input type="hidden" name="repo_action" value="DELETE_REPO_DOC"><input type="hidden" id="repoDelIdInp" name="doc_id" value=""><button type="button" onclick="document.getElementById('repoDelConfirmModal').style.display='none'" style="background:#e2e8f0;color:#0f172a;">Cancel</button><button type="submit" style="background:#dc2626;color:#fff;">Yes, Clear File</button></form></div></div>{% if notice %}<div id="repoAckModal" style="position:fixed;inset:0;background:rgba(15,23,42,.55);z-index:10001;display:flex;align-items:center;justify-content:center;padding:16px;"><div style="background:#fff;border-radius:14px;padding:22px;max-width:420px;width:100%;border-top:5px solid #16a34a;text-align:center;"><h3 style="margin:0 0 8px;color:#166534;">Action Acknowledged</h3><p style="margin:0 0 16px;font-size:.85rem;color:#475569;line-height:1.5;">{{ notice }}</p><button type="button" onclick="document.getElementById('repoAckModal').remove()" style="width:100%;">Continue</button></div></div>{% endif %}<script>function askClearRepoFile(){var inp=document.getElementById('repoFileInp');if(!inp||!inp.value){alert('No file is currently selected.');return;}document.getElementById('repoDelMsg').textContent='Clear selected file "'+inp.files.name+'" so you can attach a new one?';var f=document.querySelector('#repoDelConfirmModal form');f.onsubmit=function(e){e.preventDefault();inp.value='';document.getElementById('repoDelConfirmModal').style.display='none';var ack=document.createElement('div');ack.style.cssText='position:fixed;inset:0;background:rgba(15,23,42,.55);z-index:10002;display:flex;align-items:center;justify-content:center;padding:16px;';ack.innerHTML='<div style="background:#fff;border-radius:14px;padding:22px;max-width:400px;width:100%;border-top:5px solid #16a34a;text-align:center;"><h3 style="margin:0 0 8px;color:#166534;">Action Acknowledged</h3><p style="margin:0 0 16px;font-size:.85rem;color:#475569;">Selected file cleared. You may now attach a new file.</p><button type="button" onclick="this.parentNode.parentNode.remove()" style="width:100%;">Continue</button></div>';document.body.appendChild(ack);};document.getElementById('repoDelConfirmModal').style.display='flex';}function askDelRepoDoc(id,t){document.getElementById('repoDelIdInp').value=id;document.getElementById('repoDelMsg').textContent='Are you sure you want to remove "'+t+'"? You can attach a replacement file immediately after.';document.getElementById('repoDelConfirmModal').style.display='flex';}function openRepoDoc(u,t){var viewUrl=u;if(u&&u.startsWith('data:application/pdf;base64,')){var b64=u.split(',')[1],bin=atob(b64),arr=new Uint8Array(bin.length);for(var i=0;i<bin.length;i++)arr[i]=bin.charCodeAt(i);viewUrl=URL.createObjectURL(new Blob([arr],{type:'application/pdf'}));}document.getElementById('repoDocTitle').textContent=t;document.getElementById('repoDocFrame').src=viewUrl;var dl=document.getElementById('repoDocDlBtn');dl.href=viewUrl;dl.download=(t||'document').replace(/[^a-z0-9._-]+/gi,'_')+'.pdf';document.getElementById('repoDocModal').style.display='flex';}</script></body></html>"""
    return HttpResponse(engines["django"].from_string(tpl).render({
        "citizen": citizen, "repo_docs": repo_docs, "cert_docs": cert_docs,
        "p_col": p_col, "s_col": s_col, "notice": notice, "error": error,
    }, request))
@never_cache
def citizen_201_inspect(request, citizen_id):
    from django.shortcuts import redirect
    from django.utils import timezone
    c = get_object_or_404(CitizenProfile, id=citizen_id)
    qr_param = request.GET.get("qr", "").strip().upper()
    is_official = request.user.is_authenticated
    is_owner_citizen = (not is_official) and (c.status == "ACTIVE_RESIDENT") and ((request.session.get("citizen_auth_id") == c.id) or (bool(qr_param) and qr_param == c.citizen_qr_id.upper()))
    if not is_official and not is_owner_citizen:
        return redirect("/login/")

    action_banner = request.session.pop("bioas_inspect_banner", "")
    if request.method == "POST" and is_official:
        from audit_analytics.models import SystemAuditLog, DILGComplianceReport, COAAuditCompliance
        staff_p = getattr(request.user, "staff_profile", None)
        act_nm = staff_p.full_name if staff_p else (request.user.get_full_name() or request.user.username)
        act_rl = staff_p.get_role_display() if staff_p else "System Administrator"
        act_cmd = request.POST.get("inspect_action", "")
        if act_cmd == "APPROVE_DIRECT" and c.status == "PENDING_APPROVAL":
            c.status = "ACTIVE_RESIDENT"
            c.save(update_fields=["status"])
            SystemAuditLog.objects.create(
                barangay=c.barangay,
                action_type="PORTAL_SYNC_APPROVED",
                actor_name=act_nm,
                actor_role=act_rl,
                reference_code=c.citizen_qr_id,
                details=f"Approved citizen portal sign-up for {c.full_name} ({c.citizen_qr_id}) directly from 201 Profile Inspect.",
            )
            if c.email_address:
                try:
                    from django.core.mail import send_mail
                    from django.conf import settings as dj_settings
                    login_link = request.build_absolute_uri("/citizen-home/")
                    uname_disp = c.portal_username or c.citizen_qr_id.lower()
                    send_mail(
                        subject=f"[{c.barangay.name}] Official 201 Account Approved & Activated - {c.citizen_qr_id}",
                        message=(
                            f"Good day {c.full_name},\n\n"
                            f"Congratulations! Your Barangay 201 Citizen Registration has been verified and officially APPROVED by {c.barangay.name}.\n\n"
                            f"========================================\n"
                            f"OFFICIAL CITIZEN ACCOUNT DETAILS\n"
                            f"Reference Citizen ID : {c.citizen_qr_id}\n"
                            f"Portal Username      : {uname_disp}\n"
                            f"Account Status       : ACTIVE VERIFIED RESIDENT\n"
                            f"Resident Portal Link : {login_link}\n"
                            f"========================================\n\n"
                            f"NEXT STEP - COMPLETE YOUR 201 PROFILE:\n"
                            f"Please sign in at {login_link} using your Portal Username ({uname_disp}) and password to complete your remaining 201 profile details and access Barangay certificates.\n\n"
                            f"Respectfully,\n"
                            f"Office of the Barangay Secretary\n"
                            f"{c.barangay.name}"
                        ),
                        from_email=getattr(dj_settings, "DEFAULT_FROM_EMAIL", None),
                        recipient_list=[c.email_address],
                        fail_silently=False,
                    )
                except Exception as mail_err:
                    print("BIOAS_APPROVAL_EMAIL_ERROR:", repr(mail_err))
            action_banner = f"Approved {c.full_name} ({c.citizen_qr_id}) into Official 201 Master & 02E Gallery! Sent 'Complete your profile' notification."
        elif act_cmd == "REJECT_DIRECT" and c.status == "PENDING_APPROVAL":
            reason = request.POST.get("reject_reason", "").strip() or "Incomplete or unverified supporting documents"
            qr_ref, full_nm = c.citizen_qr_id, c.full_name
            SystemAuditLog.objects.create(
                barangay=c.barangay,
                action_type="PORTAL_SYNC_APPROVED",
                actor_name=act_nm,
                actor_role=act_rl,
                reference_code=qr_ref,
                details=f"Rejected & returned 201 application for {full_nm} ({qr_ref}). Reason: {reason}",
            )
            c.status = "REJECTED_RETURNED"
            c.rejection_reason = reason
            c.save(update_fields=["status", "rejection_reason"])
            if c.email_address:
                try:
                    from django.core.mail import send_mail
                    from django.conf import settings as dj_settings
                    send_mail(
                        subject=f"[{c.barangay.name}] 201 Registration Returned for Revision",
                        message=(
                            f"Good day {c.full_name},\n\n"
                            f"Your Barangay 201 registration ({c.citizen_qr_id}) was returned for revision.\n"
                            f"Reason: {reason}\n\n"
                            f"Please log in at /citizen-home/ using your Portal Username ({c.portal_username or c.citizen_qr_id}) to update your details or re-upload your supporting documents and resubmit.\n\n"
                            f"-- {c.barangay.name} Office of the Barangay Secretary"
                        ),
                        from_email=getattr(dj_settings, "DEFAULT_FROM_EMAIL", None),
                        recipient_list=[c.email_address],
                        fail_silently=True,
                    )
                except Exception:
                    pass
            action_banner = f"Returned {full_nm} ({qr_ref}) for revision. Reason saved & citizen notified to log in and resubmit."
        elif act_cmd == "WALKIN_RESET_CREDS":
            import base64, re
            from django.contrib.auth.hashers import make_password
            from governance.models import WalkInRecoveryRequest
            letter_file = request.FILES.get("signed_request_letter")
            new_p = request.POST.get("walkin_temp_pass", "").strip()
            target_u = (c.portal_username or c.citizen_qr_id.lower()).strip()
            if not letter_file:
                action_banner = "Error: Signed Request Letter upload is required before submitting Walk-In Account Recovery."
            elif not re.match(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$", new_p):
                action_banner = "Error: Temporary password must be at least 8 characters with Uppercase, Lowercase, Number, and Special Character."
            else:
                raw_bytes = letter_file.read()
                mime = getattr(letter_file, "content_type", "") or "application/pdf"
                data_uri = f"data:{mime};base64,{base64.b64encode(raw_bytes).decode('ascii')}"
                WalkInRecoveryRequest.objects.create(
                    barangay=c.barangay,
                    citizen=c,
                    requested_username=target_u,
                    pending_password_hash=make_password(new_p),
                    signed_request_letter_uri=data_uri,
                    signed_request_letter_name=letter_file.name[:150],
                    submitted_by_name=act_nm,
                    status="PENDING_CAPTAIN",
                )
                SystemAuditLog.objects.create(
                    barangay=c.barangay,
                    action_type="PORTAL_SYNC_APPROVED",
                    actor_name=act_nm,
                    actor_role=act_rl,
                    reference_code=c.citizen_qr_id,
                    details=f"Submitted Walk-In Account Recovery Request for {c.full_name} ({c.citizen_qr_id}) with Signed Letter '{letter_file.name}' -> Pending Punong Barangay Approval.",
                )
                action_banner = f"Submitted Walk-In Recovery Request for {c.full_name} ({c.citizen_qr_id}) ? Subject for Punong Barangay (Captain) Approval!"
        if action_banner:
            request.session["bioas_inspect_banner"] = action_banner
        return redirect(request.get_full_path())

    view_mode = (request.GET.get("view") or "desktop").strip().lower()
    device_label = "Mobile / Handset Preview (430px)" if view_mode == "mobile" else "Official Desktop / Workstation View"
    p_col = c.barangay.default_primary_color if c.barangay else "#1E3A8A"
    s_col = c.barangay.default_secondary_color if c.barangay else "#F59E0B"
    repo_docs = list(c.repository_docs.all())
    derogatory_cases = []
    try:
        from blotter.models import BlotterCase
        derogatory_cases = list(BlotterCase.objects.filter(
            barangay=c.barangay,
            respondent_name__icontains=c.last_name,
            blocks_clearance=True,
        ))
    except Exception:
        derogatory_cases = []
    html_path = Path(__file__).resolve().parent.parent / "bioas_core" / "templates" / "governance" / "citizen_201_inspect.html"
    tpl = engines["django"].from_string(html_path.read_text(encoding="utf-8"))
    return HttpResponse(tpl.render({
        "c": c, "p_col": p_col, "s_col": s_col, "repo_docs": repo_docs,
        "derogatory_cases": derogatory_cases,
        "view_mode": view_mode, "device_label": device_label,
        "qr_param": qr_param, "now_ts": timezone.now(), "is_official": is_official, "action_banner": action_banner,
    }, request))


@never_cache
@xframe_options_sameorigin
def citizen_proof_pdf(request, citizen_id):
    c = get_object_or_404(CitizenProfile, id=citizen_id)
    data_uri = c.supporting_doc_data_uri
    if not data_uri:
        repo_item = c.repository_docs.exclude(file_data_uri="").first()
        if repo_item:
            data_uri = repo_item.file_data_uri
    if data_uri and "," in data_uri:
        hdr, b64_part = data_uri.split(",", 1)
        mime = hdr.split(";")[0].replace("data:", "").strip() or "application/pdf"
        ext = "pdf" if "pdf" in mime else ("png" if "png" in mime else "jpg")
        raw_bytes = base64.b64decode(b64_part)
        resp = HttpResponse(raw_bytes, content_type=mime)
        resp["Content-Disposition"] = f'inline; filename="{c.citizen_qr_id}_supporting_doc.{ext}"'
        return resp
    if not c.supporting_document or not os.path.exists(getattr(c.supporting_document, "path", "")):
        raw_pdf = build_standardized_citizen_pdf(c)
        c.supporting_doc_data_uri = "data:application/pdf;base64," + base64.b64encode(raw_pdf).decode("ascii")
        c.save(update_fields=["supporting_doc_data_uri"])
        resp = HttpResponse(raw_pdf, content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="{c.citizen_qr_id}_supporting_doc.pdf"'
        return resp
    if c.supporting_document:
        try:
            if os.path.exists(c.supporting_document.path):
                from django.shortcuts import redirect
                return redirect(c.supporting_document.url)
        except Exception:
            pass
        return HttpResponse(
            f"<div style='font-family:system-ui;max-width:520px;margin:60px auto;padding:24px;border:1px solid #cbd5e1;border-radius:10px;'>"
            f"<h3 style='color:#991b1b;margin-top:0;'>File Reset by Server Redeploy</h3>"
            f"<p>The file <strong>{c.citizen_qr_id}_supporting_doc.pdf</strong> was uploaded before permanent database storage was active. Please re-upload it once in <strong>02B Batch QR Uploader</strong> to store it permanently in PostgreSQL.</p>"
            f"</div>",
            status=404,
        )
    return HttpResponse("No supporting document attached for this citizen record.", status=404)
