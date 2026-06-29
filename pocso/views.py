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
    POCSORegistration,
    PosterLogoConfig,
    POCSOPricingConfig,
    Subscription,
    SubscriptionPlan,
    TrainingModule,
    User,
)


@login_required(login_url="login")
def pocso_act_page(request):
    user = request.user
    # Redirect corporate employees or HR acting as employees to the corporate dashboard
    if user.is_authenticated:
        if user.account_type == "EMPLOYEE" or request.session.get("hr_as_employee"):
            return redirect("pocso_act_page_corp")

    has_access = Subscription.objects.filter(
        Q(user=user) | Q(organization__organizationmember__user=user),
        status="ACTIVE",
        plan__type__in=["POCSO", "BOTH"],
    ).exists()

    if not has_access:
        messages.error(request, "Access Denied: Subscription Required.")
        return redirect("tutorial")

    # 1. Fetch Modules
    modules = TrainingModule.objects.filter(module_type="POCSO").order_by("order")

    # 2. Fetch User Progress
    progress_map = {}
    completed_count = 0

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
    video_modules = [m for m in modules if not m.ppt_file]
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
                if mod.video_file
                else "/static/video/Demo_Video_OHPL.mp4"
            ),
            "url": "https://docs.google.com/presentation/d/1wb69ZQ4oYGYxOxzjNaTQP5bIfsB3tIKi/embed",
            "duration": mod.duration_seconds,
            "last_position": last_position,
        }
        video_list.append(item)
        previous_completed = is_completed

    # Process PPTs Sequence
    ppt_modules = [m for m in modules if m.ppt_file and not m.video_file]

    # Reset previous_completed for PPT sequence
    previous_completed = True

    # [NEW] Inject POSH Act PDF for Reference (as requested)
    posh_pdf_mod = (
        TrainingModule.objects.filter(module_type="POSH", ppt_file__isnull=False)
        .exclude(video_file__isnull=False)
        .order_by("order")
        .first()
    )
    if posh_pdf_mod:
        item = {
            "id": posh_pdf_mod.id,
            "title": f"Reference: {posh_pdf_mod.title}",
            "is_completed": False,  # Just a reference, no tracking here needed
            "is_locked": False,
            "thumb": posh_pdf_mod.thumbnail.url if posh_pdf_mod.thumbnail else None,
            "src": "",
            # UPDATED: Use new hardcoded path for PPT if referencing POSH PDF
            "url": "https://docs.google.com/presentation/d/1wb69ZQ4oYGYxOxzjNaTQP5bIfsB3tIKi/embed",
        }
        ppt_list.append(
            item
        )  # Add to end or start? User said "show... when i open ppt". List is safer.

    for mod in ppt_modules:
        prog_data = progress_map.get(mod.id, {"is_completed": False, "last_position": 0.0})
        is_completed = prog_data["is_completed"]
        is_locked = not previous_completed

        item = {
            "id": mod.id,
            "title": mod.title,
            "is_completed": is_completed,
            "is_locked": is_locked,
            "thumb": mod.thumbnail.url if mod.thumbnail else None,
            # UPDATED: Use new hardcoded path
            "src": "/media/training ppt/Posh Video PPT.pptx",
            "url": "https://docs.google.com/presentation/d/1wb69ZQ4oYGYxOxzjNaTQP5bIfsB3tIKi/embed",
        }
        ppt_list.append(item)
        if not is_completed:
            previous_completed = False

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
    formatted_total_time = (
        f"{total_seconds_watched // 3600:02}:"
        f"{(total_seconds_watched % 3600) // 60:02}:"
        f"{total_seconds_watched % 60:02}"
    )

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
        "total_seconds_watched": total_seconds_watched,
        "formatted_total_time": formatted_total_time,
        "is_assessment_unlocked": percent_complete == 100,
        "final_quiz_completed": AssessmentProgress.objects.filter(
            user=user, assessment_type="POCSO", is_passed=True
        ).exists(),
        "has_organization": has_organization,
        "org_logo_url": org_logo_url,
    }

    return render(request, "pocso/pocso_individual_training.html", context)

