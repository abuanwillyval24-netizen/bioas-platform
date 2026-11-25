from django.http import HttpResponseForbidden
from django.shortcuts import redirect


class RoleAccessAndIDORGuardMiddleware:
    OFFICIAL_PREFIXES = ("/approve-citizen/", "/update-report-status/", "/office/")
    CITIZEN_PROTECTED_PREFIXES = ("/citizen-docs/", "/citizen-proof/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path or "/"
        is_official = bool(getattr(request, "user", None) and request.user.is_authenticated)
        cit_id = request.session.get("citizen_auth_id")

        if any(path.startswith(p) for p in self.OFFICIAL_PREFIXES):
            if not is_official:
                return redirect("/login/?role=OFFICIAL")
            sp = getattr(request.user, "staff_profile", None)
            if sp and getattr(sp, "is_active_official", True) is False and not request.user.is_superuser:
                return HttpResponseForbidden("403 Forbidden: Inactive Official Account.")

        if any(path.startswith(p) for p in self.CITIZEN_PROTECTED_PREFIXES):
            if not cit_id and not is_official:
                return redirect("/login/?role=CITIZEN")

        if path.startswith("/citizen-home/"):
            is_recovery = (request.GET.get("recover") == "1") or (request.POST.get("action") in ("REQUEST_RECOVERY_OTP", "RESET_PASSWORD_OTP"))
            if not cit_id and not is_recovery:
                return redirect("/login/?role=CITIZEN")

        return self.get_response(request)
