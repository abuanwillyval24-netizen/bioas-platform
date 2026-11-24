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
    for cid in existing_ids:
        tail = cid.replace(prefix, "").strip()
        if tail.isdigit():
            max_seq = max(max_seq, int(tail))
    return f"{prefix}{max_seq + 1:05d}"


def save_standardized_citizen_files(cit, photo_file=None, doc_files=None, source_channel="SELF_PORTAL", uploaded_by=""):
    cid = cit.citizen_qr_id.strip().upper()
    if photo_file:
        ext = os.path.splitext(photo_file.name).__getitem__(1).lower() or ".png"
        if ext not in (".png", ".jpg", ".jpeg", ".webp"):
            ext = ".png"
        mime = "image/jpeg" if ext in (".jpg", ".jpeg") else ("image/webp" if ext == ".webp" else "image/png")
        photo_bytes = photo_file.read()
        if photo_bytes:
            photo_name = f"{cid}_2x2{ext}"
            cit.photo.save(photo_name, ContentFile(photo_bytes), save=False)
            cit.photo_data_uri = f"data:{mime};base64," + base64.b64encode(photo_bytes).decode("ascii")
            cit.save(update_fields=["photo", "photo_data_uri"])

    valid_docs = [f for f in (doc_files or []) if f]
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
                    im = Image.open(BytesIO(raw)).convert("RGB")
                    img_pages.append(im)
                except Exception:
                    continue
        if pdf_bytes is None and img_pages:
            out_buf = BytesIO()
            first_im = img_pages.__getitem__(0)
            rest_ims = img_pages.__getitem__(slice(1, None))
            first_im.save(out_buf, format="PDF", resolution=150.0, save_all=True, append_images=rest_ims)
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
                file_data_uri=pdf_uri,
                source_channel=source_channel,
                uploaded_by=uploaded_by or cit.full_name,
            )

def citizen_portal(request):
    import random, re
    from django.http import JsonResponse
    from django.contrib.auth.hashers import make_password
    from django.core.mail import send_mail
    from django.conf import settings as dj_settings

    if request.GET.get("check_username") is not None:
        u_q = request.GET.get("check_username", "").strip().lower()
        if len(u_q) < 4 or not re.match(r"^[a-z0-9._-]+$", u_q):
            return JsonResponse({"available": False, "message": "Use 4+ lowercase letters, numbers, dots, or underscores."})
        taken = CitizenProfile.objects.filter(portal_username__iexact=u_q).exists()
        return JsonResponse({"available": not taken, "message": "Username is already taken." if taken else "Username is available!"})

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
                "address_line": request.POST.get("address_line", "").strip(),
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
            raw_sex = draft.get("sex", "MALE").upper()
            norm_sex = "FEMALE" if ("FEMALE" in raw_sex or raw_sex.startswith("F")) else "MALE"
            g_id = raw_sex if raw_sex in ("LGBTQ_MALE", "LGBTQ_FEMALE") else norm_sex
            submitted_email = draft.get("email_address", "")
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
                address_line=draft["address_line"],
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
        "wizard_step": wizard_step,
        "draft": draft,
        "error": error,
        "ack_notice": ack_notice,
    }, request))


