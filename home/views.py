import csv
import io
import json
import os
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db import transaction
from django.db.models import Q, Sum
from django.contrib.auth.decorators import user_passes_test
from datetime import timedelta
from django.contrib.auth import logout
from PIL import Image
from django.conf import settings

# Models
# Ensure your User model has 'phone' and 'department' fields if you want to save them to the DB.
from .models import (
    User,
    SubscriptionPlan,
    Subscription,
    Payment,
    Organization,
    OrganizationMember,
    TrainingModule,
    ModuleProgress,
    DailyActivity,
    AssessmentProgress,
)

# Ensure this file exists in your app or adjust import accordingly
from .chatbot_logic import predict_answer
from .utils import generate_certificate


@login_required(login_url="login")
def upload_company_logo(request):
    """View for HR Admin to upload their company logo"""
    if request.method == "POST":
        current_user = request.user
        membership = OrganizationMember.objects.filter(
            user=current_user, role="ADMIN"
        ).first()
        if not membership:
            messages.error(request, "Unauthorized.")
            return redirect("company_dashboard")

        org = membership.organization
        logo = request.FILES.get("company_logo")
        if logo:
            org.logo = logo
            org.save()
            messages.success(request, "Company logo uploaded successfully!")
        else:
            messages.error(request, "No logo file selected.")

    return redirect("company_dashboard")


@login_required(login_url="login")
def get_poster_with_logo(request, poster_type):
    """View to merge company logo into the poster and serve it (view or download)"""
    user = request.user

    # Identify organization (HR Admin requirement)
    membership = OrganizationMember.objects.filter(user=user, role="ADMIN").first()
    if not membership:
        # Check if user is an employee of an organization
        membership = OrganizationMember.objects.filter(user=user).first()
        if not membership:
            return HttpResponse("Unauthorized", status=403)

    org = membership.organization
    is_download = request.GET.get("download") == "1"

    # Determine the poster file path
    if poster_type == "posh":
        poster_filename = "POSH Poster.jpeg"
    elif poster_type == "pocso":
        poster_filename = "POCSO Poster.jpeg"
    else:
        return HttpResponse("Invalid poster type", status=400)

    poster_path = os.path.join(settings.MEDIA_ROOT, "Posters", poster_filename)

    if not os.path.exists(poster_path):
        return HttpResponse("Base poster not found", status=404)

    try:
        # Open the base poster
        poster_img = Image.open(poster_path).convert("RGBA")
        p_width, p_height = poster_img.size

        # If organization has a logo, merge it
        if org.logo:
            logo_path = org.logo.path
            if os.path.exists(logo_path):
                logo_img = Image.open(logo_path).convert("RGBA")

                # Scale based on saved org.logo_width (percentage of poster width)
                # Default to 15% if something goes wrong
                lw_pct = org.logo_width if org.logo_width > 0 else 15.0
                target_width = int(p_width * (lw_pct / 100.0))
                w_percent = target_width / float(logo_img.size[0])
                target_height = int((float(logo_img.size[1]) * float(w_percent)))
                logo_img = logo_img.resize((target_width, target_height), Image.LANCZOS)

                # Positioning based on saved org.logo_x, org.logo_y (percentages)
                pos_x = int(p_width * (org.logo_x / 100.0))
                pos_y = int(p_height * (org.logo_y / 100.0))

                # Paste the logo directly onto the poster (using itself as mask for transparency)
                poster_img.paste(logo_img, (pos_x, pos_y), logo_img)

        # Save to buffer
        buffer = io.BytesIO()
        poster_img.convert("RGB").save(buffer, format="JPEG", quality=95)
        buffer.seek(0)

        safe_org_name = "".join(
            [c for c in org.name if c.isalnum() or c in (" ", "_", "-")]
        ).strip()
        filename = f"{safe_org_name}_{poster_filename}"

        return FileResponse(
            buffer,
            as_attachment=is_download,
            filename=filename,
            content_type="image/jpeg",
        )

    except Exception as e:
        print(f"Error generating poster: {str(e)}")
        return HttpResponse(f"Error generating poster: {str(e)}", status=500)


@csrf_exempt
@login_required(login_url="login")
def save_logo_config(request):
    """Save logo position and size from interactive editor"""
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            membership = OrganizationMember.objects.filter(
                user=request.user, role="ADMIN"
            ).first()
            if not membership:
                return JsonResponse(
                    {"status": "error", "message": "Unauthorized"}, status=403
                )

            org = membership.organization
            org.logo_x = float(data.get("x", 2.0))
            org.logo_y = float(data.get("y", 2.0))
            org.logo_width = float(data.get("width", 15.0))
            org.save()
            return JsonResponse({"status": "success"})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=500)
    return JsonResponse({"status": "error", "message": "Invalid request"}, status=400)


@login_required(login_url="login")
def reset_logo_config(request):
    """Reset logo position and size to default"""
    membership = OrganizationMember.objects.filter(
        user=request.user, role="ADMIN"
    ).first()
    if not membership:
        messages.error(request, "Unauthorized.")
        return redirect("company_dashboard")

    org = membership.organization
    org.logo_x = 2.0
    org.logo_y = 2.0
    org.logo_width = 15.0
    org.save()
    messages.success(request, "Logo position and size reset to default.")
    return redirect("company_dashboard")


