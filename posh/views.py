import csv
import io
import json
import logging
import os

logger = logging.getLogger(__name__)
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.db.models import Q, Sum
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from PIL import Image


from home.models import (
    AssessmentProgress,
    DailyActivity,
    EmailTemplate,
    ModuleProgress,
    Organization,
    OrganizationMember,
    POSHRegistration,
    PosterLogoConfig,
    POSHPricingConfig,
    Subscription,
    SubscriptionPlan,
    TrainingModule,
    User,
    POSHPolicy,
)


def posh_video_source(request):
    """Redirects to the POSH training video URL stored in settings."""
    return redirect(settings.POSH_TRAINING_VIDEO_URL)

@login_required(login_url="login")
def posh_act_page(request):
    user = request.user
    # Redirect corporate employees or HR acting as employees to the corporate dashboard
    if user.is_authenticated:
        if user.account_type == "EMPLOYEE" or request.session.get("hr_as_employee"):
            return redirect("posh_act_page_corp")

    has_access = Subscription.objects.filter(
        Q(user=user) | Q(organization__organizationmember__user=user),
        status="ACTIVE",
        plan__type__in=["POSH", "BOTH"],
    ).exists()

    if not has_access:
        messages.error(request, "Access Denied: Subscription Required.")
        return redirect("tutorial")

    # 1. Fetch Modules
    modules = TrainingModule.objects.filter(module_type="POSH").order_by("order")

    # 2. Fetch User Progress
    progress_map = {}
    completed_count = 0

    # Initialize progress for all modules if not exists
    for mod in modules:
        prog, created = ModuleProgress.objects.get_or_create(user=user, module=mod)
        progress_map[mod.id] = {
            "is_completed": prog.is_completed,
            "last_position": getattr(prog, "last_position", 0.0),
        }
        if prog.is_completed:
            completed_count += 1

    # 3. Calculate Overall Status
    total_modules = modules.count()
    percent_complete = (
        int((completed_count / total_modules) * 100) if total_modules > 0 else 0
    )

    # 4. Determine Locked Status & Split
    video_list = []
    ppt_list = []

    # Process Videos Sequence
    # UPDATED: Include if it has a video_file (priority), regardless of PPT presence
    video_modules = [m for m in modules if m.video_file]
    previous_completed = True
    for mod in video_modules:
        prog_data = progress_map.get(mod.id, {"is_completed": False, "last_position": 0.0})
        is_completed = prog_data["is_completed"]
        last_position = prog_data["last_position"]
        is_locked = not previous_completed

        item = {
            "id": mod.id,
            "title": mod.title,
            "is_completed": is_completed,
            "is_locked": is_locked,
            "thumb": mod.thumbnail.url if mod.thumbnail else "",
            "src": (
                mod.video_file.url
                if mod.video_file and os.path.exists(mod.video_file.path)
                else "/posh-video-source/"
            ),
            # UPDATED: Use new hardcoded path for demo video
            "url": "https://docs.google.com/presentation/d/1wb69ZQ4oYGYxOxzjNaTQP5bIfsB3tIKi/embed",
            "duration": mod.duration_seconds,
            "last_position": last_position,
        }
        video_list.append(item)
        previous_completed = is_completed

    # Process PPT Sequence
    ppt_modules = [m for m in modules if m.ppt_file and not m.video_file]

    # UPDATED: Only include if it has PPT AND NO Video (to prevent duplicates)
    previous_completed = True
    for mod in ppt_modules:
        prog_data = progress_map.get(mod.id, {"is_completed": False, "last_position": 0.0})
        is_completed = prog_data["is_completed"]
        is_locked = not previous_completed

        item = {
            "id": mod.id,
            "title": mod.title,
            "is_completed": is_completed,
            "is_locked": is_locked,
            "thumb": mod.thumbnail.url if mod.thumbnail else "",
            "src": "",
            # UPDATED: Use new hardcoded path for PPT
            "url": "https://docs.google.com/presentation/d/1wb69ZQ4oYGYxOxzjNaTQP5bIfsB3tIKi/embed",
            "duration": mod.duration_seconds,
        }
        ppt_list.append(item)
        previous_completed = is_completed

    # 5. Daily Activity Stats for Chart (Last 7 days)
    today = timezone.now().date()

    # Calculate Total Study Time (Lifetime)
    total_mins_agg = (
        DailyActivity.objects.filter(user=user).aggregate(Sum("minutes_watched"))[
            "minutes_watched__sum"
        ]
        or 0
    )
    total_secs_agg = (
        DailyActivity.objects.filter(user=user).aggregate(Sum("seconds_watched"))[
            "seconds_watched__sum"
        ]
        or 0
    )
    total_seconds_watched = (total_mins_agg * 60) + total_secs_agg

    last_7_days = [(today - timedelta(days=i)) for i in range(6, -1, -1)]
    chart_labels = [d.strftime("%a") for d in last_7_days]
    chart_data = []

    for d in last_7_days:
        activity = DailyActivity.objects.filter(user=user, date=d).first()
        chart_data.append(activity.minutes_watched if activity else 0)

    has_organization = False
    org_logo_url = None
    membership = OrganizationMember.objects.filter(user=user).first()
    if membership:
        has_organization = True
        org = membership.organization
        if org.logo:
            org_logo_url = org.logo.url

    context = {
        "video_modules": video_list,
        "ppt_modules": ppt_list,
        "percent_complete": percent_complete,
        "completed_count": completed_count,
        "total_modules": total_modules,
        "chart_labels": json.dumps(chart_labels),
        "chart_data": json.dumps(chart_data),
        # Remove duplicate key if present
        "total_seconds_watched": total_seconds_watched,
        "formatted_total_time": (
            f"{total_seconds_watched // 3600:02}:"
            f"{(total_seconds_watched % 3600) // 60:02}:"
            f"{total_seconds_watched % 60:02}"
        ),
        "is_final_quiz_passed": AssessmentProgress.objects.filter(
            user=user, assessment_type="POSH", is_passed=True
        ).exists(),
        "posh_video_url": "/posh-video-source/",
        "has_organization": has_organization,
        "org_logo_url": org_logo_url,
    }

    return render(request, "posh/posh_individual_training.html", context)

