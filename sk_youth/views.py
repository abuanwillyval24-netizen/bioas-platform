from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect
from django.utils import timezone
from citizens.models import CitizenProfile
from .models import KatipunanKabataanProfile, SKProjectActivity, SKOfficialSeat


def sk_portal(request):
    cid = request.session.get("citizen_auth_id")
    if not cid:
        return redirect("/login/?role=CITIZEN")
    citizen = CitizenProfile.objects.select_related("barangay").filter(id=cid, is_archived=False).first()
    seat = SKOfficialSeat.objects.filter(citizen=citizen, term_status="ACTIVE").first() if citizen else None
    if not citizen or not seat:
        return HttpResponseForbidden("403 Forbidden: Active SK Official Term Seat required to access /sk-portal/.")
    brgy = citizen.barangay
    notice, error = "", ""
    if request.method == "POST":
        act = request.POST.get("action", "")
        if act == "ADD_KK_MEMBER":
            q_id = request.POST.get("kk_citizen_qr", "").strip().upper()
            target = CitizenProfile.objects.filter(barangay=brgy, citizen_qr_id=q_id, is_archived=False).first()
            if not target:
                error = "Verified resident Reference ID not found in this Barangay."
            elif target.age < 15 or target.age > 30:
                error = f"RA 10742 Rule: Katipunan ng Kabataan (KK) members must be aged 15 to 30 (resident age: {target.age})."
            else:
                KatipunanKabataanProfile.objects.update_or_create(
                    citizen=target,
                    defaults={"barangay": brgy, "youth_classification": request.POST.get("youth_classification", "IN_SCHOOL"), "education_level": request.POST.get("education_level", "SENIOR_HIGH"), "skills_and_interests": request.POST.get("skills", "").strip()},
                )
                notice = f"Registered {target.full_name} (Age {target.age}) in the Katipunan ng Kabataan (KK) Registry."
        elif act == "ADD_SK_PROJECT":
            title = request.POST.get("title", "").strip()
            budget = request.POST.get("allocated_budget") or 0
            if title:
                SKProjectActivity.objects.create(
                    barangay=brgy, project_code=f"SK-{uuid.uuid4().hex[:6].upper()}", title=title,
                    category=request.POST.get("category", "SPORTS_WELLNESS"), allocated_budget=budget,
                    sk_chairperson_lead=citizen.full_name,
                )
                notice = f"Added ABYIP / 10% SK Fund project: {title}."
        elif act == "ASSIGN_SK_SEAT" and seat.position == "SK_CHAIRPERSON":
            q_id = request.POST.get("seat_citizen_qr", "").strip().upper()
            pos = request.POST.get("position", "SK_KAGAWAD")
            elec_dt = request.POST.get("election_date") or str(seat.election_date)
            target = CitizenProfile.objects.filter(barangay=brgy, citizen_qr_id=q_id, is_archived=False).first()
            limits = {"SK_CHAIRPERSON": 1, "SK_KAGAWAD": 7, "SK_SECRETARY": 1, "SK_TREASURER": 1}
            if not target:
                error = "Resident Reference ID not found."
            elif SKOfficialSeat.objects.filter(barangay=brgy, position=pos, term_status="ACTIVE").count() >= limits.get(pos, 1):
                error = f"Maximum active seats reached for {pos}."
            else:
                try:
                    SKOfficialSeat.objects.create(barangay=brgy, citizen=target, position=pos, term_label=seat.term_label, election_date=elec_dt, appointed_by=citizen.full_name)
                    notice = f"Assigned {target.full_name} as {pos} ({seat.term_label})."
                except Exception as exc:
                    error = str(exc)
    kk_list = KatipunanKabataanProfile.objects.select_related("citizen").filter(barangay=brgy)
    projects = SKProjectActivity.objects.filter(barangay=brgy)
    sk_seats = SKOfficialSeat.objects.select_related("citizen").filter(barangay=brgy, term_status="ACTIVE")
    total_sk_fund = sum(float(p.allocated_budget or 0) for p in projects)
    return render(request, "governance/sk_portal.html", {"citizen": citizen, "seat": seat, "kk_list": kk_list, "projects": projects, "sk_seats": sk_seats, "total_sk_fund": total_sk_fund, "notice": notice, "error": error})