# --- 1. LOGIN REDIRECT LOGIC ---
@login_required
def custom_login_redirect(request):
    user = request.user

    # 0. SUPERUSER -> Superuser Dashboard
    if user.is_superuser:
        return redirect("superuser_dashboard")

    # 1. ADMIN -> Dashboard
    if user.account_type == "COMPANY_ADMIN":
        return redirect("company_dashboard")

    # 2. USER (Employee/Individual) -> Direct to Training Page
    elif user.account_type in ["EMPLOYEE", "INDIVIDUAL"]:
        has_posh = Subscription.objects.filter(
            Q(user=user) | Q(organization__organizationmember__user=user),
            status="ACTIVE",
            plan__type__in=["POSH", "BOTH"],
        ).exists()

        has_pocso = Subscription.objects.filter(
            Q(user=user) | Q(organization__organizationmember__user=user),
            status="ACTIVE",
            plan__type__in=["POCSO", "BOTH"],
        ).exists()

        if user.account_type == "EMPLOYEE":
            # Check if password change is required
            if user.force_password_change:
                return redirect("force_password_change")

            # Company employees -> pages WITHOUT certificate option
            if has_posh:
                return redirect("posh_act_page_corp")
            if has_pocso:
                return redirect("pocso_act_page_corp")
        else:
            # Individual subscribers -> pages WITH certificate option
            if has_posh:
                return redirect("posh_act_page")
            if has_pocso:
                return redirect("pocso_act_page")

        return redirect("tutorial")

    return redirect("home")


# --- 1.5 FORCE PASSWORD CHANGE (First-time Login) ---
@login_required
def force_password_change(request):
    user = request.user

    # Redirect if user doesn't need to change password
    if not user.force_password_change:
        return redirect("custom_login_redirect")

    if request.method == "POST":
        new_password = request.POST.get("new_password")
        confirm_password = request.POST.get("confirm_password")

        if not new_password or not confirm_password:
            messages.error(request, "Both fields are required.")
            return render(request, "force_password_change.html")

        if new_password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, "force_password_change.html")

        if len(new_password) < 8:
            messages.error(request, "Password must be at least 8 characters long.")
            return render(request, "force_password_change.html")

        # Update password
        user.set_password(new_password)
        user.force_password_change = False
        user.save()

        # Send email notification
        from home.email_utils import send_password_change_email

        send_password_change_email(user)

        # Update session to prevent logout
        from django.contrib.auth import update_session_auth_hash

        update_session_auth_hash(request, user)

        messages.success(request, "Password changed successfully!")
        return redirect("custom_login_redirect")

    return render(request, "force_password_change.html")


# --- 2. COMPANY SUBSCRIPTION (FORM) ---
def company_subscription(request, plan_type):
    db_type = "POSH" if "POSH" in plan_type else "POCSO"
    plan = SubscriptionPlan.objects.filter(type=db_type).first()

    if request.method == "POST":
        comp_name = request.POST.get("company_name", "").strip()
        seats = request.POST.get("seats", 10)
        fullname = request.POST.get("fullname", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "").strip()

        # Restriction: Ensure all info is compulsory
        if not all([comp_name, fullname, email, password]):
            messages.error(
                request, "All fields are compulsory. Please fill out the entire form."
            )
            return redirect(request.path)

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already registered.")
            return redirect(request.path)
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=email, email=email, password=password
                )
                user.first_name = fullname
                user.account_type = "COMPANY_ADMIN"
                user.save()

                org = Organization.objects.create(
                    name=comp_name, owner=user, max_users=int(seats)
                )

                # Generate default password for this organization
                org.default_password = org.generate_default_password()
                org.save()

                OrganizationMember.objects.create(
                    organization=org, user=user, role="ADMIN"
                )

                Subscription.objects.create(
                    organization=org,
                    plan=plan,
                    status="ACTIVE",
                    start_date=timezone.now(),
                )

                # Regenerate user_id after organization and subscription are created
                user.user_id = user.generate_user_id()
                user.save()

                # Send welcome email to company admin
                from home.email_utils import send_welcome_email

                send_welcome_email(user, password, is_company_employee=False)

            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            return redirect("company_dashboard")

        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
            return redirect(request.path)

    # FIX FOR CACHE PROBLEM: Clear messages on a fresh GET request
    else:
        list(messages.get_messages(request))

    response = render(request, "company_signup.html", {"plan_type": plan_type})
    # FIX FOR CACHE PROBLEM: Disable browser caching for this page
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


# --- 3. ADD EMPLOYEE (SINGLE) ---
@login_required(login_url="login")
def add_employee(request):
    if request.method == "POST":
        current_user = request.user

        membership = OrganizationMember.objects.filter(
            user=current_user, role="ADMIN"
        ).first()
        if not membership:
            messages.error(request, "Unauthorized.")
            return redirect("tutorial")

        org = membership.organization
        current_count = OrganizationMember.objects.filter(organization=org).count()
        if current_count >= org.max_users:
            messages.error(
                request,
                f"Seat limit reached ({org.max_users}). Upgrade plan to add more.",
            )
            return redirect("company_dashboard")

        emp_name = request.POST.get("emp_name")
        emp_email = request.POST.get("emp_email")
        emp_password = request.POST.get("emp_password")

        # Use default password if not provided in form
        if not emp_password:
            emp_password = org.default_password

        # If still no password (org doesn't have default), generate one
        if not emp_password:
            emp_password = org.generate_default_password()
            org.default_password = emp_password
            org.save()

        if User.objects.filter(email=emp_email).exists():
            messages.error(request, "User email already exists.")
            return redirect("company_dashboard")

        try:
            with transaction.atomic():
                new_user = User.objects.create_user(
                    username=emp_email, email=emp_email, password=emp_password
                )
                new_user.first_name = emp_name
                new_user.account_type = "EMPLOYEE"
                new_user.force_password_change = (
                    True  # Force password change on first login
                )
                # Generate user_id by passing org directly (avoids querying unsaved relationships)
                new_user.user_id = new_user.generate_user_id(organization=org)
                new_user.save()

                OrganizationMember.objects.create(
                    organization=org, user=new_user, role="MEMBER"
                )

                # Send welcome email with credentials
                from home.email_utils import send_welcome_email

                send_welcome_email(
                    new_user,
                    emp_password,
                    is_company_employee=True,
                    organization_name=org.name,
                )

            messages.success(request, f"{emp_name} added successfully!")
        except Exception as e:
            print(f"Error adding employee: {str(e)}")
            import traceback

            traceback.print_exc()
            messages.error(request, f"Database error: {str(e)}")

        return redirect("company_dashboard")
    return redirect("company_dashboard")