@login_required(login_url="login")
def posh_act_page_corp(request):
    """Same as posh_act_page but for company employees - no certificate option."""
    user = request.user
    has_access = Subscription.objects.filter(
        Q(user=user) | Q(organization__organizationmember__user=user),
        status="ACTIVE",
        plan__type__in=["POSH", "BOTH"],
    ).exists()

    if not has_access:
        messages.error(request, "Access Denied: Subscription Required.")
        return redirect("tutorial")

    # 1. Fetch Modules
    modules = TrainingModule.objects.filter(module_type="POSH").order_by("order")

    # 2. Fetch User Progress
    progress_map = {}

    # Initialize progress for all modules if not exists
    for mod in modules:
        prog, created = ModuleProgress.objects.get_or_create(user=user, module=mod)
        progress_map[mod.id] = {
            "is_completed": prog.is_completed,
            "last_position": getattr(prog, "last_position", 0.0),
        }

    # Only video and quiz modules are part of corp training flow now.
    visible_modules = [
        m
        for m in modules
        if m.video_file
        or (m.ppt_file and not m.video_file and "quiz" in m.title.lower())
    ]
    completed_count = sum(1 for m in visible_modules if progress_map.get(m.id, {}).get("is_completed", False))

    # 3. Calculate Overall Status
    total_modules = len(visible_modules)
    percent_complete = (
        int((completed_count / total_modules) * 100) if total_modules > 0 else 0
    )

    # 4. Determine Locked Status & Split
    video_list = []
    ppt_list = []

    # Process Videos Sequence
    # UPDATED: Include if it has a video_file (priority), regardless of PPT presence
    video_modules = [m for m in modules if m.video_file]
    previous_completed = True
    for mod in video_modules:
        prog_data = progress_map.get(mod.id, {"is_completed": False, "last_position": 0.0})
        is_completed = prog_data["is_completed"]
        last_position = prog_data["last_position"]
        is_locked = not previous_completed

        item = {
            "id": mod.id,
            "title": mod.title,
            "is_completed": is_completed,
            "is_locked": is_locked,
            "thumb": mod.thumbnail.url if mod.thumbnail else "",
            "src": (
                mod.video_file.url
                if mod.video_file and os.path.exists(mod.video_file.path)
                else settings.POSH_TRAINING_VIDEO_URL
            ),
            # UPDATED: Use new hardcoded path for demo video
            "url": "https://docs.google.com/presentation/d/1wb69ZQ4oYGYxOxzjNaTQP5bIfsB3tIKi/embed",
            "duration": mod.duration_seconds,
            "last_position": last_position,
        }
        video_list.append(item)
        previous_completed = is_completed

    # PPT modules intentionally excluded for corp flow (video + quiz only).

    # Move Practice Quiz into video_list (shown under Video Modules tab, below the video)
    quiz_modules = [
        m
        for m in modules
        if m.ppt_file and not m.video_file and "quiz" in m.title.lower()
    ]
    for mod in quiz_modules:
        prog_data = progress_map.get(mod.id, {"is_completed": False, "last_position": 0.0})
        is_completed = prog_data["is_completed"]
        # Lock the quiz until all video modules are completed
        all_videos_done = all(progress_map.get(v.id, {}).get("is_completed", False) for v in video_modules)
        is_locked = not all_videos_done

        item = {
            "id": mod.id,
            "title": mod.title,
            "is_completed": is_completed,
            "is_locked": is_locked,
            "thumb": mod.thumbnail.url if mod.thumbnail else "",
            "url": "https://docs.google.com/presentation/d/1wb69ZQ4oYGYxOxzjNaTQP5bIfsB3tIKi/embed",
            "is_quiz": True,
            "duration": mod.duration_seconds,
        }
        video_list.append(item)

    # 5. Daily Activity Stats for Chart (Last 7 days)
    today = timezone.now().date()

    # Calculate Total Study Time (Lifetime)
    total_mins_agg = (
        DailyActivity.objects.filter(user=user).aggregate(Sum("minutes_watched"))[
            "minutes_watched__sum"
        ]
        or 0
    )
    total_secs_agg = (
        DailyActivity.objects.filter(user=user).aggregate(Sum("seconds_watched"))[
            "seconds_watched__sum"
        ]
        or 0
    )
    total_seconds_watched = (total_mins_agg * 60) + total_secs_agg

    last_7_days = [(today - timedelta(days=i)) for i in range(6, -1, -1)]
    chart_labels = [d.strftime("%a") for d in last_7_days]
    chart_data = []

    for d in last_7_days:
        activity = DailyActivity.objects.filter(user=user, date=d).first()
        chart_data.append(activity.minutes_watched if activity else 0)

    context = {
        "video_modules": video_list,
        "ppt_modules": ppt_list,
        "percent_complete": percent_complete,
        "completed_count": completed_count,
        "total_modules": total_modules,
        "chart_labels": json.dumps(chart_labels),
        "chart_data": json.dumps(chart_data),
        # Remove duplicate key if present
        "total_seconds_watched": total_seconds_watched,
        "formatted_total_time": (
            f"{total_seconds_watched // 3600:02}:"
            f"{(total_seconds_watched % 3600) // 60:02}:"
            f"{total_seconds_watched % 60:02}"
        ),
        "is_final_quiz_passed": AssessmentProgress.objects.filter(
            user=user, assessment_type="POSH", is_passed=True
        ).exists(),
        "is_company_employee": True,
        "posh_video_url": settings.POSH_TRAINING_VIDEO_URL,
    }

    return render(request, "posh/posh_employee_training.html", context)

