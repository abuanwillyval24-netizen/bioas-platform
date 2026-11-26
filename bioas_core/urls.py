from django.contrib import admin
from django.urls import path, re_path
from bioas_core.hybrid_sync import hybrid_sync_pull
from sk_youth.views import sk_portal
from governance.views import public_anonymous_report
from django.conf import settings
from django.views.static import serve
from governance.views import command_dashboard, theme_settings, staff_login, staff_logout
from governance.portal_info import portal_info
from governance.staff_turnover import staff_roster_and_turnover, approve_staff_account, download_term_archive
from citizens.views import citizen_portal, citizen_home, approve_citizen, review_citizen_photo, update_report_status, citizen_docs_repository, citizen_201_inspect, citizen_proof_pdf
from documents.views import issue_certificate_counter, print_certificate
from treasury.views import export_treasury_excel, issue_or_and_unlock

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", staff_login, name="staff_login"),
    path("logout/", staff_logout, name="staff_logout"),
    path("portal-info/", portal_info, name="portal_info"),
    path("", command_dashboard, name="command_dashboard"),
    path("theme-settings/", theme_settings, name="theme_settings"),
    path("staff-roster/", staff_roster_and_turnover, name="staff_roster"),
    path("staff-roster/approve/<int:profile_id>/<str:new_status>/", approve_staff_account, name="approve_staff"),
    path("staff-roster/archive/<int:archive_id>/", download_term_archive, name="download_term_archive"),
    path("portal/", citizen_portal, name="citizen_portal"),
    path("anonymous-report/", public_anonymous_report, name="public_anonymous_report"),
    path("citizen-home/", citizen_home, name="citizen_home"),
    path("sk-portal/", sk_portal, name="sk_portal"),
    path("citizen-docs/<str:qr_id>/", citizen_docs_repository, name="citizen_docs_repository"),
    path("citizen-inspect/<int:citizen_id>/", citizen_201_inspect, name="citizen_201_inspect"),
    path("citizen-proof/<int:citizen_id>/", citizen_proof_pdf, name="citizen_proof_pdf"),
    path("approve-citizen/<int:citizen_id>/", approve_citizen, name="approve_citizen"),
    path("citizen-photo-review/<int:citizen_id>/", review_citizen_photo, name="review_citizen_photo"),
    path("report-status/<int:report_id>/<str:new_status>/", update_report_status, name="update_report_status"),
    path("issue-certificate/", issue_certificate_counter, name="issue_certificate_counter"),
    path("certificate/<str:control_number>/", print_certificate, name="print_certificate"),
    path("treasury-export/", export_treasury_excel, name="export_treasury_excel"),
    path("issue-or/<int:cert_id>/", issue_or_and_unlock, name="issue_or_and_unlock"),
    path("api/hybrid-sync/pull/", hybrid_sync_pull, name="hybrid_sync_pull"),
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]