# --- 4. COMPANY DASHBOARD ---
@login_required(login_url="login")
def company_dashboard(request):
    user = request.user
    membership = OrganizationMember.objects.filter(user=user, role="ADMIN").first()

    if not membership:
        messages.error(request, "Access Denied. Admin only.")
        return redirect("tutorial")

    org = membership.organization
    active_sub = Subscription.objects.filter(organization=org, status="ACTIVE").first()
    members = OrganizationMember.objects.filter(organization=org).select_related("user")

    # --- DATA CALCULATION FOR HTML ---
    total_employees = members.count()
    seats_remaining = org.max_users - total_employees

    # Identify Training Type based on Plan
    training_type = "POSH"  # Default
    if active_sub and active_sub.plan.type in ["POCSO", "BOTH"]:
        if active_sub.plan.type == "POCSO":
            training_type = "POCSO"

    # Fetch total modules for calculation
    all_modules = TrainingModule.objects.filter(module_type=training_type).order_by(
        "order"
    )
    total_modules_count = all_modules.count()

    training_completed_count = 0

    # Annotate members with progress
    for mem in members:
        user_obj = mem.user

        # Get progress for this user
        completed_modules = ModuleProgress.objects.filter(
            user=user_obj, module__module_type=training_type, is_completed=True
        ).count()

        mem.percent_complete = (
            int((completed_modules / total_modules_count) * 100)
            if total_modules_count > 0
            else 0
        )
        mem.completed_modules_count = completed_modules
        mem.is_training_completed = (completed_modules == total_modules_count) and (
            total_modules_count > 0
        )

        if mem.is_training_completed:
            training_completed_count += 1

        # Get Last 7 Days Activity for Chart
        today = timezone.now().date()
        last_7_days = [(today - timedelta(days=i)) for i in range(6, -1, -1)]
        mem_chart_data = []
        for d in last_7_days:
            act = DailyActivity.objects.filter(user=user_obj, date=d).first()
            mem_chart_data.append(act.minutes_watched if act else 0)
        mem.chart_data = json.dumps(mem_chart_data)

        # Module Status List for Modal
        mem_modules_status = []
        user_progress_map = set(
            ModuleProgress.objects.filter(
                user=user_obj, module__module_type=training_type, is_completed=True
            ).values_list("module_id", flat=True)
        )

        # Split modules for calculation
        # Note: all_modules is already filtered by training_type
        vid_mods = [m for m in all_modules if m.video_file]
        ppt_mods = [m for m in all_modules if m.ppt_file and not m.video_file]

        total_vid_count = len(vid_mods)
        total_ppt_count = len(ppt_mods)

        completed_vid_count = sum(1 for m in vid_mods if m.id in user_progress_map)
        completed_ppt_count = sum(1 for m in ppt_mods if m.id in user_progress_map)

        mem.video_percent = (
            int((completed_vid_count / total_vid_count) * 100)
            if total_vid_count > 0
            else 0
        )
        mem.ppt_percent = (
            int((completed_ppt_count / total_ppt_count) * 100)
            if total_ppt_count > 0
            else 0
        )

        for mod in all_modules:
            is_done = mod.id in user_progress_map
            item = {
                "title": mod.title,
                "is_completed": is_done,
                "duration": mod.duration_seconds,
                "thumbnail_url": mod.thumbnail.url if mod.thumbnail else "",
                "ppt_url": mod.ppt_file.url if mod.ppt_file else "",
                "is_ppt": bool(mod.ppt_file and not mod.video_file),  # Strict check
            }
            mem_modules_status.append(item)

        mem.modules_status = mem_modules_status
        mem.video_modules = [m for m in mem_modules_status if not m["is_ppt"]]
        mem.ppt_modules = [m for m in mem_modules_status if m["is_ppt"]]

        # Calculate Total Active Time
        total_mins_agg = (
            DailyActivity.objects.filter(user=user_obj).aggregate(
                Sum("minutes_watched")
            )["minutes_watched__sum"]
            or 0
        )
        total_secs_agg = (
            DailyActivity.objects.filter(user=user_obj).aggregate(
                Sum("seconds_watched")
            )["seconds_watched__sum"]
            or 0
        )

        # Convert all to integer seconds
        grand_total_seconds = (total_mins_agg * 60) + total_secs_agg
        hours = grand_total_seconds // 3600
        minutes = (grand_total_seconds % 3600) // 60
        mem.total_active_time = f"{hours}h {minutes}m"

        # Check if employee has passed the final quiz (for certificate eligibility)
        has_passed_quiz = AssessmentProgress.objects.filter(
            user=user_obj, assessment_type=training_type, is_passed=True
        ).exists()
        mem.has_certificate = has_passed_quiz and mem.is_training_completed

    training_pending = total_employees - training_completed_count

    # Get employees with certificates
    certified_employees = [
        m for m in members if hasattr(m, "has_certificate") and m.has_certificate
    ]

    # Ensure organization has a default password
    if not org.default_password:
        org.default_password = org.generate_default_password()
        org.save()

    context = {
        "organization": org,
        "active_plan": active_sub,
        "members": members,
        "seats_used": total_employees,
        "seats_remaining": seats_remaining,
        "total_employees": total_employees,
        "training_completed": training_completed_count,
        "training_pending": training_pending,
        "total_modules_count": total_modules_count,
        "certified_employees": certified_employees,
        "training_type": training_type,
        "default_password": org.default_password,  # Pass default password to template
    }

    # --- LOGIC TO SWITCH TEMPLATES BASED ON PLAN ---
    if active_sub and active_sub.plan.type == "POCSO":
        return render(request, "company_dashboard_pocso.html", context)
    else:
        # Default to POSH dashboard
        return render(request, "company_dashboard.html", context)