@login_required(login_url="login")
def pocso_act_page_corp(request):
    """Same as pocso_act_page but for company employees - no certificate option."""
    user = request.user
    has_access = Subscription.objects.filter(
        Q(user=user) | Q(organization__organizationmember__user=user),
        status="ACTIVE",
        plan__type__in=["POCSO", "BOTH"],
    ).exists()

    if not has_access:
        messages.error(request, "Access Denied: Subscription Required.")
        return redirect("tutorial")

    # 1. Fetch Modules
    modules = TrainingModule.objects.filter(module_type="POCSO").order_by("order")

    # Debug logging
    print(f"DEBUG POCSO CORP: Total modules found: {modules.count()}")

    # 2. Fetch User Progress
    progress_map = {}
    completed_count = 0

    for mod in modules:
        prog, created = ModuleProgress.objects.get_or_create(user=user, module=mod)
        progress_map[mod.id] = {
            "is_completed": prog.is_completed,
            "last_position": getattr(prog, "last_position", 0.0),
        }
        if prog.is_completed:
            completed_count += 1
        print(
            f"DEBUG: Module {mod.id} '{mod.title}' - is_completed: {prog.is_completed}"
        )

    # 3. Calculate Overall Status
    total_modules = modules.count()
    percent_complete = (
        int((completed_count / total_modules) * 100) if total_modules > 0 else 0
    )

    # 4. Determine Locked Status & Split
    video_list = []
    ppt_list = []

    # Process Videos Sequence - modules with video files
    video_modules = [m for m in modules if m.video_file]
    print(f"DEBUG: Video modules count: {len(video_modules)}")
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
                if mod.video_file
                else "/static/video/Demo_Video_OHPL.mp4"
            ),
            "url": "https://docs.google.com/presentation/d/1wb69ZQ4oYGYxOxzjNaTQP5bIfsB3tIKi/embed",
            "duration": mod.duration_seconds,
            "last_position": last_position,
        }
        video_list.append(item)
        print(
            f"DEBUG: Added video {mod.id} - is_completed: {is_completed}, is_locked: {is_locked}"
        )
        previous_completed = is_completed

    # Process PPTs Sequence
    ppt_modules = [m for m in modules if m.ppt_file and not m.video_file]
    print(f"DEBUG: PPT modules count: {len(ppt_modules)}")

    # Reset previous_completed for PPT sequence
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
            "thumb": mod.thumbnail.url if mod.thumbnail else None,
            "src": "/media/training ppt/Posh Video PPT.pptx",
            "url": "https://docs.google.com/presentation/d/1wb69ZQ4oYGYxOxzjNaTQP5bIfsB3tIKi/embed",
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
    formatted_total_time = (
        f"{total_seconds_watched // 3600:02}:"
        f"{(total_seconds_watched % 3600) // 60:02}:"
        f"{total_seconds_watched % 60:02}"
    )

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
        "total_seconds_watched": total_seconds_watched,
        "formatted_total_time": formatted_total_time,
        "is_assessment_unlocked": percent_complete == 100,
        "final_quiz_completed": AssessmentProgress.objects.filter(
            user=user, assessment_type="POCSO", is_passed=True
        ).exists(),
        "is_company_employee": True,
    }

    return render(request, "pocso/pocso_employee_training.html", context)

def pocso_assessment(request):
    return render(request, "pocso/pocso_assessment.html")

def pocso_i(request):
    return render(request, "pocso/pocso_individual_details.html")

def pocso_c(request):
    return render(request, "pocso/pocso_company_details.html")

@login_required(login_url="accounts_login")
def accounts_verify_pocso_payment_view(request, registration_id):
    """Mark a POCSO registration as verified by the accounts department"""

    if request.user.account_type != "ACCOUNTS" and not request.user.is_superuser:
        return redirect("home")

    registration = get_object_or_404(POCSORegistration, id=registration_id)

    registration.payment_status = "VERIFIED"
    registration.save()

    # Send payment verification email
    try:
        from home.email_utils import send_tiered_email

        send_tiered_email(registration, "PAYMENT_VERIFIED", "POCSO")

    except Exception as e:
        logger.warning(
            f"Payment verified but email failed for {registration.school_name}: {e}"
        )

    messages.success(request, f"Payment for {registration.school_name} has been verified!", extra_tags="payment_approved")

    return redirect("accounts_pocso_registration_detail", registration_id=registration_id)

@login_required(login_url="accounts_login")
def accounts_reject_pocso_payment_view(request, registration_id):
    """Reject/reset a POCSO payment status back to PENDING"""
    if request.user.account_type != "ACCOUNTS" and not request.user.is_superuser:
        return redirect("home")
    registration = get_object_or_404(POCSORegistration, id=registration_id)
    registration.payment_status = "REJECTED"
    registration.save()
    messages.warning(
        request, f"Payment for {registration.school_name} has been rejected.", extra_tags="payment_rejected"
    )
    return redirect("accounts_pocso_registration_detail", registration_id=registration_id)

def get_pocso_pricing_context(registration):
    """Refactored helper to calculate POCSO billing context for both customer billing and admin review"""
    from home.utils import get_pocso_billing_data

    billing_data = get_pocso_billing_data(registration)

    return {
        "reg": registration,
        "registration": registration,
        "addon_fees": billing_data["addon_fees"],
        "subtotal": billing_data["subtotal"],
        "gst_percentage": billing_data["gst_percentage"],
        "tax": billing_data["gst_amount"],
        "total": billing_data["total_amount"],
        "total_tier_1": billing_data["total_amount"],
        "total_tier_2": billing_data["total_amount"],
        "total_tier_3": billing_data["total_amount"],
        "payment_status": registration.payment_status,
    }

@login_required(login_url="accounts_login")
def accounts_pocso_registration_detail_view(request, registration_id):
    """Full POCSO registration detail with billing breakdown for Accounts team review"""
    if request.user.account_type != "ACCOUNTS" and not request.user.is_superuser:
        return redirect("home")

    registration = get_object_or_404(POCSORegistration, id=registration_id)
    context = get_pocso_pricing_context(registration)
    return render(request, "pocso/accounts_pocso_registration_detail.html", context)

