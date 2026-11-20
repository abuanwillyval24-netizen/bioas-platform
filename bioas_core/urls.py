from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from governance.views import command_dashboard, theme_settings, staff_login, staff_logout
from governance.staff_turnover import staff_roster_and_turnover, approve_staff_account, download_term_archive
from citizens.views import citizen_portal, citizen_home, approve_citizen, update_report_status
from documents.views import issue_certificate_counter, print_certificate
from treasury.views import export_treasury_excel, issue_or_and_unlock

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", staff_login, name="staff_login"),
    path("logout/", staff_logout, name="staff_logout"),
    path("", command_dashboard, name="command_dashboard"),
    path("theme-settings/", theme_settings, name="theme_settings"),
    path("staff-roster/", staff_roster_and_turnover, name="staff_roster"),
    path("staff-roster/approve/<int:profile_id>/<str:new_status>/", approve_staff_account, name="approve_staff"),
    path("staff-roster/archive/<int:archive_id>/", download_term_archive, name="download_term_archive"),
    path("portal/", citizen_portal, name="citizen_portal"),
    path("citizen-home/", citizen_home, name="citizen_home"),
    path("approve-citizen/<int:citizen_id>/", approve_citizen, name="approve_citizen"),
    path("report-status/<int:report_id>/<str:new_status>/", update_report_status, name="update_report_status"),
    path("issue-certificate/", issue_certificate_counter, name="issue_certificate_counter"),
    path("certificate/<str:control_number>/", print_certificate, name="print_certificate"),
    path("treasury-export/", export_treasury_excel, name="export_treasury_excel"),
    path("issue-or/<int:cert_id>/", issue_or_and_unlock, name="issue_or_and_unlock"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