# --- 5. INDIVIDUAL SUBSCRIPTION (FORM) ---
def individual_subscription(request, plan_type):
    db_type = "POSH" if "POSH" in plan_type else "POCSO"
    plan = SubscriptionPlan.objects.filter(type=db_type).first()

    if request.method == "POST":
        fullname = request.POST.get("fullname", "").strip()
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "").strip()

        # Restriction: Ensure all info is compulsory
        if not all([fullname, username, email, password]):
            messages.error(
                request, "All fields are compulsory. Please fill out the entire form."
            )
            return redirect(request.path)

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username taken.")
            return redirect(request.path)
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=username, email=email, password=password
                )
                user.first_name = fullname
                user.account_type = "INDIVIDUAL"
                user.save()

                Subscription.objects.create(
                    user=user, plan=plan, status="ACTIVE", start_date=timezone.now()
                )

                # Regenerate user_id after subscription is created
                user.user_id = user.generate_user_id()
                user.save()

                # Send welcome email
                from home.email_utils import send_welcome_email

                send_welcome_email(user, password, is_company_employee=False)

            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            return redirect("posh_act_page")
        except Exception as e:
            messages.error(request, str(e))
            return redirect(request.path)

    # FIX FOR CACHE PROBLEM: Clear messages on a fresh GET request
    else:
        list(messages.get_messages(request))

    context = {
        "plan_type": plan.name if plan else "Unknown Plan",
        "price": plan.price if plan else 0,
    }
    response = render(request, "subscription_details.html", context)
    # FIX FOR CACHE PROBLEM: Disable browser caching
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


# --- 6. SECURE TRAINING PAGES ---
@login_required(login_url="login")
def posh_act_page(request):
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
    completed_count = 0

    # Initialize progress for all modules if not exists
    for mod in modules:
        prog, created = ModuleProgress.objects.get_or_create(user=user, module=mod)
        progress_map[mod.id] = prog.is_completed
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
        is_completed = progress_map.get(mod.id, False)
        is_locked = not previous_completed

        item = {
            "id": mod.id,
            "title": mod.title,
            "is_completed": is_completed,
            "is_locked": is_locked,
            "thumb": mod.thumbnail.url if mod.thumbnail else "",
            # UPDATED: Use new hardcoded path for demo video
            "url": "https://docs.google.com/presentation/d/1wb69ZQ4oYGYxOxzjNaTQP5bIfsB3tIKi/embed",
            "duration": mod.duration_seconds,
        }
        video_list.append(item)
        previous_completed = is_completed

    # Process PPT Sequence
    ppt_modules = [m for m in modules if m.ppt_file and not m.video_file]

    # UPDATED: Only include if it has PPT AND NO Video (to prevent duplicates)
    previous_completed = True
    for mod in ppt_modules:
        is_completed = progress_map.get(mod.id, False)
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

    context = {
        "video_modules": video_list,
        "ppt_modules": ppt_list,
        "percent_complete": percent_complete,
        "completed_count": completed_count,
        "total_modules": total_modules,
        "chart_labels": json.dumps(chart_labels),
        "chart_data": json.dumps(chart_data),
        "chart_data": json.dumps(chart_data),
        # Remove duplicate key if present
        "total_seconds_watched": total_seconds_watched,
        "formatted_total_time": f"{total_seconds_watched // 3600:02}:{(total_seconds_watched % 3600) // 60:02}:{total_seconds_watched % 60:02}",
        "is_final_quiz_passed": AssessmentProgress.objects.filter(
            user=user, assessment_type="POSH", is_passed=True
        ).exists(),
    }

    return render(request, "posh_act_page.html", context)