@login_required(login_url="accounts_login")
def accounts_save_pocso_pricing_view(request):
    """Save the POCSO pricing configuration with Flat Fee Model"""
    if request.user.account_type != "ACCOUNTS" and not request.user.is_superuser:
        return redirect("home")

    if request.method == "POST":
        from decimal import Decimal

        # Deactivate all existing configs
        POCSOPricingConfig.objects.update(is_active=False)

        p = request.POST.get
        gst_percentage_str = request.POST.get("gst_percentage", "").strip()
        if gst_percentage_str == "":
            gst_percentage = Decimal("18.00")
        else:
            gst_percentage = Decimal(gst_percentage_str)

        config = POCSOPricingConfig(
            # Compliance Gap Fees (Flat)
            fee_no_policy=p("fee_no_policy", 5000.00),
            fee_no_committee=p("fee_no_committee", 5000.00),
            # Redundant gap fees removed in favor of granular per-head rates
            # Granular Training Rates
            teacher_rate_online=p("teacher_rate_online", 136.00),
            teacher_rate_offline=p("teacher_rate_offline", 136.00),
            teacher_rate_elearning=p("teacher_rate_elearning", 136.00),
            staff_rate_online=p("staff_rate_online", 91.00),
            staff_rate_offline=p("staff_rate_offline", 91.00),
            staff_rate_elearning=p("staff_rate_elearning", 91.00),
            student_rate=p("student_rate", 55.00),
            gst_percentage=gst_percentage,
            created_by=request.user,
            is_active=True,
        )
        config.save()
        request.session["pocso_pricing_saved"] = True

    from django.urls import reverse

    return redirect(f"{reverse('accounts_dashboard')}?active_tab=pocso_pricing")

def pocso_registration_view(request):
    """Handle POCSO compliance registration submission"""
    if request.method == "POST":
        data = request.POST

        # Verify custom CAPTCHA
        captcha_code = request.POST.get("captcha", "").strip()
        session_captcha = request.session.get("captcha_text", "")
        if not session_captcha or captcha_code.lower() != session_captcha.lower():
            messages.error(request, "CAPTCHA verification failed. Please try again.")
            return redirect("pocso_registration")

        reg = POCSORegistration(
            school_name=data.get("school_name"),
            person_name=data.get("person_name"),
            email=data.get("email"),
            phone=data.get("phone"),
            address=data.get("address"),
            city=data.get("city"),
            students_count=int(data.get("students_count", 0)),
            teachers_count=int(data.get("teachers_count", 0)),
            non_teaching_staff_count=int(data.get("non_teaching_staff_count", 0)),
            has_policy=data.get("has_policy") == "yes",
            has_committee=data.get("has_committee") == "yes",
            teaching_staff_trained=data.get("teaching_staff_trained") == "yes",
            non_teaching_staff_trained=data.get("non_teaching_staff_trained") == "yes",
            students_trained=data.get("students_trained") == "yes",
            vendors_access_premises=data.get("vendors_access_premises") == "yes",
            has_transport=data.get("has_transport") == "yes",
            # POCSO Training Preferences
            teaching_training_mode=data.get("teaching_staff_training_pref"),
            non_teaching_training_mode=data.get("non_teaching_staff_training_pref"),
        )
        reg.save()
        request.session["last_pocso_registration_id"] = reg.id
        return redirect("pocso_billing")

    registration = None
    if request.GET.get("edit") == "true":
        if request.user.is_authenticated:
            registration = (
                POCSORegistration.objects.filter(user=request.user)
                .order_by("-created_at")
                .first()
            )
        else:
            reg_id = request.session.get("last_pocso_registration_id")
            if reg_id:
                registration = POCSORegistration.objects.filter(id=reg_id).first()

    return render(request, "pocso/pocso_registration.html", {"registration": registration})

def pocso_billing_view(request):
    """Show billing breakdown for POCSO with calculated context"""
    reg_id = request.session.get("last_pocso_registration_id")
    registration = (
        POCSORegistration.objects.filter(id=reg_id).first() if reg_id else None
    )

    if not registration and request.user.is_authenticated:
        registration = (
            POCSORegistration.objects.filter(user=request.user)
            .order_by("-created_at")
            .first()
        )

    if not registration:
        return redirect("pocso_registration")

    if request.method == "POST":
        registration.payment_status = "PENDING"
        registration.is_paid = False
        registration.save()
        try:
            from home.email_utils import send_interest_email
            send_interest_email(registration, "POCSO", request=request)
        except Exception as e:
            logger.warning(f"Failed to send interest email for POCSO registration {registration.id}: {e}")
        request.session["registration_submitted"] = True
        return redirect("pocso_billing")

    context = get_pocso_pricing_context(registration)
    context["registration_submitted"] = request.session.pop("registration_submitted", False)
    return render(request, "pocso/pocso_billing.html", context)