def posh_T(request):
    return render(request, "posh/posh_training_overview.html")

def blogdata(request):
    return render(request, "posh/posh_training_article.html")

def posh_compliance(request):
    return render(request, "posh_compliance.html")

def posh_assessment(request):
    return render(request, "posh/posh_assessment.html")

def posh_c(request):
    return render(request, "posh/posh_company_details.html")

def posh_i(request):
    return render(request, "posh/posh_individual_details.html")

def get_posh_pricing_context(registration):
    """Refactored helper to calculate POSH billing context for both billing_view and admin review"""
    from home.utils import get_posh_billing_data

    billing_data = get_posh_billing_data(registration)

    # Add view-specific context that isn't in billing_data
    config = (
        POSHPricingConfig.objects.filter(is_active=True).order_by("-updated_at").first()
    )
    if not config:
        config = POSHPricingConfig()

    emp_count = registration.employee_count
    if emp_count <= config.price_tier_0_max:
        tier_label = f"Tier 1 (1-{config.price_tier_0_max})"
    elif emp_count <= config.price_tier_1_max:
        tier_label = f"Tier 2 ({config.price_tier_0_max + 1}-{config.price_tier_1_max})"
    elif emp_count <= config.price_tier_2_max:
        tier_label = f"Tier 3 ({config.price_tier_1_max + 1}-{config.price_tier_2_max})"
    elif emp_count <= config.price_tier_3_max:
        tier_label = f"Tier 4 ({config.price_tier_2_max + 1}-{config.price_tier_3_max})"
    else:
        tier_label = f"Tier 5 ({config.price_tier_3_max}+)"

    per_employee_rate = (
        billing_data["training_total"] / emp_count if emp_count > 0 else 0
    )

    return {
        "reg": registration,
        "registration": registration,
        "addon_fees": billing_data["addon_fees"],
        "subtotal": billing_data["subtotal"],
        "tax": billing_data["gst_amount"],
        "total": billing_data["total_amount"],
        "total_tier_3": billing_data["total_amount"],
        "total_tier_2": billing_data["total_amount"],
        "total_tier_1": billing_data["total_amount"],
        "gst_percentage": billing_data["gst_percentage"],
        "company_name": registration.company_name,
        "payment_status": registration.payment_status,
        "tier_label": tier_label,
        "per_emp": per_employee_rate,
        "training_cost": billing_data["training_total"],
    }