def citizen_home(request):
    from django.contrib.auth.hashers import check_password, make_password
    import random
    qr_id = (request.POST.get("qr_id") or request.GET.get("qr_id") or "").strip().upper()
    login_username = (request.POST.get("portal_username") or "").strip().lower()
    rec_qr_id = (request.POST.get("rec_qr_id") or "").strip().upper()
    rec_email = (request.POST.get("rec_email") or "").strip()
    otp_stage, notice, error, citizen = "", "", "", None
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
        if request.method == "GET":
            request.session.pop("citizen_auth_id", None)
        auth_cid = request.session.get("citizen_auth_id")
        if auth_cid:
            citizen = CitizenProfile.objects.select_related("barangay", "household").filter(id=auth_cid).first()
        elif qr_id and request.user.is_authenticated:
            citizen = CitizenProfile.objects.select_related("barangay", "household").filter(citizen_qr_id=qr_id).first()

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
    elif citizen and request.method == "GET":
        notice = "Account Approved & Verified! Please complete your remaining 201 profile details below so your full Barangay 201 Master Record is up to date."

    if request.method == "POST" and citizen:
        act = request.POST.get("action")
        if act == "UPDATE_201_PROFILE":
            citizen.birth_place = request.POST.get("birth_place", citizen.birth_place).strip()
            citizen.religion = request.POST.get("religion", citizen.religion).strip()
            citizen.blood_type = request.POST.get("blood_type", citizen.blood_type).strip()
            citizen.civil_status = request.POST.get("civil_status", citizen.civil_status)
            citizen.address_line = request.POST.get("address_line", citizen.address_line).strip()
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

        elif act == "REQUEST_CERT":
            ctype = request.POST["cert_type"]
            exempt = ctype in ("INDIGENCY", "FIRST_TIME_JOBSEEKER")
            cert = CertificateRequest.objects.create(
                barangay=citizen.barangay,
                citizen=citizen,
                control_number=f"CERT-{uuid.uuid4().hex[:6].upper()}",
                cert_type=ctype,
                purpose=request.POST["purpose"].strip(),
                is_fee_exempt=exempt,
                fee_amount=0.00 if exempt else float(citizen.barangay.default_clearance_fee),
                status="READY_TO_PRINT" if (exempt or not citizen.barangay.fee_collection_enabled) else "PENDING_OR",
            )
            notice = f"Certificate Requested! Control No.: {cert.control_number} ({cert.get_status_display()})."

    citizen_qr_uri = make_citizen_qr_uri(request.build_absolute_uri(f"/citizen-home/?qr_id={citizen.citizen_qr_id}")) if citizen else ""
    family_members = citizen.household.members.all() if (citizen and citizen.household) else []
    recent_certs = CertificateRequest.objects.filter(citizen=citizen)[:5] if citizen else []
    recent_reports = CitizenCommunityReport.objects.filter(citizen=citizen)[:5] if citizen else []

    html_path = Path(__file__).resolve().parent.parent / "bioas_core" / "templates" / "governance" / "citizen_home.html"
    tpl = engines["django"].from_string(html_path.read_text(encoding="utf-8"))
    resp = HttpResponse(tpl.render({
        "citizen": citizen, "qr_id": qr_id, "notice": notice, "error": error,
        "citizen_qr_uri": citizen_qr_uri, "family_members": family_members,
        "recent_certs": recent_certs, "recent_reports": recent_reports, "login_username": login_username, "rec_qr_id": rec_qr_id, "rec_email": rec_email, "otp_stage": otp_stage,
    }, request))
    resp["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp["Pragma"] = "no-cache"
    return resp

from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required


@login_required(login_url="/login/")
def approve_citizen(request, citizen_id):
    citizen = get_object_or_404(CitizenProfile, id=citizen_id)
    citizen.status = "ACTIVE_RESIDENT"
    citizen.save()
    return redirect("/?tier=BARANGAY&module=CITIZENS")


@login_required(login_url="/login/")
def update_report_status(request, report_id, new_status):
    report = get_object_or_404(CitizenCommunityReport, id=report_id)
    if new_status in ("SUBMITTED_OPEN", "DISPATCHED_TANOD_WO", "RESOLVED_CLOSED"):
        report.status = new_status
        report.save(update_fields=["status"])
    return redirect("/?tier=BARANGAY&module=CITIZENS")
@login_required(login_url="/login/")
def citizen_docs_repository(request, qr_id):
    from .models import CitizenSupportingDocument

    citizen = get_object_or_404(CitizenProfile, citizen_qr_id=qr_id.strip().upper())
    if citizen.supporting_document and citizen.supporting_document.name:
        if not CitizenSupportingDocument.objects.filter(citizen=citizen, file=citizen.supporting_document.name).exists():
            CitizenSupportingDocument.objects.create(
                citizen=citizen,
                document_title=f"201 Supporting Document ({citizen.full_name})",
                source_channel="WALKIN_DESK",
                file=citizen.supporting_document.name,
                uploaded_by="201 Master Record",
            )

    notice, error = "", ""
    if request.method == "POST":
        doc_title = request.POST.get("document_title", "").strip()
        uploaded_file = request.FILES.get("repo_file")
        if not doc_title or not uploaded_file:
            error = "Document title and file (PDF, JPG, PNG) are required."
        else:
            staff_prof = getattr(request.user, "staff_profile", None)
            uploader = staff_prof.full_name if staff_prof else request.user.username
            CitizenSupportingDocument.objects.create(
                citizen=citizen,
                document_title=doc_title,
                source_channel="STAFF_REPOSITORY",
                file=uploaded_file,
                uploaded_by=uploader,
            )
            notice = f"Uploaded '{doc_title}' into {citizen.full_name}'s Supporting Docs Repository."

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
</style></head><body>
<div class="top">
  <div><strong>201 Supporting Documents Repository</strong> &mdash; {{ citizen.barangay.name }}</div>
  <button type="button" onclick="window.close()" style="background:rgba(255,255,255,.18);">Close Tab &#10005;</button>
</div>
<div class="wrap">
  {% if notice %}<div class="card" style="background:#dcfce7;color:#166534;font-weight:700;">{{ notice }}</div>{% endif %}
  {% if error %}<div class="card" style="background:#fee2e2;color:#991b1b;font-weight:700;">{{ error }}</div>{% endif %}

  <div class="card" style="display:flex;gap:16px;align-items:center;flex-wrap:wrap;border-top:4px solid {{ p_col }};">
    {% if citizen.photo %}
      <img src="{{ citizen.photo.url }}" alt="2x2 Photo" style="width:76px;height:76px;object-fit:cover;border-radius:8px;border:2px solid {{ s_col }};">
    {% else %}
      <div style="width:76px;height:76px;background:#e2e8f0;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:.72rem;font-weight:700;color:#475569;text-align:center;">No 2x2 Photo</div>
    {% endif %}
    <div style="flex:1;min-width:220px;">
      <div style="font-size:1.15rem;font-weight:800;">{{ citizen.full_name }} <span class="badge">{{ citizen.citizen_qr_id }}</span></div>
      <div style="font-size:.84rem;color:#475569;margin-top:3px;">{{ citizen.purok }} &bull; {{ citizen.address_line|default:"No street address" }} &bull; Age {{ citizen.age }} ({{ citizen.get_sex_display }})</div>
      <div style="font-size:.8rem;color:#166534;font-weight:700;margin-top:3px;">Status: {{ citizen.get_status_display }} {% if citizen.photo %}&bull; <a href="{{ citizen.photo.url }}" target="_blank" style="color:#1e3a8a;">Open Full 2x2 Photo &nearr;</a>{% endif %}</div>
    </div>
  </div>

  <div class="card" style="border-top:4px solid #16a34a;">
    <h3 style="margin-top:0;">Upload Additional Supporting Document to Citizen Repository</h3>
    <form method="post" enctype="multipart/form-data" style="display:grid;grid-template-columns:2fr 2fr auto;gap:10px;align-items:end;">{% csrf_token %}
      <div><label style="font-size:.76rem;font-weight:700;">Document Label / Description *</label><input name="document_title" placeholder="e.g., PSA Birth Certificate / PhilSys ID / Voter Stub" required></div>
      <div><label style="font-size:.76rem;font-weight:700;">Attach File (PDF, JPG, PNG) *</label><input type="file" name="repo_file" required style="padding:5px;"></div>
      <button type="submit">+ Upload File</button>
    </form>
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
        <td><a href="{{ d.file.url }}" target="_blank" style="background:#1e3a8a;color:#fff;padding:5px 11px;border-radius:5px;text-decoration:none;font-size:.76rem;font-weight:700;">View / Download &nearr;</a></td>
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
</div></body></html>"""
    return HttpResponse(engines["django"].from_string(tpl).render({
        "citizen": citizen, "repo_docs": repo_docs, "cert_docs": cert_docs,
        "p_col": p_col, "s_col": s_col, "notice": notice, "error": error,
    }, request))
def citizen_201_inspect(request, citizen_id):
    from django.shortcuts import redirect
    from django.utils import timezone
    c = get_object_or_404(CitizenProfile, id=citizen_id)
    qr_param = request.GET.get("qr", "").strip().upper()
    is_official = request.user.is_authenticated
    is_owner_citizen = (not is_official) and bool(qr_param) and (qr_param == c.citizen_qr_id.upper()) and (c.status == "ACTIVE_RESIDENT")
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


def citizen_proof_pdf(request, citizen_id):
    c = get_object_or_404(CitizenProfile, id=citizen_id)
    data_uri = c.supporting_doc_data_uri
    if not data_uri:
        repo_item = c.repository_docs.exclude(file_data_uri="").first()
        if repo_item:
            data_uri = repo_item.file_data_uri
    if data_uri and "," in data_uri:
        b64_part = data_uri.split(",", 1).__getitem__(1)
        raw_pdf = base64.b64decode(b64_part)
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
