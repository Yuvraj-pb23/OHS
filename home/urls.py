from django.contrib import admin
from django.urls import path
from home import views
from django.contrib.auth import views as auth_views

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
    path("posh_T/", views.posh_T, name="posh_T"),
    path("workplace/", views.workplace, name="workplace"),
    path("legal/", views.legal, name="legal"),
    path("blogdata/", views.blogdata, name="blogdata"),
    path("why_choose_ohs/", views.why_choose_ohs, name="why_choose_ohs"),
    path("posh-compliance/", views.posh_compliance, name="posh_compliance"),
    # --- MAIN TUTORIAL LANDING ---
    path("tutorial/", views.tutorial_view, name="tutorial"),
    # --- INTERMEDIATE COURSE INFO PAGE (NEW) ---
    path("posh-info/", views.posh_c, name="posh_c_page"),

    # --- MAIN TUTORIAL / TRAINING LANDING ---
    path('tutorial/', views.tutorial_view, name='tutorial'),

    # --- INTERMEDIATE COURSE INFO PAGES ---
    path('posh-individual-info/', views.posh_i, name='posh_i_page'),
    path('posh-company-info/', views.posh_c, name='posh_c_page'),
    path('pocso-individual-info/', views.pocso_i, name='pocso_i_page'),
    path('pocso-company-info/', views.pocso_c, name='pocso_c_page'),

    # --- ASSESSMENTS ---
    path("posh_assessment/", views.posh_assessment, name="posh_assessment"),
    path("pocso_assessment/", views.pocso_assessment, name="pocso_assessment"),
    # --- SECURE TRAINING PAGES (Accessed after login/subscription) ---
    path("tutorial/posh-act/", views.posh_act_page, name="posh_act_page"),
    path("tutorial/pocso-act/", views.pocso_act_page, name="pocso_act_page"),
    # Note: You had a duplicate path for pocso earlier in your code,
    # ensuring backward compatibility with 'pocso_act' name if used elsewhere:
    path("tutorial/pocso-act-legacy/", views.pocso_act_page, name="pocso_act"),
    path('posh_assessment/', views.posh_assessment, name='posh_assessment'),
    path('pocso_assessment/', views.pocso_assessment, name='pocso_assessment'),

    # --- SECURE TRAINING PAGES ---
    path('tutorial/posh-act/', views.posh_act_page, name='posh_act_page'),
    path('tutorial/pocso-act/', views.pocso_act_page, name='pocso_act_page'),
    path('tutorial/pocso-act-legacy/', views.pocso_act_page, name='pocso_act'),

    # --- CHATBOT ---
    path("chat/", views.chatbot_response, name="chatbot_response"),
    
    # --- AJAX API for Training ---
    path("ajax/update-watch-time/", views.update_watch_time, name="update_watch_time"),
    path("ajax/mod-complete/<int:module_id>/", views.mod_complete, name="mod_complete"),

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
    # --- COMPANY DASHBOARD & MANAGEMENT ---
    path("dashboard/company/", views.company_dashboard, name="company_dashboard"),
    path("dashboard/add-employee/", views.add_employee, name="add_employee"),
    path(
        "download-template/",
        views.download_employee_template,
        name="download_employee_template",
    ),
    path("upload-bulk/", views.upload_employee_bulk, name="upload_employee_bulk"),
    # --- AUTHENTICATION & SUPERUSER ---
    path(
        "login/", auth_views.LoginView.as_view(template_name="login.html"), name="login"
    ),
    path("accounts/profile/", views.custom_login_redirect, name="login_redirect"),
    path("login-redirect/", views.custom_login_redirect, name="custom_login_redirect"),
    path("superuser/dashboard/", views.superuser_dashboard, name="superuser_dashboard"),
    path('dashboard/company/', views.company_dashboard, name='company_dashboard'),
    path('dashboard/add-employee/', views.add_employee, name='add_employee'),
    path('download-template/', views.download_employee_template, name='download_employee_template'),
    path('upload-bulk/', views.upload_employee_bulk, name='upload_employee_bulk'),

    # --- AUTHENTICATION ---
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='home'), name='logout'),
    path('accounts/profile/', views.custom_login_redirect, name='login_redirect'),
    path('login-redirect/', views.custom_login_redirect, name='custom_login_redirect'),
    
    # --- SUPERUSER ---
    path('superuser/dashboard/', views.superuser_dashboard, name='superuser_dashboard'),
    path('admin/', admin.site.urls),
]