def billing_view(request):
    """Calculate and show POSH billing summary with tiered pricing"""
    # Prioritize recent session registration for immediate post-reg experience
    reg_id = request.session.get("last_registration_id")
    registration = (
        POSHRegistration.objects.filter(id=reg_id).first() if reg_id else None
    )

    if not registration and request.user.is_authenticated:
        registration = (
            POSHRegistration.objects.filter(user=request.user)
            .order_by("-created_at")
            .first()
        )

    if not registration:
        return redirect("posh_registration")

    if request.method == "POST":
        registration.payment_status = "PENDING"
        registration.is_paid = False
        registration.save()
        try:
            from home.email_utils import send_interest_email
            send_interest_email(registration, "POSH", request=request)
        except Exception as e:
            logger.warning(f"Failed to send interest email for POSH registration {registration.id}: {e}")
        request.session["registration_submitted"] = True
        return redirect("billing")

    context = get_posh_pricing_context(registration)
    context["registration_submitted"] = request.session.pop("registration_submitted", False)
    return render(request, "posh/posh_billing.html", context)

@login_required(login_url="accounts_login")
def accounts_verify_payment_view(request, registration_id):
    """Mark a registration as verified by the accounts department"""

    if request.user.account_type != "ACCOUNTS" and not request.user.is_superuser:
        return redirect("home")

    registration = get_object_or_404(POSHRegistration, id=registration_id)

    try:
        registration.payment_status = "VERIFIED"
        registration.is_paid = True
        registration.save()

        # Send payment verification email (creates the setup token & link)
        from home.email_utils import send_tiered_email
        send_tiered_email(registration, "PAYMENT_VERIFIED", "POSH")

    except Exception as e:
        logger.warning(
            f"Payment verified but email failed for {registration.company_name}: {e}"
        )
        messages.error(request, f"Error verifying payment: {str(e)}")
        return redirect("accounts_registration_detail", registration_id=registration_id)

    messages.success(request, f"Payment for {registration.company_name} has been verified!", extra_tags="payment_approved")
    return redirect("accounts_registration_detail", registration_id=registration_id)

@login_required(login_url="accounts_login")
def accounts_reject_payment_view(request, registration_id):
    """Reject a payment and return it to pending status"""
    if request.user.account_type != "ACCOUNTS" and not request.user.is_superuser:
        return redirect("home")

    registration = get_object_or_404(POSHRegistration, id=registration_id)
    registration.payment_status = "REJECTED"
    registration.save()

    # Send payment rejection email
    try:
        from home.email_utils import send_payment_rejected_email
        send_payment_rejected_email(registration)
    except Exception as e:
        logger.warning(
            f"Payment rejection email failed for {registration.company_name}: {e}"
        )

    messages.warning(request, f"Payment for {registration.company_name} rejected.", extra_tags="payment_rejected")
    return redirect("accounts_registration_detail", registration_id=registration_id)

@login_required(login_url="accounts_login")
def accounts_registration_detail_view(request, registration_id):
    """Full registration detail for billing review with calculated context"""
    if request.user.account_type != "ACCOUNTS" and not request.user.is_superuser:
        return redirect("home")

    registration = get_object_or_404(POSHRegistration, id=registration_id)
    context = get_posh_pricing_context(registration)
    return render(request, "posh/accounts_posh_registration_detail.html", context)

