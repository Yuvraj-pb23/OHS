from django.contrib import admin
from django.urls import path
from home import views
from django.contrib.auth import views as auth_views
urlpatterns = [
    path("", views.index, name='home'),
    path("about/", views.about, name='about'),
    path("resources/", views.resources, name='resources'),
    path("services/", views.services, name='services'),
    path("blog/", views.blog, name='blog'),
    path("gallery/", views.gallery, name='gallery'),
    path("achievements/", views.achievements, name='achievements'),
    path("footer/", views.footer, name='footer'),
    path("posh_T/", views.posh_T, name='posh_T'),
    path("workplace/", views.workplace, name='workplace'),
    path("legal/", views.legal, name='legal'),
    path("blogdata/", views.blogdata, name='blogdata'),
    path('why_choose_ohs/', views.why_choose_ohs, name='why_choose_ohs'),
    path('posh_assessment/', views.posh_assessment, name='posh_assessment'),
    path('tutorial/pocso-act/', views.pocso_act_page, name='pocso_act'),
    path('pocso_assessment/', views.pocso_assessment, name='pocso_assessment'),

    
    
    # --- CHANGED THIS LINE BACK TO name='tutorial' ---
    path('tutorial/', views.tutorial_view, name='tutorial'),
    
    path('chat/', views.chatbot_response, name='chatbot_response'),
    path("posh-compliance/", views.posh_compliance, name="posh_compliance"),

    # --- NEW PATHS FOR CLICKABLE CARDS ---
    path('tutorial/posh-act/', views.posh_act_page, name='posh_act_page'),
    path('tutorial/pocso-act/', views.pocso_act_page, name='pocso_act_page'),

    # --- NEW PATH FOR SUBSCRIPTION ---
    path('subscription/individual/<str:plan_type>/', views.individual_subscription, name='individual_subscription'),
    
    
    path('subscription/company/<str:plan_type>/', views.company_subscription, name='company_subscription'),
    path('dashboard/company/', views.company_dashboard, name='company_dashboard'),
    
    path('dashboard/company/', views.company_dashboard, name='company_dashboard'),

    path('dashboard/add-employee/', views.add_employee, name='add_employee'),
    path('download-template/', views.download_employee_template, name='download_employee_template'),
    path('upload-bulk/', views.upload_employee_bulk, name='upload_employee_bulk'),
    
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('accounts/profile/', views.custom_login_redirect, name='login_redirect'),
  

]