@csrf_exempt
@login_required
def update_watch_time(request):
    """
    API called by frontend to record watch time (seconds).
    Frequency: ~5s
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            seconds_delta = int(
                data.get("seconds", 60)
            )  # Default to 60 for backward compat if any old frontend hits it

            today = timezone.now().date()
            activity, created = DailyActivity.objects.get_or_create(
                user=request.user, date=today
            )

            # Add delta
            activity.seconds_watched += seconds_delta

            # Normalize: If seconds >= 60, convert to minutes
            if activity.seconds_watched >= 60:
                extra_mins = activity.seconds_watched // 60
                activity.minutes_watched += extra_mins
                activity.seconds_watched = activity.seconds_watched % 60

            activity.save()

            # Return Total Time in Minutes (for backward compat display) + Raw Seconds
            total_minutes = activity.minutes_watched
            return JsonResponse({"status": "success", "total_minutes": total_minutes})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=500)
    return JsonResponse({"status": "error"}, status=400)


@csrf_exempt
@login_required
def mod_complete(request, module_id):
    """
    API called when a video ends. Marks module as complete.
    """
    print(
        f"DEBUG mod_complete called: method={request.method}, module_id={module_id}, user={request.user}"
    )
    if request.method == "POST":
        try:
            module = TrainingModule.objects.get(id=module_id)
            print(f"DEBUG: Found module: {module.title}")
            prog, created = ModuleProgress.objects.get_or_create(
                user=request.user, module=module
            )
            print(
                f"DEBUG: ModuleProgress {'created' if created else 'found'}, current is_completed={prog.is_completed}"
            )
            prog.is_completed = True
            prog.save()
            print(
                f"DEBUG: Saved ModuleProgress, is_completed=True for user={request.user.id}, module={module_id}"
            )
            return JsonResponse({"status": "success", "module_id": module_id})
        except TrainingModule.DoesNotExist:
            print(f"DEBUG ERROR: Module {module_id} not found")
            return JsonResponse(
                {"status": "error", "message": "Module not found"}, status=404
            )
        except Exception as e:
            print(f"DEBUG ERROR: Exception in mod_complete: {e}")
            return JsonResponse({"status": "error", "message": str(e)}, status=500)
    print(f"DEBUG: Invalid method {request.method}")
    return JsonResponse({"status": "error"}, status=400)


@csrf_exempt
@login_required
def submit_assessment(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            assessment_type = data.get("type", "POSH")  # POSH or POCSO
            score = int(data.get("score", 0))
            passed = bool(data.get("passed", False))

            progress, created = AssessmentProgress.objects.get_or_create(
                user=request.user, assessment_type=assessment_type
            )
            progress.score = score
            progress.is_passed = passed
            progress.save()

            return JsonResponse({"status": "success", "message": "Result saved"})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=500)
    return JsonResponse({"status": "error", "message": "Invalid method"}, status=400)


@login_required(login_url="login")
def pocso_act_page(request):
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

    # 2. Fetch User Progress
    progress_map = {}
    completed_count = 0

    for mod in modules:
        prog, created = ModuleProgress.objects.get_or_create(user=user, module=mod)
        progress_map[mod.id] = prog.is_completed
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
        is_completed = progress_map.get(mod.id, False)
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
                else "/media/training%20videos/Demo%20video.mp4"
            ),
            "url": "https://docs.google.com/presentation/d/1wb69ZQ4oYGYxOxzjNaTQP5bIfsB3tIKi/embed",
            "duration": mod.duration_seconds,
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
        is_completed = progress_map.get(mod.id, False)
        is_locked = not previous_completed

        item = {
            "id": mod.id,
            "title": mod.title,
            "is_completed": is_completed,
            "is_locked": is_locked,
            "thumb": mod.thumbnail.url if mod.thumbnail else None,
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
    formatted_total_time = f"{total_seconds_watched // 3600:02}:{(total_seconds_watched % 3600) // 60:02}:{total_seconds_watched % 60:02}"

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
    }

    return render(request, "pocso_act_page.html", context)


# --- 6b. COMPANY EMPLOYEE TRAINING PAGES (No Certificate) ---


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
    completed_count = 0

    # Initialize progress for all modules if not exists
    for mod in modules:
        prog, created = ModuleProgress.objects.get_or_create(user=user, module=mod)
        progress_map[mod.id] = prog.is_completed
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
        is_completed = progress_map.get(mod.id, False)
        is_locked = not previous_completed

        item = {
            "id": mod.id,
            "title": mod.title,
            "is_completed": is_completed,
            "is_locked": is_locked,
            "thumb": mod.thumbnail.url if mod.thumbnail else "",
            # UPDATED: Use new hardcoded path for demo video
            "url": "https://docs.google.com/presentation/d/1wb69ZQ4oYGYxOxzjNaTQP5bIfsB3tIKi/embed",
            "duration": mod.duration_seconds,
        }
        video_list.append(item)
        previous_completed = is_completed

    # Process PPT Sequence
    ppt_modules = [m for m in modules if m.ppt_file and not m.video_file]

    # UPDATED: Only include if it has PPT AND NO Video (to prevent duplicates)
    previous_completed = True
    for mod in ppt_modules:
        is_completed = progress_map.get(mod.id, False)
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
        "formatted_total_time": f"{total_seconds_watched // 3600:02}:{(total_seconds_watched % 3600) // 60:02}:{total_seconds_watched % 60:02}",
        "is_final_quiz_passed": AssessmentProgress.objects.filter(
            user=user, assessment_type="POSH", is_passed=True
        ).exists(),
        "is_company_employee": True,
    }

    return render(request, "posh_act_page_corp.html", context)


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
        progress_map[mod.id] = prog.is_completed
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
        is_completed = progress_map.get(mod.id, False)
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
                else "/media/training%20videos/Demo%20video.mp4"
            ),
            "url": "https://docs.google.com/presentation/d/1wb69ZQ4oYGYxOxzjNaTQP5bIfsB3tIKi/embed",
            "duration": mod.duration_seconds,
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
        is_completed = progress_map.get(mod.id, False)
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
    formatted_total_time = f"{total_seconds_watched // 3600:02}:{(total_seconds_watched % 3600) // 60:02}:{total_seconds_watched % 60:02}"

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

    return render(request, "pocso_act_page_corp.html", context)


# --- 7. STATIC, CHATBOT & INTERMEDIATE PAGES ---
def index(request):
    return render(request, "index.html")


def about(request):
    return render(request, "about.html")


def resources(request):
    return render(request, "resources.html")


def services(request):
    return render(request, "services.html")


def blog(request):
    return render(request, "blog.html")


def gallery(request):
    return render(request, "gallery.html")


def achievements(request):
    return render(request, "achievements.html")


def footer(request):
    return render(request, "footer.html")


def contact(request):
    return render(request, "contact.html")


def posh_T(request):
    return render(request, "posh_T.html")


def workplace(request):
    return render(request, "workplace.html")


def legal(request):
    return render(request, "legal.html")


def blogdata(request):
    return render(request, "blogdata.html")


def why_choose_ohs(request):
    return render(request, "why_choose_ohs.html")


def posh_compliance(request):
    return render(request, "posh_compliance.html")


# --- UPDATED TUTORIAL VIEW ---
def tutorial_view(request):
    # Default to showing both for non-logged in users
    show_posh = True
    show_pocso = True

    if request.user.is_authenticated:
        # Check POSH Access
        has_posh = Subscription.objects.filter(
            Q(user=request.user)
            | Q(organization__organizationmember__user=request.user),
            status="ACTIVE",
            plan__type__in=["POSH", "BOTH"],
        ).exists()

        # Check POCSO Access
        has_pocso = Subscription.objects.filter(
            Q(user=request.user)
            | Q(organization__organizationmember__user=request.user),
            status="ACTIVE",
            plan__type__in=["POCSO", "BOTH"],
        ).exists()

        # If user has POSH but not POCSO, hide POCSO
        if has_posh and not has_pocso:
            show_pocso = False

        # If user has POCSO but not POSH, hide POSH
        elif has_pocso and not has_posh:
            show_posh = False

    context = {"show_posh": show_posh, "show_pocso": show_pocso}
    return render(request, "tutorial.html", context)


def posh_assessment(request):
    return render(request, "posh_assessment.html")


def pocso_assessment(request):
    return render(request, "pocso_assessment.html")


def posh_c(request):
    return render(request, "posh_c.html")


def posh_i(request):
    return render(request, "posh_i.html")


def pocso_i(request):
    return render(request, "pocso_i.html")


def pocso_c(request):
    return render(request, "pocso_c.html")


@csrf_exempt
def chatbot_response(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            msg = data.get("message", "").strip().lower()
            if not msg:
                return JsonResponse({"error": "Empty"}, status=400)

            if msg in ["bye", "clear"]:
                return JsonResponse({"response": "Goodbye!", "reset": True})
            if "hello" in msg:
                return JsonResponse({"response": "Hi! Ask me about OHS."})

            ml_resp = predict_answer(msg)
            return JsonResponse({"response": ml_resp})
        except:
            return JsonResponse({"error": "Error"}, status=500)
    return JsonResponse({"error": "Post only"}, status=405)


# --- 8. BULK IMPORT FEATURES ---


@login_required
@login_required(login_url="login")
def download_employee_template(request):
    # Get user's organization to include the default password
    membership = OrganizationMember.objects.filter(
        user=request.user, role="ADMIN"
    ).first()

    default_password = "Welcome@123"  # Fallback
    if membership and membership.organization.default_password:
        default_password = membership.organization.default_password

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="employee_template.csv"'
    writer = csv.writer(response)
    writer.writerow(
        ["Name", "Last name", "Department", "Email", "Phone no", "Default password"]
    )
    writer.writerow(
        ["John", "Doe", "IT", "john.doe@company.com", "9876543210", default_password]
    )
    return response


@login_required
def upload_employee_bulk(request):
    if request.method == "POST" and request.FILES.get("employee_file"):
        current_user = request.user
        membership = OrganizationMember.objects.filter(
            user=current_user, role="ADMIN"
        ).first()
        if not membership:
            messages.error(request, "Unauthorized.")
            return redirect("company_dashboard")

        org = membership.organization
        csv_file = request.FILES["employee_file"]

        if not csv_file.name.endswith(".csv"):
            messages.error(request, "Please upload a CSV file.")
            return redirect("company_dashboard")

        try:
            file_data = csv_file.read().decode("utf-8-sig")
            csv_data = io.StringIO(file_data)
            reader = csv.DictReader(csv_data)

            if reader.fieldnames:
                reader.fieldnames = [name.strip() for name in reader.fieldnames]

            added_count = 0

            for row in reader:
                current_count = OrganizationMember.objects.filter(
                    organization=org
                ).count()
                if current_count >= org.max_users:
                    messages.warning(
                        request,
                        f"Limit reached. Stopped after adding {added_count} users.",
                    )
                    break

                first_name = row.get("Name", "").strip()
                last_name = row.get("Last name", "").strip()
                department = row.get("Department", "").strip()
                email = row.get("Email", "").strip()
                phone = row.get("Phone no", "").strip()
                password = row.get("Default password", "").strip()

                # Use organization's default password if not provided in CSV
                if not password:
                    password = org.default_password

                if not email or not password:
                    continue
                if User.objects.filter(email=email).exists():
                    continue

                try:
                    user = User.objects.create_user(
                        username=email, email=email, password=password
                    )
                    user.first_name = first_name
                    user.last_name = last_name
                    user.account_type = "EMPLOYEE"
                    user.force_password_change = (
                        True  # Force password change on first login
                    )

                    if hasattr(user, "department"):
                        user.department = department
                    if hasattr(user, "phone"):
                        user.phone = phone

                    user.save()

                    OrganizationMember.objects.create(
                        organization=org, user=user, role="MEMBER"
                    )

                    # Regenerate user_id after membership is created
                    user.user_id = user.generate_user_id()
                    user.save()

                    # Send welcome email
                    from home.email_utils import send_welcome_email

                    send_welcome_email(
                        user,
                        password,
                        is_company_employee=True,
                        organization_name=org.name,
                    )

                    added_count += 1
                except Exception as e:
                    continue

            if added_count > 0:
                messages.success(
                    request, f"Successfully imported {added_count} employees."
                )
            else:
                messages.warning(
                    request, "No new employees were added (check emails or duplicates)."
                )

        except Exception as e:
            messages.error(request, f"Error processing file: {str(e)}")

    return redirect("company_dashboard")


# --- 9. SUPERUSER DASHBOARD ---
@login_required
@user_passes_test(lambda u: u.is_superuser)
def superuser_dashboard(request):
    from django.db.models import Count, Q, Max
    from django.db.models.functions import TruncMonth
    from django.utils import timezone
    import datetime

    def get_monthly_counts(queryset):
        today = timezone.now().date()
        six_months_ago = today - datetime.timedelta(days=180)

        monthly_data = (
            queryset.filter(created_at__gte=six_months_ago)
            .annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )

        months_map = {}
        labels = []
        current = six_months_ago.replace(day=1)
        for i in range(6):
            next_month = (current.replace(day=28) + datetime.timedelta(days=4)).replace(
                day=1
            )
            label = current.strftime("%b")
            labels.append(label)
            months_map[current.strftime("%Y-%m")] = 0
            current = next_month

        for entry in monthly_data:
            month_str = entry["month"].strftime("%Y-%m")
            if month_str in months_map:
                months_map[month_str] = entry["count"]

        data_points = list(months_map.values())
        return labels, data_points

    def generate_svg_points(data_points):
        if not data_points:
            return ""
        max_val = max(data_points) if max(data_points) > 0 else 1
        points = []
        step_x = 100 / (len(data_points) - 1) if len(data_points) > 1 else 100

        for i, val in enumerate(data_points):
            x = i * step_x
            y = 50 - ((val / max_val) * 45)
            points.append(f"{x},{y}")
        return " ".join(points)

    all_users_count = User.objects.count()
    all_orgs = Organization.objects.all()

    total_companies = all_orgs.filter(organization_type="CORPORATE").count()
    total_schools = all_orgs.filter(organization_type="SCHOOL").count()

    users_started_training = (
        ModuleProgress.objects.filter(is_completed=True)
        .values("user")
        .distinct()
        .count()
    )

    posh_subs = Subscription.objects.filter(
        plan__type__in=["POSH", "BOTH"], status="ACTIVE"
    )
    posh_individuals = posh_subs.filter(user__isnull=False).count()
    posh_orgs_subs = posh_subs.filter(organization__isnull=False)
    posh_companies = posh_orgs_subs.filter(
        organization__organization_type="CORPORATE"
    ).count()
    posh_schools = posh_orgs_subs.filter(
        organization__organization_type="SCHOOL"
    ).count()

    posh_total = posh_individuals + posh_companies + posh_schools

    pocso_subs = Subscription.objects.filter(
        plan__type__in=["POCSO", "BOTH"], status="ACTIVE"
    )
    pocso_individuals = pocso_subs.filter(user__isnull=False).count()
    pocso_orgs_subs = pocso_subs.filter(organization__isnull=False)
    pocso_companies = pocso_orgs_subs.filter(
        organization__organization_type="CORPORATE"
    ).count()
    pocso_schools = pocso_orgs_subs.filter(
        organization__organization_type="SCHOOL"
    ).count()

    pocso_total = pocso_individuals + pocso_companies + pocso_schools

    recent_posh_orgs = (
        Organization.objects.filter(
            subscriptions__plan__type__in=["POSH", "BOTH"],
            subscriptions__status="ACTIVE",
        )
        .distinct()
        .order_by("-created_at")[:10]
    )

    recent_pocso_orgs = (
        Organization.objects.filter(
            subscriptions__plan__type__in=["POCSO", "BOTH"],
            subscriptions__status="ACTIVE",
        )
        .distinct()
        .order_by("-created_at")[:10]
    )

    posh_growth = 12
    pocso_growth = 8

    total_posh_modules = TrainingModule.objects.filter(module_type="POSH").count()
    total_pocso_modules = TrainingModule.objects.filter(module_type="POCSO").count()

    if total_posh_modules > 0:
        posh_completers = (
            User.objects.annotate(
                completed_count=Count(
                    "module_progress",
                    filter=Q(
                        module_progress__is_completed=True,
                        module_progress__module__module_type="POSH",
                    ),
                ),
                latest_completion=Max(
                    "module_progress__timestamp",
                    filter=Q(
                        module_progress__is_completed=True,
                        module_progress__module__module_type="POSH",
                    ),
                ),
            )
            .filter(completed_count=total_posh_modules)
            .order_by("-latest_completion")[:10]
        )
    else:
        posh_completers = []

    if total_pocso_modules > 0:
        pocso_completers = (
            User.objects.annotate(
                completed_count=Count(
                    "module_progress",
                    filter=Q(
                        module_progress__is_completed=True,
                        module_progress__module__module_type="POCSO",
                    ),
                ),
                latest_completion=Max(
                    "module_progress__timestamp",
                    filter=Q(
                        module_progress__is_completed=True,
                        module_progress__module__module_type="POCSO",
                    ),
                ),
            )
            .filter(completed_count=total_pocso_modules)
            .order_by("-latest_completion")[:10]
        )
    else:
        pocso_completers = []

    posh_orgs_qs = Organization.objects.filter(
        organization_type="CORPORATE",
        subscriptions__plan__type__in=["POSH", "BOTH"],
        subscriptions__status="ACTIVE",
    ).distinct()
    posh_labels, posh_data = get_monthly_counts(posh_orgs_qs)
    posh_svg_points = generate_svg_points(posh_data)
    posh_svg_area = f"0,50 {posh_svg_points} 100,50"

    posh_complete_percent = 75
    if posh_total > 0:
        posh_complete_percent = int(
            (users_started_training / (posh_total if posh_total > 0 else 1)) * 100
        )
        posh_complete_percent = min(posh_complete_percent, 100)

    pocso_orgs_qs = Organization.objects.filter(
        organization_type="SCHOOL",
        subscriptions__plan__type__in=["POCSO", "BOTH"],
        subscriptions__status="ACTIVE",
    ).distinct()
    pocso_labels, pocso_data = get_monthly_counts(pocso_orgs_qs)
    pocso_svg_points = generate_svg_points(pocso_data)
    pocso_svg_area = f"0,50 {pocso_svg_points} 100,50"

    pocso_complete_percent = 60
    if pocso_total > 0:
        pocso_complete_percent = int(
            (users_started_training / (pocso_total if pocso_total > 0 else 1)) * 100
        )
        pocso_complete_percent = min(pocso_complete_percent, 100)

    context = {
        "total_users": all_users_count,
        "total_companies": total_companies,
        "total_schools": total_schools,
        "training_completed_count": users_started_training,
        "posh_counts": {
            "total": posh_total,
            "individuals": posh_individuals,
            "companies": posh_companies,
            "schools": posh_schools,
            "growth": posh_growth,
            "chart_labels": posh_labels,
            "chart_points": posh_svg_points,
            "chart_area": posh_svg_area,
            "complete_percent": posh_complete_percent,
            "pending_percent": 100 - posh_complete_percent,
            "completers": posh_completers,
        },
        "pocso_counts": {
            "total": pocso_total,
            "individuals": pocso_individuals,
            "companies": pocso_companies,
            "schools": pocso_schools,
            "growth": pocso_growth,
            "chart_labels": pocso_labels,
            "chart_points": pocso_svg_points,
            "chart_area": pocso_svg_area,
            "complete_percent": pocso_complete_percent,
            "pending_percent": 100 - pocso_complete_percent,
            "completers": pocso_completers,
        },
        "recent_posh_orgs": recent_posh_orgs,
        "recent_pocso_orgs": recent_pocso_orgs,
    }
    return render(request, "superuser_dashboard.html", context)


def custom_logout(request):
    logout(request)
    return redirect("home")


def download_certificate(request, course_type="POSH"):
    if not request.user.is_authenticated:
        return redirect("login")

    # Check if downloading for another user (company admin)
    user_id = request.GET.get("user_id")
    if user_id:
        # Verify that the requester is an admin of the organization
        try:
            target_user = User.objects.get(id=user_id)
            # Check if current user is admin
            is_admin = OrganizationMember.objects.filter(
                user=request.user, role="ADMIN"
            ).exists()

            if not is_admin:
                messages.error(request, "Access denied. Admin privileges required.")
                return redirect("company_dashboard")

            # Check if target user is in same organization
            target_membership = OrganizationMember.objects.filter(
                user=target_user
            ).first()
            admin_membership = OrganizationMember.objects.filter(
                user=request.user, role="ADMIN"
            ).first()

            if (
                not target_membership
                or not admin_membership
                or target_membership.organization != admin_membership.organization
            ):
                messages.error(
                    request,
                    "Cannot download certificate for user outside your organization.",
                )
                return redirect("company_dashboard")

            certificate_user = target_user
        except User.DoesNotExist:
            messages.error(request, "User not found.")
            return redirect("company_dashboard")
    else:
        certificate_user = request.user

    # 1. Check Completion
    # Re-using logic from posh_act_page roughly
    # In a real app, maybe extract this check to a helper
    if course_type == "POSH":
        modules = TrainingModule.objects.filter(module_type="POSH")
        total = modules.count()
        # Count COMPLETED modules for this user
        completed = ModuleProgress.objects.filter(
            user=certificate_user, module__in=modules, is_completed=True
        ).count()

        # Strict check: Must be 100% complete
        if total == 0 or completed < total:
            messages.error(
                request,
                "Training must be completed before downloading the certificate.",
            )
            return (
                redirect("posh_act_page")
                if not user_id
                else redirect("company_dashboard")
            )

        # CHECK FINAL ASSESSMENT (NEW)
        has_passed_assessment = AssessmentProgress.objects.filter(
            user=certificate_user, assessment_type="POSH", is_passed=True
        ).exists()
        if not has_passed_assessment:
            messages.error(
                request, "Final Quiz must be passed to download the certificate."
            )
            return (
                redirect("posh_act_page")
                if not user_id
                else redirect("company_dashboard")
            )

    elif course_type == "POCSO":
        # Check POCSO completion
        modules = TrainingModule.objects.filter(module_type="POCSO")
        total = modules.count()
        completed = ModuleProgress.objects.filter(
            user=certificate_user, module__in=modules, is_completed=True
        ).count()

        if total == 0 or completed < total:
            messages.error(
                request,
                "Training must be completed before downloading the certificate.",
            )
            return (
                redirect("pocso_act_page")
                if not user_id
                else redirect("company_dashboard")
            )

        has_passed_assessment = AssessmentProgress.objects.filter(
            user=certificate_user, assessment_type="POCSO", is_passed=True
        ).exists()
        if not has_passed_assessment:
            messages.error(
                request, "Final Quiz must be passed to download the certificate."
            )
            return (
                redirect("pocso_act_page")
                if not user_id
                else redirect("company_dashboard")
            )

    # 2. Generate PDF
    pdf_content = generate_certificate(certificate_user, course_type)

    if not pdf_content:
        messages.error(request, "Error generating certificate. Please contact support.")
        return (
            redirect("posh_act_page") if not user_id else redirect("company_dashboard")
        )

    # 3. Serve PDF
    response = HttpResponse(pdf_content, content_type="application/pdf")
    filename = f"Certificate_{course_type}_{certificate_user.username}.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# In your Django Form
def clean_phone(self):
    phone = self.cleaned_data.get("phone")
    if not phone.isdigit() or len(phone) != 10:
        raise forms.ValidationError("Invalid phone number")
    return phone


def custom_404(request, exception):
    return render(request, "hh.html", status=404)


def custom_403(request, exception):
    return render(request, "hh.html", status=403)


def custom_500(request):
    return render(request, "hh.html", status=500)


def custom_402(request, exception=None):
    return render(request, "hh.html", status=402)