@login_required(login_url="accounts_login")
def accounts_save_pricing_view(request):
    """Update the POSH pricing matrix with per-tier add-on fees"""
    if request.user.account_type != "ACCOUNTS" and not request.user.is_superuser:
        return redirect("home")

    if request.method == "POST":
        from decimal import Decimal

        def to_dec(val, default="0.00"):
            try:
                return Decimal(str(val))
            except Exception:
                return Decimal(default)

        p = request.POST.get

        try:
            # Create a NEW config as the active one
            config = POSHPricingConfig(
                base_platform_fee=to_dec(p("base_platform_fee", 5000.00)),
                gst_percentage=to_dec(p("gst_percentage", 18.00)),
                price_tier_0_rate=to_dec(p("price_tier_0_rate", 200.00)),
                price_tier_1_rate=to_dec(p("price_tier_1_rate", 163.00)),
                price_tier_2_rate=to_dec(p("price_tier_2_rate", 154.00)),
                price_tier_3_rate=to_dec(p("price_tier_3_rate", 145.00)),
                price_tier_4_rate=to_dec(p("price_tier_4_rate", 127.00)),
                fee_no_posh_policy_t0=to_dec(p("fee_no_posh_policy_t0", 0.00)),
                fee_no_posh_policy_t1=to_dec(p("fee_no_posh_policy_t1", 0.00)),
                fee_no_posh_policy_t2=to_dec(p("fee_no_posh_policy_t2", 0.00)),
                fee_no_posh_policy_t3=to_dec(p("fee_no_posh_policy_t3", 0.00)),
                fee_no_posh_policy_t4=to_dec(p("fee_no_posh_policy_t4", 0.00)),
                fee_no_ic_t0=to_dec(p("fee_no_ic_t0", 0.00)),
                fee_no_ic_t1=to_dec(p("fee_no_ic_t1", 0.00)),
                fee_no_ic_t2=to_dec(p("fee_no_ic_t2", 0.00)),
                fee_no_ic_t3=to_dec(p("fee_no_ic_t3", 0.00)),
                fee_no_ic_t4=to_dec(p("fee_no_ic_t4", 0.00)),
                fee_no_external_member_t0=to_dec(p("fee_no_external_member_t0", 0.00)),
                fee_no_external_member_t1=to_dec(p("fee_no_external_member_t1", 0.00)),
                fee_no_external_member_t2=to_dec(p("fee_no_external_member_t2", 0.00)),
                fee_no_external_member_t3=to_dec(p("fee_no_external_member_t3", 0.00)),
                fee_no_external_member_t4=to_dec(p("fee_no_external_member_t4", 0.00)),
                fee_ic_requested_online_t0=to_dec(
                    p("fee_ic_requested_online_t0", 0.00)
                ),
                fee_ic_requested_online_t1=to_dec(
                    p("fee_ic_requested_online_t1", 0.00)
                ),
                fee_ic_requested_online_t2=to_dec(
                    p("fee_ic_requested_online_t2", 0.00)
                ),
                fee_ic_requested_online_t3=to_dec(
                    p("fee_ic_requested_online_t3", 0.00)
                ),
                fee_ic_requested_online_t4=to_dec(
                    p("fee_ic_requested_online_t4", 0.00)
                ),
                fee_ic_requested_physical_t0=to_dec(
                    p("fee_ic_requested_physical_t0", 0.00)
                ),
                fee_ic_requested_physical_t1=to_dec(
                    p("fee_ic_requested_physical_t1", 0.00)
                ),
                fee_ic_requested_physical_t2=to_dec(
                    p("fee_ic_requested_physical_t2", 0.00)
                ),
                fee_ic_requested_physical_t3=to_dec(
                    p("fee_ic_requested_physical_t3", 0.00)
                ),
                fee_ic_requested_physical_t4=to_dec(
                    p("fee_ic_requested_physical_t4", 0.00)
                ),
                fee_ic_requested_virtual_t0=to_dec(
                    p("fee_ic_requested_virtual_t0", 0.00)
                ),
                fee_ic_requested_virtual_t1=to_dec(
                    p("fee_ic_requested_virtual_t1", 0.00)
                ),
                fee_ic_requested_virtual_t2=to_dec(
                    p("fee_ic_requested_virtual_t2", 0.00)
                ),
                fee_ic_requested_virtual_t3=to_dec(
                    p("fee_ic_requested_virtual_t3", 0.00)
                ),
                fee_ic_requested_virtual_t4=to_dec(
                    p("fee_ic_requested_virtual_t4", 0.00)
                ),
                fee_ic_history_21_23_t0=to_dec(p("fee_ic_history_21_23_t0", 0.00)),
                fee_ic_history_21_23_t1=to_dec(p("fee_ic_history_21_23_t1", 0.00)),
                fee_ic_history_21_23_t2=to_dec(p("fee_ic_history_21_23_t2", 0.00)),
                fee_ic_history_21_23_t3=to_dec(p("fee_ic_history_21_23_t3", 0.00)),
                fee_ic_history_21_23_t4=to_dec(p("fee_ic_history_21_23_t4", 0.00)),
                fee_ic_history_24_25_t0=to_dec(p("fee_ic_history_24_25_t0", 0.00)),
                fee_ic_history_24_25_t1=to_dec(p("fee_ic_history_24_25_t1", 0.00)),
                fee_ic_history_24_25_t2=to_dec(p("fee_ic_history_24_25_t2", 0.00)),
                fee_ic_history_24_25_t3=to_dec(p("fee_ic_history_24_25_t3", 0.00)),
                fee_ic_history_24_25_t4=to_dec(p("fee_ic_history_24_25_t4", 0.00)),
                fee_ic_history_other_t0=to_dec(p("fee_ic_history_other_t0", 0.00)),
                fee_ic_history_other_t1=to_dec(p("fee_ic_history_other_t1", 0.00)),
                fee_ic_history_other_t2=to_dec(p("fee_ic_history_other_t2", 0.00)),
                fee_ic_history_other_t3=to_dec(p("fee_ic_history_other_t3", 0.00)),
                fee_ic_history_other_t4=to_dec(p("fee_ic_history_other_t4", 0.00)),
                fee_not_she_box_t0=to_dec(p("fee_not_she_box_t0", 0.00)),
                fee_not_she_box_t1=to_dec(p("fee_not_she_box_t1", 0.00)),
                fee_not_she_box_t2=to_dec(p("fee_not_she_box_t2", 0.00)),
                fee_not_she_box_t3=to_dec(p("fee_not_she_box_t3", 0.00)),
                fee_not_she_box_t4=to_dec(p("fee_not_she_box_t4", 0.00)),
                fee_nodal_officer_t0=to_dec(p("fee_nodal_officer_t0", 0.00)),
                fee_nodal_officer_t1=to_dec(p("fee_nodal_officer_t1", 0.00)),
                fee_nodal_officer_t2=to_dec(p("fee_nodal_officer_t2", 0.00)),
                fee_nodal_officer_t3=to_dec(p("fee_nodal_officer_t3", 0.00)),
                fee_nodal_officer_t4=to_dec(p("fee_nodal_officer_t4", 0.00)),
                created_by=request.user,
                is_active=True,
            )
            config.save()

            # Now deactivate others (safely)
            POSHPricingConfig.objects.exclude(id=config.id).update(is_active=False)

            request.session["pricing_saved"] = True
            # messages.success(request, "POSH Billing Engine updated successfully!")
        except Exception as e:
            messages.error(request, f"Error updating pricing: {str(e)}")

    from django.urls import reverse

    return redirect(f"{reverse('accounts_dashboard')}?active_tab=pricing")

