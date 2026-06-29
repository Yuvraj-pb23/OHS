from django.urls import path

from . import views

urlpatterns = [
    # --- STATIC & INFO PAGES ---
    path("", views.index, name="home"),
    path("about/", views.about, name="about"),
    path("resources/", views.resources, name="resources"),
    path("services/", views.services, name="services"),
    path("blog/", views.blog, name="blog"),
    path("gallery/", views.gallery, name="gallery"),
    path("achievements/", views.achievements, name="achievements"),
    path("footer/", views.footer, name="footer"),
    path("workplace/", views.workplace, name="workplace"),
    path("legal/", views.legal, name="legal"),
    path("why_choose_ohs/", views.why_choose_ohs, name="why_choose_ohs"),
    path(
        "registration-selection/",
        views.registration_selection_view,
        name="registration_selection",
    ),
    # --- MAIN TUTORIAL / TRAINING LANDING ---
    path("tutorial/", views.tutorial_view, name="tutorial"),
    # --- FORCE PASSWORD CHANGE (First-time login) ---
    path(
        "force-password-change/",
        views.force_password_change,
        name="force_password_change",
    ),
    # --- AJAX API for Training ---
    path("ajax/update-watch-time/", views.update_watch_time, name="update_watch_time"),
    path("ajax/mod-complete/<int:module_id>/", views.mod_complete, name="mod_complete"),
    path("ajax/get-assessment-questions/", views.get_assessment_questions, name="get_assessment_questions"),
    path("ajax/submit-assessment/", views.submit_assessment, name="submit_assessment"),
    path("ajax/reset-progress/", views.reset_progress, name="reset_progress"),
    path("ajax/save-video-progress/", views.save_video_progress, name="save_video_progress"),
    path("ajax/member-progress/<int:member_id>/", views.member_progress_api, name="member_progress_api"),
    path("ajax/upload-org-logo/", views.upload_org_logo, name="upload_org_logo"),
    # --- SUBSCRIPTION FLOWS ---
    path(
        "subscription/individual/<str:plan_type>/",
        views.individual_subscription,
        name="individual_subscription",
    ),
    path(
        "subscription/company/<str:plan_type>/",
        views.company_subscription,
        name="company_subscription",
    ),
    # --- OTP ENDPOINTS FOR COMPANY REGISTRATION ---
    path(
        "ajax/send-reg-otp/", views.send_registration_otp, name="send_registration_otp"
    ),
    path(
        "ajax/verify-reg-otp/",
        views.verify_registration_otp,
        name="verify_registration_otp",
    ),
    path(
        "generate-captcha/",
        views.generate_captcha_image,
        name="generate_captcha",
    ),
    path(
        "ajax/verify-captcha/",
        views.verify_captcha_view,
        name="verify_captcha",
    ),
    # --- COMPANY DASHBOARD & MANAGEMENT ---
    path("dashboard/company/", views.company_dashboard, name="company_dashboard"),
    path("dashboard/company", views.company_dashboard),
    # Backward-compatible aliases for older bookmarks/links
    path("company-dashboard/", views.company_dashboard),
    path("company-dashboard", views.company_dashboard),
    path("company_dashboard/", views.company_dashboard),
    path("company_dashboard", views.company_dashboard),
    path("dashboard/add-employee/", views.add_employee, name="add_employee"),
    path(
        "download-template/",
        views.download_employee_template,
        name="download_employee_template",
    ),
    path("upload-bulk/", views.upload_employee_bulk, name="upload_employee_bulk"),
    # NEW: Logo Management & Dynamic Posters
    path(
        "dashboard/upload-logo/", views.upload_company_logo, name="upload_company_logo"
    ),
    path(
        "get-poster/<str:poster_type>/",
        views.get_poster_with_logo,
        name="get_poster_with_logo",
    ),
    path("save-logo-config/", views.save_logo_config, name="save_logo_config"),
    path("reset-logo-config/", views.reset_logo_config, name="reset_logo_config"),
    # --- AUTHENTICATION & SUPERUSER ---
    path("login/", views.custom_login_view, name="login"),
    path("logout/", views.custom_logout, name="logout"),
    path("accounts/profile/", views.custom_login_redirect, name="login_redirect"),
    path("login-redirect/", views.custom_login_redirect, name="custom_login_redirect"),
    path("superuser/dashboard/", views.superuser_dashboard, name="superuser_dashboard"),
    # --- CERTIFICATE ---
    path(
        "certificate/<str:course_type>/",
        views.download_certificate,
        name="download_certificate",
    ),
    path("402/", views.custom_402, name="402"),
    # --- ACCOUNTS PORTAL ---
    path("accounts-portal/login/", views.accounts_login_view, name="accounts_login"),
    path(
        "accounts-portal/dashboard/",
        views.accounts_dashboard_view,
        name="accounts_dashboard",
    ),
    path("accounts-portal/logout/", views.accounts_logout, name="accounts_logout"),
    path("hr/logout/", views.hr_logout, name="hr_logout"),
    path("training/logout/", views.training_logout, name="training_logout"),
    path("session/tab-close/", views.tab_close_logout, name="tab_close_logout"),
    path(
        "accounts-portal/save-email-templates/",
        views.accounts_save_email_templates_view,
        name="accounts_save_email_templates",
    ),
    path(
        "billing/trigger-tier-email/",
        views.trigger_tier_email_view,
        name="trigger_tier_email",
    ),
    path(
        "billing/submit-payment/<int:registration_id>/",
        views.submit_payment_view,
        name="submit_payment",
    ),
]
