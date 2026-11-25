import hashlib, hmac, html, os, time
from django.apps import apps
from django.conf import settings
from django.http import JsonResponse
from citizens.models import CitizenProfile


def _clean(val):
    return html.escape(str(val or "").strip())


def hybrid_sync_pull(request):
    secret = os.environ.get("BIOAS_SYNC_TOKEN") or settings.SECRET_KEY
    tok = request.headers.get("X-BIOAS-Token", "")
    ts = request.headers.get("X-BIOAS-Timestamp", "")
    sig = request.headers.get("X-BIOAS-Signature", "")
    brgy_code = request.GET.get("barangay_code", "").strip()
    if not tok or not hmac.compare_digest(tok, secret):
        return JsonResponse({"error": "Invalid sync token"}, status=401)
    if not ts.isdigit() or abs(int(time.time()) - int(ts)) > 300:
        return JsonResponse({"error": "Expired or invalid timestamp"}, status=401)
    expected = hmac.new(secret.encode(), f"{ts}:{brgy_code}".encode(), hashlib.sha256).hexdigest()
    if not sig or not hmac.compare_digest(sig, expected):
        return JsonResponse({"error": "Invalid HMAC signature"}, status=401)
    qs = CitizenProfile.objects.filter(status="PENDING_APPROVAL", is_archived=False)
    if brgy_code:
        qs = qs.filter(barangay__code__iexact=brgy_code)
    citizens = [{"ref_id": _clean(c.citizen_qr_id), "full_name": _clean(c.full_name), "purok": _clean(c.purok), "sex": _clean(c.sex), "birth_date": str(c.birth_date)} for c in qs[:150]]
    CertModel = next((m for m in apps.get_models() if m.__name__ == "CertificateRequest"), None)
    certs = [{"control_number": _clean(r.control_number), "citizen_ref": _clean(r.citizen.citizen_qr_id), "type": _clean(r.cert_type), "purpose": _clean(r.purpose), "status": _clean(r.status)} for r in CertModel.objects.filter(status="PENDING_REVIEW")[:150]] if CertModel else []
    RepModel = next((m for m in apps.get_models() if "Report" in m.__name__ and any(f.name == "tracking_code" for f in m._meta.fields)), None)
    reports = [{"tracking_code": _clean(rp.tracking_code), "category": _clean(rp.category), "landmark": _clean(rp.location_landmark), "description": _clean(rp.description)} for rp in RepModel.objects.filter(status="SUBMITTED_OPEN")[:150]] if RepModel else []
    return JsonResponse({"ok": True, "sanitized_text_only": True, "pending_citizens": citizens, "pending_certificates": certs, "open_reports": reports})
