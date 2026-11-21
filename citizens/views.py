import uuid
from pathlib import Path
from django.http import HttpResponse
from django.template import engines
from governance.models import BarangayTenant
from treasury.models import CertificateRequest
from .models import CitizenProfile, Household, CitizenCommunityReport


def citizen_portal(request):
    barangays = BarangayTenant.objects.all()
    active_barangay = barangays.first()
    submitted_citizen = None
    submitted_email = ""

    if request.method == "POST" and active_barangay:
        target_brgy = barangays.filter(id=request.POST.get("barangay_id")).first() or active_barangay
        raw_sex = (request.POST.get("sex") or request.POST.get("gender") or "MALE").strip().upper()
        norm_sex = "FEMALE" if raw_sex.startswith("F") else "MALE"
        submitted_email = request.POST.get("email_address", "").strip()

        submitted_citizen = CitizenProfile.objects.create(
            barangay=target_brgy,
            citizen_qr_id=f"CIT-{uuid.uuid4().hex[:6].upper()}",
            last_name=request.POST["last_name"].strip(),
            first_name=request.POST["first_name"].strip(),
            middle_name=request.POST.get("middle_name", "").strip(),
            suffix=request.POST.get("suffix", "").strip(),
            sex=norm_sex,
            gender_identity=request.POST.get("gender_identity", "PREFER_NOT_TO_SAY"),
            birth_date=request.POST["birth_date"],
            civil_status=request.POST.get("civil_status", "SINGLE"),
            address_line=request.POST.get("address_line", "").strip(),
            purok=request.POST.get("purok", "Purok I").strip() or "Purok I",
            mobile_number=request.POST.get("mobile_number", "").strip(),
            email_address=submitted_email,
            is_registered_voter=bool(request.POST.get("is_registered_voter")),
            is_senior_citizen=bool(request.POST.get("is_senior_citizen")),
            is_pwd=bool(request.POST.get("is_pwd")),
            is_solo_parent=bool(request.POST.get("is_solo_parent")),
            is_4ps_beneficiary=bool(request.POST.get("is_4ps_beneficiary")),
            is_first_time_jobseeker=bool(request.POST.get("is_first_time_jobseeker")),
            supporting_document=request.FILES.get("supporting_document"),
            electronic_signature=request.POST.get("applicant_electronic_signature", "").strip(),
            status="PENDING_APPROVAL",
        )

    html_path = Path(__file__).resolve().parent.parent / "bioas_core" / "templates" / "governance" / "portal.html"
    template = engines["django"].from_string(html_path.read_text(encoding="utf-8"))
    return HttpResponse(template.render({
        "barangays": barangays,
        "active_barangay": active_barangay,
        "submitted_citizen": submitted_citizen,
        "submitted_email": submitted_email,
    }, request))


def citizen_home(request):
    qr_id = (request.POST.get("qr_id") or request.GET.get("qr_id") or "").strip().upper()
    citizen = CitizenProfile.objects.select_related("barangay", "household").filter(citizen_qr_id=qr_id).first() if qr_id else None
    notice, error = "", ""

    if qr_id and not citizen:
        error = f"Citizen QR ID '{qr_id}' not found."
    elif citizen and citizen.status == "PENDING_APPROVAL":
        error = "Account Status: Pending Administrator Approval. You will receive access within 24 hours once verified by the Barangay Secretary."
        citizen = None
    elif citizen and citizen.status != "ACTIVE_RESIDENT":
        error = f"Account Status: {citizen.get_status_display()}."
        citizen = None

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
            if request.FILES.get("photo"):
                citizen.photo = request.FILES["photo"]
            if request.FILES.get("supporting_document"):
                citizen.supporting_document = request.FILES["supporting_document"]
            citizen.save()
            notice = f"201 Master Profile synced! Completion: {citizen.profile_completion_pct}%."

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

    family_members = citizen.household.members.all() if (citizen and citizen.household) else []
    recent_certs = CertificateRequest.objects.filter(citizen=citizen)[:5] if citizen else []
    recent_reports = CitizenCommunityReport.objects.filter(citizen=citizen)[:5] if citizen else []

    tpl = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>Citizen 201 & Self-Service Portal</title>
