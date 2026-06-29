from django.urls import path
from . import views

urlpatterns = [
    path("posh_T/", views.posh_T, name="posh_T"),
    path("blogdata/", views.blogdata, name="blogdata"),
    path("posh-compliance/", views.posh_compliance, name="posh_compliance"),
    path("posh-registration/", views.posh_registration_view, name="posh_registration"),
    path("posh-individual-info/", views.posh_i, name="posh_i_page"),
    path("posh-company-info/", views.posh_c, name="posh_c_page"),
    path("posh_assessment/", views.posh_assessment, name="posh_assessment"),
    path("tutorial/posh-act/", views.posh_act_page, name="posh_act_page"),
    path("tutorial/posh-act-corp/", views.posh_act_page_corp, name="posh_act_page_corp"),
    path("posh-video-source/", views.posh_video_source, name="posh_video_source"),
    path("dashboard/company/generate-policy/", views.generate_posh_policy, name="generate_posh_policy"),
    path("billing/", views.billing_view, name="billing"),
    path("accounts-portal/registration/<int:registration_id>/", views.accounts_registration_detail_view, name="accounts_registration_detail"),
    path("accounts-portal/save-pricing/", views.accounts_save_pricing_view, name="accounts_save_pricing"),
    path("accounts-portal/verify-payment/<int:registration_id>/", views.accounts_verify_payment_view, name="accounts_verify_payment"),
    path("accounts-portal/reject-payment/<int:registration_id>/", views.accounts_reject_payment_view, name="accounts_reject_payment"),
]
