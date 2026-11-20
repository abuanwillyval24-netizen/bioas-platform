from django.contrib import admin
from django.urls import path
from governance.views import command_dashboard, theme_settings, staff_login, staff_logout
from governance.staff_turnover import staff_roster_and_turnover, approve_staff_account, download_term_archive
from citizens.views import citizen_portal, citizen_home, approve_citizen, update_report_status
from documents.views import issue_certificate_counter, print_certificate, verify_certificate

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", staff_login, name="staff_login"),
    path("logout/", staff_logout, name="staff_logout"),
    path("settings/", theme_settings, name="theme_settings"),
    path("staff-roster/", staff_roster_and_turnover, name="staff_roster"),
    path("staff-roster/approve/<int:profile_id>/<str:new_status>/", approve_staff_account, name="approve_staff"),
    path("staff-roster/archive/<int:archive_id>/", download_term_archive, name="download_term_archive"),
    path("portal/", citizen_portal, name="citizen_portal"),
    path("citizen-home/", citizen_home, name="citizen_home"),
    path("citizens/approve/<int:citizen_id>/", approve_citizen, name="approve_citizen"),
    path("citizens/report/<int:report_id>/<str:new_status>/", update_report_status, name="update_report_status"),
    path("certificates/counter/", issue_certificate_counter, name="issue_certificate_counter"),
    path("certificates/print/<int:cert_id>/", print_certificate, name="print_certificate"),
    path("verify/<str:control_number>/", verify_certificate, name="verify_certificate"),
    path("", command_dashboard, name="command_dashboard"),
]
