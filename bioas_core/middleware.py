import hashlib
from django.contrib.auth import logout
from django.http import HttpResponseForbidden
from django.shortcuts import redirect


class RoleAccessAndIDORGuardMiddleware:
    OFFICIAL_PREFIXES = ('/approve-citizen/', '/update-report-status/', '/office/', '/staff-roster/', '/citizen-inspect/', '/certificate-assess/')
    CITIZEN_PROTECTED_PREFIXES = ('/citizen-docs/', '/citizen-proof/')
    NO_STORE_PREFIXES = ('/office/', '/citizen-home/', '/citizen-docs/', '/citizen-proof/', '/citizen-inspect/', '/staff-roster/', '/login/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path or '/'
        is_official = bool(getattr(request, 'user', None) and request.user.is_authenticated)
        cit_id = request.session.get('citizen_auth_id')

        if is_official and not path.startswith('/login/'):
            ua_str = request.META.get('HTTP_USER_AGENT', '')
            if any(m in ua_str.lower() for m in ('mobile', 'android', 'iphone', 'ipad', 'ipod', 'windows phone')):
                logout(request)
                return redirect('/login/?role=OFFICIAL')
            from governance.models import TrustedLoginDevice
            dev_tok = request.COOKIES.get('bioas_dev_tok', '')
            dev_hash = hashlib.sha256(f'{dev_tok}|{ua_str[:80]}'.encode('utf-8')).hexdigest()
            if not TrustedLoginDevice.objects.filter(account_key=f'OFF:{request.user.id}', device_token_hash=dev_hash, is_approved_workstation=True).exists():
                logout(request)
                return redirect('/login/?role=OFFICIAL')

        if any(path.startswith(p) for p in self.OFFICIAL_PREFIXES):
            if not is_official:
                return redirect('/login/?role=OFFICIAL')
            sp = getattr(request.user, 'staff_profile', None)
            if sp and getattr(sp, 'is_active_official', True) is False and not request.user.is_superuser:
                return HttpResponseForbidden('403 Forbidden: Inactive Official Account.')

        if any(path.startswith(p) for p in self.CITIZEN_PROTECTED_PREFIXES):
            if not cit_id and not is_official:
                return redirect('/login/?role=CITIZEN')

        if path.startswith('/citizen-home/'):
            is_recovery = (request.GET.get('recover') == '1') or (request.POST.get('action') in ('REQUEST_RECOVERY_OTP', 'RESET_PASSWORD_OTP'))
            if not cit_id and not is_recovery:
                return redirect('/login/?role=CITIZEN')

        response = self.get_response(request)
        if path == '/' or any(path.startswith(p) for p in self.NO_STORE_PREFIXES):
            response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
        return response
