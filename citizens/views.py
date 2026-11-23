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
    barangays = BarangayTenant.objects.select_related("city_municipality__province").all()
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
            citizen_qr_id=generate_national_citizen_id(target_brgy),
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
            electronic_signature=request.POST.get("applicant_electronic_signature", "").strip(),
            status="PENDING_APPROVAL",
        )
        save_standardized_citizen_files(
            submitted_citizen,
            photo_file=request.FILES.get("photo"),
            doc_files=request.FILES.getlist("supporting_document"),
            source_channel="SELF_PORTAL",
            uploaded_by=submitted_citizen.full_name,
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
            citizen.save()
            save_standardized_citizen_files(
                citizen,
                photo_file=request.FILES.get("photo"),
                doc_files=request.FILES.getlist("supporting_document"),
                source_channel="SELF_PORTAL",
                uploaded_by=citizen.full_name,
            )

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
    return HttpResponse(tpl.render({
        "citizen": citizen, "qr_id": qr_id, "notice": notice, "error": error,
        "citizen_qr_uri": citizen_qr_uri, "family_members": family_members,
        "recent_certs": recent_certs, "recent_reports": recent_reports,
    }, request))

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

    ua = request.META.get("HTTP_USER_AGENT", "")
    is_mobile_ua = any(k in ua for k in ("Mobile", "Android", "iPhone", "iPad", "Opera Mini", "IEMobile"))
    view_mode = request.GET.get("view", "").strip().lower()
    if view_mode not in ("mobile", "sheet"):
        view_mode = "mobile" if (is_mobile_ua and is_owner_citizen) else "sheet"
    device_label = "Mobile Phone" if is_mobile_ua else "Desktop Computer"

    if is_owner_citizen:
        try:
            from audit.models import SystemAuditLog
            SystemAuditLog.objects.create(
                barangay=c.barangay,
                action_type="PORTAL_SYNC_APPROVED",
                actor_name=c.full_name,
                actor_role=f"CITIZEN_SELF_SERVICE ({device_label})",
                reference_code=c.citizen_qr_id,
                details=f"Resident viewed synchronized 201 profile ({view_mode.upper()} mode) via {device_label}.",
            )
        except Exception:
            pass

    p_col = c.barangay.default_primary_color if c.barangay else "#1E3A8A"
    s_col = c.barangay.default_secondary_color if c.barangay else "#F59E0B"
    repo_docs = list(c.repository_docs.all())
    html_path = Path(__file__).resolve().parent.parent / "bioas_core" / "templates" / "governance" / "citizen_201_inspect.html"
    tpl = engines["django"].from_string(html_path.read_text(encoding="utf-8"))
    return HttpResponse(tpl.render({
        "c": c, "p_col": p_col, "s_col": s_col, "repo_docs": repo_docs,
        "view_mode": view_mode, "device_label": device_label,
        "qr_param": qr_param, "now_ts": timezone.now(),
    }, request))


def citizen_proof_pdf(request, citizen_id):
    c = get_object_or_404(CitizenProfile, id=citizen_id)
    if c.supporting_doc_data_uri and "," in c.supporting_doc_data_uri:
        b64_part = c.supporting_doc_data_uri.split(",", 1).__getitem__(1)
        raw_pdf = base64.b64decode(b64_part)
        resp = HttpResponse(raw_pdf, content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="{c.citizen_qr_id}_supporting_doc.pdf"'
        return resp
    if c.supporting_document:
        from django.shortcuts import redirect
        return redirect(c.supporting_document.url)
    return HttpResponse("No supporting document attached for this citizen record.", status=404)