def posh_registration_view(request):
    """Handle POSH compliance registration submission"""
    if request.method == "POST":
        data = request.POST

        # Verify custom CAPTCHA
        captcha_code = request.POST.get("captcha", "").strip()
        session_captcha = request.session.get("captcha_text", "")
        if not session_captcha or captcha_code.lower() != session_captcha.lower():
            messages.error(request, "CAPTCHA verification failed. Please try again.")
            return redirect("posh_registration")

        # Determine IC training mode from hidden fields or radio
        ic_training_mode = data.get("requested_ic_training_mode")
        expert_led_type = data.get("requested_expert_led_type")

        # Join multiple office locations if present
        cities = request.POST.getlist("city")
        city_str = ", ".join([c.strip() for c in cities if c.strip()])

        reg = POSHRegistration(
            contact_person=data.get("contact_person"),
            designation=data.get("designation"),
            city=city_str,
            phone=data.get("phone"),
            email=data.get("email"),
            website=data.get("website"),
            company_name=data.get("company_name"),
            employee_count=int(data.get("employee_count", 0)),
            trained_employee_count=0,  # Defaulting to 0 for now as it's required by model
            last_training_year=data.get("last_training_year"),
            has_posh_policy=data.get("has_posh_policy") == "yes",
            has_ic=data.get("has_ic") == "yes",
            ic_specialized_training=data.get("ic_specialized_training") == "yes",
            ic_last_training_year=data.get("ic_last_training_year"),
            require_ic_training=data.get("require_ic_training") == "yes",
            requested_ic_training_mode=ic_training_mode,
            requested_expert_led_type=expert_led_type,
            external_member_support=data.get("external_member_support") == "yes",
            require_external_member_support=data.get("require_external_member_support")
            == "yes",
            she_box_registered=data.get("she_box_registered") == "yes",
            nodal_officer_appointed=data.get("nodal_officer_appointed") == "yes",
            annual_report_submitted=data.get("annual_report_submitted") == "yes",
            require_nodal_officer_support=data.get("require_nodal_officer_support")
            == "yes",
        )
        reg.save()
        request.session["last_registration_id"] = reg.id
        
        # Send interest email immediately upon registration form submission
        try:
            from home.email_utils import send_interest_email
            send_interest_email(reg, "POSH", request=request)
        except Exception as e:
            logger.warning(f"Failed to send interest email for POSH registration {reg.id}: {e}")
            
        request.session["registration_submitted"] = True
        return redirect("billing")

    registration = None
    if request.GET.get("edit") == "true":
        if request.user.is_authenticated:
            registration = (
                POSHRegistration.objects.filter(user=request.user)
                .order_by("-created_at")
                .first()
            )
        else:
            reg_id = request.session.get("last_registration_id")
            if reg_id:
                registration = POSHRegistration.objects.filter(id=reg_id).first()

    return render(request, "posh/posh_registration.html", {"registration": registration})

