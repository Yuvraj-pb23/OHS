from django.urls import path
from . import views

urlpatterns = [
    path("pocso-registration/", views.pocso_registration_view, name="pocso_registration"),
    path("pocso-billing/", views.pocso_billing_view, name="pocso_billing"),
    path("pocso-individual-info/", views.pocso_i, name="pocso_i_page"),
    path("pocso-company-info/", views.pocso_c, name="pocso_c_page"),
    path("pocso_assessment/", views.pocso_assessment, name="pocso_assessment"),
    path("tutorial/pocso-act/", views.pocso_act_page, name="pocso_act_page"),
    path("tutorial/pocso-act-legacy/", views.pocso_act_page, name="pocso_act"),
    path("tutorial/pocso-act-corp/", views.pocso_act_page_corp, name="pocso_act_page_corp"),
    path("accounts-portal/save-pocso-pricing/", views.accounts_save_pocso_pricing_view, name="accounts_save_pocso_pricing"),
    path("accounts-portal/verify-pocso-payment/<int:registration_id>/", views.accounts_verify_pocso_payment_view, name="accounts_verify_pocso_payment"),
    path("accounts-portal/reject-pocso-payment/<int:registration_id>/", views.accounts_reject_pocso_payment_view, name="accounts_reject_pocso_payment"),
    path("accounts-portal/pocso-registration/<int:registration_id>/", views.accounts_pocso_registration_detail_view, name="accounts_pocso_registration_detail"),
]