@login_required(login_url="login")
def generate_posh_policy(request):
    if request.method == "POST":
        user = request.user
        membership = OrganizationMember.objects.filter(user=user, role="ADMIN").first()
        if not membership:
            messages.error(request, "Access Denied. Admin only.")
            return redirect("tutorial")
            
        org = membership.organization
        
        # Get POST parameters
        company_name = request.POST.get("companyName", "").strip()
        registered_address = request.POST.get("registeredAddress", "").strip()
        hr_email = request.POST.get("hrEmail", "").strip()
        posh_email = request.POST.get("poshEmail", "").strip()
        effective_date = request.POST.get("effectiveDate", "").strip()
        district_name = request.POST.get("districtName", "").strip()
        
        po_name = request.POST.get("poName", "").strip()
        po_email = request.POST.get("poEmail", "").strip()
        po_phone = request.POST.get("poPhone", "").strip()
        
        m1_name = request.POST.get("m1Name", "").strip()
        m1_email = request.POST.get("m1Email", "").strip()
        m1_phone = request.POST.get("m1Phone", "").strip()
        
        m2_name = request.POST.get("m2Name", "").strip()
        m2_email = request.POST.get("m2Email", "").strip()
        m2_phone = request.POST.get("m2Phone", "").strip()

        m3_name = request.POST.get("m3Name", "").strip()
        m3_email = request.POST.get("m3Email", "").strip()
        m3_phone = request.POST.get("m3Phone", "").strip()

        m4_name = request.POST.get("m4Name", "").strip()
        m4_email = request.POST.get("m4Email", "").strip()
        m4_phone = request.POST.get("m4Phone", "").strip()
        
        ext_name = request.POST.get("extName", "").strip()
        ext_email = request.POST.get("extEmail", "").strip()
        ext_phone = request.POST.get("extPhone", "").strip()
        
        hr_head_name = request.POST.get("hrHeadName", "").strip()

        escalation_officer_name = request.POST.get("escalationName", "").strip()
        escalation_officer_designation = request.POST.get("escalationDesignation", "").strip()
        
        approver_name = request.POST.get("approverName", "").strip()
        approver_designation = request.POST.get("approverDesignation", "").strip()
        approval_date = request.POST.get("approvalDate", "").strip()
        
        company_logo = request.FILES.get("companyLogo")
        
        # --- STRICT BACKEND VALIDATION ---
        errors = []

        import re
        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError
        from datetime import datetime, date
        import os

        def is_valid_email(email_str):
            try:
                validate_email(email_str)
                return True
            except ValidationError:
                return False

        def is_valid_phone(phone_str):
            return bool(re.match(r"^\+?([0-9]{1,3})?[-. ]?([0-9]{10})$", phone_str))

        # 1. Check required text lengths and min lengths
        if len(company_name) < 3:
            errors.append("Company Name must be at least 3 characters.")
        if len(registered_address) < 10:
            errors.append("Registered Office Address must be at least 10 characters.")
        if len(district_name) < 2:
            errors.append("District must be at least 2 characters.")
            
        # 2. Email uniqueness and syntax checks
        if hr_email == posh_email:
            errors.append("HR Email and POSH Email must be different.")

        for label, email in [
            ("HR Email", hr_email),
            ("POSH Email", posh_email),
            ("Presiding Officer Email", po_email),
            ("IC Member 1 Email", m1_email),
            ("IC Member 2 Email", m2_email),
            ("IC Member 3 Email", m3_email),
            ("IC Member 4 Email", m4_email),
            ("External Member Email", ext_email),
        ]:
            if not email or not is_valid_email(email):
                errors.append(f"Invalid format for {label}.")

        # 3. Phone format checks
        for label, phone in [
            ("Presiding Officer Phone", po_phone),
            ("IC Member 1 Phone", m1_phone),
            ("IC Member 2 Phone", m2_phone),
            ("IC Member 3 Phone", m3_phone),
            ("IC Member 4 Phone", m4_phone),
            ("External Member Phone", ext_phone),
        ]:
            if not phone or not is_valid_phone(phone):
                errors.append(f"Invalid format for {label} (must be a valid 10-digit mobile number).")

        # 4. Strict name sanitization checks (min 3 chars, no numbers)
        for label, name in [
            ("Presiding Officer Name", po_name),
            ("IC Member 1 Name", m1_name),
            ("IC Member 2 Name", m2_name),
            ("IC Member 3 Name", m3_name),
            ("IC Member 4 Name", m4_name),
            ("External Member Name", ext_name),
            ("HR Head Name", hr_head_name),
            ("Escalation Officer Name", escalation_officer_name),
            ("Approver Name", approver_name),
        ]:
            if len(name) < 3:
                errors.append(f"{label} must be at least 3 characters.")
            elif any(char.isdigit() for char in name):
                errors.append(f"{label} cannot contain numeric digits.")

        if len(approver_designation) < 2:
            errors.append("Approver Designation must be at least 2 characters.")
        if len(escalation_officer_designation) < 2:
            errors.append("Escalation Officer Designation must be at least 2 characters.")

        # 5. Date logic check
        try:
            eff_dt = datetime.strptime(effective_date, "%Y-%m-%d").date()
            max_future = date.today().replace(year=date.today().year + 1)
            if eff_dt > max_future:
                errors.append("Policy Effective Date cannot be more than 1 year in the future.")
        except ValueError:
            errors.append("Invalid Effective Date format.")

        try:
            app_dt = datetime.strptime(approval_date, "%Y-%m-%d").date()
            if app_dt > date.today():
                errors.append("Policy Approval Date cannot be in the future.")
        except ValueError:
            errors.append("Invalid Approval Date format.")

        # 6. Company Logo Validation (If uploaded)
        if company_logo:
            valid_exts = [".png", ".jpg", ".jpeg", ".webp"]
            ext = os.path.splitext(company_logo.name)[1].lower()
            if ext not in valid_exts:
                errors.append("Company Logo must be a PNG, JPG, JPEG, or WEBP image.")
            if company_logo.size > 2 * 1024 * 1024:
                errors.append("Company Logo size exceeds 2MB.")
        else:
            # Check if there is already an existing policy with a logo
            existing_policy = POSHPolicy.objects.filter(organization=org).first()
            if not existing_policy or not existing_policy.company_logo:
                errors.append("Company Logo is required.")

        # Redirect back if validation fails
        if errors:
            messages.error(request, f"Policy Generation Failed: {', '.join(errors)}")
            return redirect("company_dashboard")

        # Save or update POSHPolicy safely by querying first to avoid database NOT NULL constraint failures on creation
        policy = POSHPolicy.objects.filter(organization=org).first()
        if not policy:
            policy = POSHPolicy(organization=org)
        policy.company_name = company_name
        policy.registered_address = registered_address
        policy.hr_email = hr_email
        policy.posh_email = posh_email
        policy.effective_date = effective_date
        policy.district_name = district_name
        
        policy.po_name = po_name
        policy.po_email = po_email
        policy.po_phone = po_phone
        
        policy.m1_name = m1_name
        policy.m1_email = m1_email
        policy.m1_phone = m1_phone
        
        policy.m2_name = m2_name
        policy.m2_email = m2_email
        policy.m2_phone = m2_phone

        policy.m3_name = m3_name
        policy.m3_email = m3_email
        policy.m3_phone = m3_phone

        policy.m4_name = m4_name
        policy.m4_email = m4_email
        policy.m4_phone = m4_phone
        
        policy.ext_name = ext_name
        policy.ext_email = ext_email
        policy.ext_phone = ext_phone
        
        policy.hr_head_name = hr_head_name

        policy.escalation_officer_name = escalation_officer_name
        policy.escalation_officer_designation = escalation_officer_designation
        
        policy.approver_name = approver_name
        policy.approver_designation = approver_designation
        policy.approval_date = approval_date
        
        if company_logo:
            policy.company_logo = company_logo
            
        policy.save()
        
        messages.success(request, "POSH Policy has been generated successfully!")
        from django.urls import reverse
        return redirect(reverse("company_dashboard") + "?section=policy#policy")
        
    return redirect("company_dashboard")

