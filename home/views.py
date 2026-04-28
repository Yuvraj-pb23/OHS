import csv
import io
import json
import logging
import os
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

from home.models import POCSORegistration, POSHRegistration

# Ensure this file exists in your app or adjust import accordingly
from .chatbot_logic import predict_answer

# Models
# Ensure your User model has 'phone' and 'department' fields if you want to save them to the DB.
from .models import (
    AssessmentProgress,
    DailyActivity,
    EmailTemplate,
    ModuleProgress,
    Organization,
    OrganizationMember,
    POCSOPricingConfig,
    POSHPricingConfig,
    Subscription,
    SubscriptionPlan,
    TrainingModule,
    User,
)
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
            # messages.success(request, "Company logo uploaded successfully!")
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
    # messages.success(request, "Logo position and size reset to default.")
    return redirect("company_dashboard")


# --- 0. CUSTOM LOGIN VIEW ---
def custom_login_view(request):
    from django.contrib.auth import authenticate, get_user_model, login
    from django.db.models import Q

    from .models import Organization

    if request.method == "POST":
        u = request.POST.get("username")
        p = request.POST.get("password")

        # Try standard authentication first
        user = authenticate(username=u, password=p)
        if user is not None:
            login(request, user)
            if "hr_as_employee" in request.session:
                del request.session["hr_as_employee"]
            return redirect("custom_login_redirect")

        # Check if HR is using company default password
        User = get_user_model()
        user_obj = User.objects.filter(Q(username=u) | Q(email=u)).first()
        if user_obj and user_obj.account_type == "COMPANY_ADMIN":
            org = Organization.objects.filter(owner=user_obj).first()
            if org and org.default_password and org.default_password == p:
                login(
                    request,
                    user_obj,
                    backend="django.contrib.auth.backends.ModelBackend",
                )
                request.session["hr_as_employee"] = True
                return redirect("custom_login_redirect")

        # Fallback error
        class MockForm:
            errors = True

        return render(request, "login.html", {"form": MockForm()})

    return render(request, "login.html")


# --- 1. LOGIN REDIRECT LOGIC ---
@login_required
def custom_login_redirect(request):
    user = request.user

    # 0. SUPERUSER -> Superuser Dashboard
    if user.is_superuser:
        return redirect("superuser_dashboard")

    # 1. ADMIN -> Dashboard
    if user.account_type == "COMPANY_ADMIN":
        if request.session.get("hr_as_employee"):
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
            if has_posh:
                return redirect("posh_act_page_corp")
            if has_pocso:
                return redirect("pocso_act_page_corp")
            return redirect("tutorial")

        return redirect("company_dashboard")

    # 1.5 ACCOUNTS -> Accounts Dashboard
    if user.account_type == "ACCOUNTS":
        return redirect("accounts_dashboard")

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

        # messages.success(request, "Password changed successfully!")
        return redirect("custom_login_redirect")

    return render(request, "force_password_change.html")


# --- OTP VIEWS FOR COMPANY REGISTRATION EMAIL VERIFICATION ---
@csrf_exempt
def send_registration_otp(request):
    """Generate and email a 6-digit OTP for registration email verification."""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Invalid method."}, status=405)
    try:
        data = json.loads(request.body)
        email = data.get("email", "").strip()
    except Exception:
        email = request.POST.get("email", "").strip()

    if not email or "@" not in email:
        return JsonResponse(
            {"success": False, "error": "Please enter a valid email address."}
        )
    if User.objects.filter(email=email).exists():
        return JsonResponse(
            {"success": False, "error": "This email is already registered."}
        )

    import time

    otp = str(secrets.randbelow(900000) + 100000)
    request.session["reg_otp"] = otp
    request.session["reg_otp_email"] = email
    request.session["reg_otp_verified"] = False
    request.session["reg_otp_ts"] = time.time()  # store generation timestamp
    request.session.modified = True

    from django.core.mail import send_mail

    try:
        send_mail(
            subject="Your OTP - Open Hand Solutions Registration",
            message=(
                f"Hello,\n\n"
                f"Your one-time password (OTP) for Corporate Registration is:\n\n"
                f"    {otp}\n\n"
                f"This OTP is valid for 2 minutes only.\n"
                f"Do not share it with anyone.\n\n"
                f"Best regards,\nOpen Hand Solutions Team"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
        return JsonResponse({"success": True, "message": "OTP sent to your email."})
    except Exception as e:
        return JsonResponse(
            {"success": False, "error": f"Failed to send email: {str(e)}"}
        )


@csrf_exempt
def verify_registration_otp(request):
    """Verify the submitted OTP against the session-stored OTP."""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Invalid method."}, status=405)
    try:
        data = json.loads(request.body)
        submitted = str(data.get("otp", "")).strip()
        email = data.get("email", "").strip()
    except Exception:
        submitted = str(request.POST.get("otp", "")).strip()
        email = request.POST.get("email", "").strip()

    session_otp = request.session.get("reg_otp", "")
    session_email = request.session.get("reg_otp_email", "")
    otp_ts = request.session.get("reg_otp_ts", 0)

    if not session_otp:
        return JsonResponse(
            {"success": False, "error": "No OTP found. Please request a new one."}
        )
    if email != session_email:
        return JsonResponse(
            {"success": False, "error": "Email mismatch. Please request a new OTP."}
        )

    import time

    if time.time() - otp_ts > 120:  # 2-minute expiry
        # Clear expired OTP
        request.session.pop("reg_otp", None)
        request.session.pop("reg_otp_ts", None)
        request.session.modified = True
        return JsonResponse(
            {
                "success": False,
                "error": "OTP expired. Please request a new one.",
                "expired": True,
            }
        )

    if submitted == session_otp:
        request.session["reg_otp_verified"] = True
        request.session.modified = True
        return JsonResponse(
            {"success": True, "message": "Email verified successfully!"}
        )
    return JsonResponse({"success": False, "error": "Incorrect OTP. Please try again."})


# --- 2. COMPANY SUBSCRIPTION (FORM) ---
def company_subscription(request, plan_type):
    db_type = "POSH" if "POSH" in plan_type else "POCSO"
    plan = SubscriptionPlan.objects.filter(type=db_type).first()

    if request.method == "POST":
        comp_name = request.POST.get("company_name", "").strip()
        seats = request.POST.get("seats", 10)
        fullname = request.POST.get("fullname", "").strip()
        password = request.POST.get("password", "").strip()

        # If a setup_token is in the POST, decode the email from it (tamper-proof)
        setup_token = request.POST.get("setup_token", "").strip()
        if setup_token:
            try:
                from django.core import signing

                payload = signing.loads(
                    setup_token, salt="posh-admin-setup", max_age=60 * 60 * 72
                )  # 72h
                email = payload["email"]
                # Auto-populate company name from the POSH registration
                logger = logging.getLogger(__name__)
                if not comp_name:

                    try:

                        posh_reg = POSHRegistration.objects.get(id=payload["reg_id"])
                        comp_name = posh_reg.company_name
                        seats = posh_reg.employee_count or seats

                    except POSHRegistration.DoesNotExist:
                        logger.warning(
                            f"POSHRegistration not found for reg_id={payload.get('reg_id')}"
                        )

                    except Exception as e:
                        logger.exception(
                            f"Unexpected error while fetching POSHRegistration: {e}"
                        )

            except Exception as e:
                logger.exception(f"Invalid setup link payload: {e}")

                messages.error(
                    request, "Invalid or expired setup link. Please contact support."
                )
                return redirect(request.path)
        else:
            email = request.POST.get("email", "").strip()

        if not comp_name:
            comp_name = f"{fullname}'s Organization"

        # Restriction: Email must be OTP-verified (skip if coming from verified setup link)
        if not setup_token:
            if (
                not request.session.get("reg_otp_verified")
                or request.session.get("reg_otp_email") != email
            ):
                messages.error(
                    request, "Please verify your email with the OTP before submitting."
                )
                return redirect(request.path)

        # Restriction: Ensure all info is compulsory
        if not all([fullname, email, password]):
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

    # --- GET ---
    else:
        list(messages.get_messages(request))

    # Decode setup_token on GET to pre-fill and lock the email field
    locked_email = None
    setup_token = request.GET.get("setup_token", "").strip()
    if setup_token:
        try:
            from django.core import signing

            payload = signing.loads(
                setup_token, salt="posh-admin-setup", max_age=60 * 60 * 72
            )
            locked_email = payload["email"]
        except Exception:
            messages.error(
                request,
                "This setup link has expired or is invalid. Please contact support.",
            )

    response = render(
        request,
        "company_signup.html",
        {
            "plan_type": plan_type,
            "locked_email": locked_email,
            "setup_token": setup_token,
        },
    )
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
        current_count = OrganizationMember.objects.filter(
            organization=org, role="MEMBER"
        ).count()
        if current_count >= org.max_users:
            messages.error(
                request,
                f"Seat limit reached ({org.max_users}). Upgrade plan to add more.",
            )
            return redirect("company_dashboard")

        emp_name = request.POST.get("emp_name")
        emp_email = request.POST.get("emp_email")
        emp_password = request.POST.get("emp_password")
        emp_designation = request.POST.get("emp_designation", "").strip()

        # Use employee_count from POSH registration as the seat limit if available

        posh_reg = POSHRegistration.objects.filter(email=org.owner.email).first()
        seat_limit = posh_reg.employee_count if posh_reg else org.max_users

        if current_count >= seat_limit:
            messages.error(
                request,
                f"Employee limit reached ({seat_limit} from registration). Contact Open Hand Solutions to expand.",
            )
            return redirect("company_dashboard")

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
                new_user.designation = emp_designation or None
                new_user.force_password_change = (
                    True  # Force password change on first login
                )
                # Generate user_id by passing org directly (avoids querying unsaved relationships)
                new_user.user_id = new_user.generate_user_id(organization=org)
                new_user.save()

                OrganizationMember.objects.create(
                    organization=org, user=new_user, role="MEMBER"
                )

                # Send welcome email with credentials + training link
                from django.conf import settings as django_settings

                from home.email_utils import send_welcome_email

                site_base = getattr(
                    django_settings, "SITE_URL", "https://openhandsolutions.com"
                )
                training_link = f"{site_base}/login/"
                company_name = posh_reg.company_name if posh_reg else org.name

                send_welcome_email(
                    new_user,
                    emp_password,
                    is_company_employee=True,
                    organization_name=company_name,
                    training_link=training_link,
                    designation=emp_designation,
                )

            # messages.success(request, f"{emp_name} added successfully!")
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
    print("COMPANY DASHBOARD VIEW IS CALLED!!!")
    # Check if user logged out from HR portal
    if request.session.get("logged_out_of_hr"):
        request.session.pop("logged_out_of_hr", None)

    user = request.user
    membership = OrganizationMember.objects.filter(user=user, role="ADMIN").first()

    if not membership:
        messages.error(request, "Access Denied. Admin only.")
        return redirect("tutorial")

    org = membership.organization
    active_sub = Subscription.objects.filter(organization=org, status="ACTIVE").first()
    members = OrganizationMember.objects.filter(
        organization=org, role="MEMBER"
    ).select_related("user")

    # --- DATA CALCULATION FOR HTML ---
    total_employees = members.count()

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
        mem.video_modules = [
            m
            for m in mem_modules_status
            if not m["is_ppt"] or "quiz" in m["title"].lower()
        ]
        mem.video_lesson_modules = [
            m for m in mem.video_modules if "quiz" not in m["title"].lower()
        ]
        mem.ppt_modules = [
            m
            for m in mem_modules_status
            if m["is_ppt"] and "quiz" not in m["title"].lower()
        ]

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
        mem.employee_id = user_obj.user_id if user_obj else None
        # Check if employee has passed the final quiz (for certificate eligibility)
        has_passed_quiz = AssessmentProgress.objects.filter(
            user=user_obj, assessment_type=training_type, is_passed=True
        ).exists()
        mem.has_certificate = has_passed_quiz and mem.is_training_completed

        # Quiz completion — check practice quiz module progress (module titled 'quiz')
        quiz_module = next(
            (
                m
                for m in all_modules
                if "quiz" in m.title.lower() and m.ppt_file and not m.video_file
            ),
            None,
        )
        if quiz_module:
            quiz_prog = ModuleProgress.objects.filter(
                user=user_obj, module=quiz_module
            ).first()
            mem.quiz_completed = quiz_prog.is_completed if quiz_prog else False
        else:
            mem.quiz_completed = False

        # Assessment score (if formal assessment exists for this type)
        assessment = AssessmentProgress.objects.filter(
            user=user_obj, assessment_type=training_type
        ).first()
        mem.quiz_score = assessment.score if assessment else None
        mem.quiz_passed = assessment.is_passed if assessment else False

    training_pending = total_employees - training_completed_count

    # Get employees with certificates
    certified_employees = [
        m for m in members if hasattr(m, "has_certificate") and m.has_certificate
    ]

    # Look up the company name from POSH registration by the org owner's email

    posh_reg = POSHRegistration.objects.filter(email=org.owner.email).first()
    posh_company_name = posh_reg.company_name if posh_reg else org.name

    # If org name is still the auto-generated fallback, update it + regenerate password
    if posh_reg and (
        org.name == f"{org.owner.first_name}'s Organization" or not org.name
    ):
        org.name = posh_reg.company_name
        org.default_password = org.generate_default_password()
        org.save()

    # Ensure organization has a default password (generate if missing)
    if not org.default_password:
        org.default_password = org.generate_default_password()
        org.save()

    # Force-regenerate password if prefix doesn't match company name
    # (handles case where org name was corrected but old password was already saved)
    expected_prefix = "".join(c for c in org.name if c.isalnum())[:4].upper()
    if org.default_password and not org.default_password.upper().startswith(
        expected_prefix
    ):
        org.default_password = org.generate_default_password()
        org.save()

    seat_limit = posh_reg.employee_count if posh_reg else org.max_users

    context = {
        "organization": org,
        "posh_company_name": posh_company_name,
        "posh_reg_employee_count": seat_limit,
        "active_plan": active_sub,
        "members": members,
        "seats_used": total_employees,
        "seats_remaining": max(seat_limit - total_employees, 0),
        "total_employees": total_employees,
        "training_completed": training_completed_count,
        "training_pending": training_pending,
        "total_modules_count": total_modules_count,
        "certified_employees": certified_employees,
        "training_type": training_type,
        "default_password": org.default_password,
        "logout_url": "hr_logout",
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
            "src": (
                mod.video_file.url
                if mod.video_file
                else "/media/training_videos/POSH_Training_Video.mp4"
            ),
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
        "formatted_total_time": (
            f"{total_seconds_watched // 3600:02}:"
            f"{(total_seconds_watched % 3600) // 60:02}:"
            f"{total_seconds_watched % 60:02}"
        ),
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
            score_raw = int(data.get("score", 0))
            total_q = int(data.get("total", 15)) # Default to 15 if not provided

            # Calculate percentage accurately
            percentage = int((score_raw / total_q) * 100) if total_q > 0 else score_raw
            
            # Enforce 80% pass threshold globally
            passed = percentage >= 80

            progress, created = AssessmentProgress.objects.get_or_create(
                user=request.user, assessment_type=assessment_type
            )
            progress.score = percentage # Store percentage as score for HR dashboard
            progress.is_passed = passed
            progress.save()

            # If failed, reset module progress so they have to watch videos again
            if not passed:
                from home.models import ModuleProgress, TrainingModule
                ModuleProgress.objects.filter(
                    user=request.user,
                    module__module_type=assessment_type
                ).delete()

            return JsonResponse({"status": "success", "message": "Result saved", "passed": passed, "score_percent": percentage})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=500)
    return JsonResponse({"status": "error", "message": "Invalid method"}, status=400)


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

    # Initialize progress for all modules if not exists
    for mod in modules:
        prog, created = ModuleProgress.objects.get_or_create(user=user, module=mod)
        progress_map[mod.id] = prog.is_completed

    # Only video and quiz modules are part of corp training flow now.
    visible_modules = [
        m
        for m in modules
        if m.video_file
        or (m.ppt_file and not m.video_file and "quiz" in m.title.lower())
    ]
    completed_count = sum(1 for m in visible_modules if progress_map.get(m.id, False))

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
                else "/media/training_videos/POSH_Training_Video.mp4"
            ),
            # UPDATED: Use new hardcoded path for demo video
            "url": "https://docs.google.com/presentation/d/1wb69ZQ4oYGYxOxzjNaTQP5bIfsB3tIKi/embed",
            "duration": mod.duration_seconds,
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
        is_completed = progress_map.get(mod.id, False)
        # Lock the quiz until all video modules are completed
        all_videos_done = all(progress_map.get(v.id, False) for v in video_modules)
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

    context = {
        "show_posh": show_posh,
        "show_pocso": show_pocso,
        "logout_url": "training_logout",
    }
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
        except Exception:
            return JsonResponse({"error": "Error"}, status=500)
    return JsonResponse({"error": "Post only"}, status=405)


# --- 8. BULK IMPORT FEATURES ---


@login_required
@login_required(login_url="login")
def download_employee_template(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        'attachment; filename="employee_template_no_password.csv"'
    )
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    writer = csv.writer(response)
    writer.writerow(["Name", "Last name", "Department", "Email", "Phone no"])
    writer.writerow(["John", "Doe", "IT", "john.doe@company.com", "9876543210"])
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
        posh_reg = POSHRegistration.objects.filter(email=org.owner.email).first()
        seat_limit = posh_reg.employee_count if posh_reg else org.max_users
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
                    organization=org, role="MEMBER"
                ).count()
                if current_count >= seat_limit:
                    messages.warning(
                        request,
                        f"Limit reached ({seat_limit} from registration). Stopped after adding {added_count} users.",
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
                    logger.warning(f"Skipping employee import row: {e}")
                    continue

            if added_count > 0:
                # messages.success(
                #     request, f"Successfully imported {added_count} employees."
                # )
                pass
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
    import datetime

    from django.db.models import Count, Max, Q
    from django.db.models.functions import TruncMonth
    from django.utils import timezone

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
    # messages.success(request, "Successfully logged out.")
    return redirect("home")


def accounts_logout(request):
    """Fully log out the accounts user and clear the session."""
    logout(request)
    # messages.success(request, "Successfully signed out from Accounts Portal.")
    return redirect("home")


def hr_logout(request):
    """Logout for HR/Company Dashboard users - keeps user authenticated but removes portal access"""
    request.session["logged_out_of_hr"] = True
    # messages.success(request, "Successfully logged out from HR Portal.")
    return redirect("home")


def training_logout(request):
    """Logout for Training users - keeps user authenticated but removes portal access"""
    request.session["logged_out_of_training"] = True
    if "hr_as_employee" in request.session:
        del request.session["hr_as_employee"]
    # messages.success(request, "Successfully logged out from Training Portal.")
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


def custom_404(request, exception):
    return render(request, "hh.html", status=404)


def custom_403(request, exception):
    return render(request, "hh.html", status=403)


def custom_500(request):
    return render(request, "hh.html", status=500)


def custom_402(request, exception=None):
    return render(request, "hh.html", status=402)


def get_posh_pricing_context(registration):
    """Refactored helper to calculate POSH billing context for both billing_view and admin review"""
    from .utils import get_posh_billing_data

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
        "total_tier_2": billing_data["total_amount"] * 0.9,
        "total_tier_1": billing_data["total_amount"] * 0.8,
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

    context = get_posh_pricing_context(registration)
    return render(request, "billing.html", context)


def accounts_login_view(request):
    """Custom login for accounts department"""
    if request.method == "POST":
        u = request.POST.get("username")
        p = request.POST.get("password")
        user = authenticate(username=u, password=p)
        if user is not None and (user.account_type == "ACCOUNTS" or user.is_superuser):
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            return redirect("accounts_dashboard")
        else:
            return render(
                request,
                "accounts_login.html",
                {"form": type("F", (), {"errors": True})()},
            )

    return render(request, "accounts_login.html", {})


@login_required(login_url="accounts_login")
def accounts_dashboard_view(request):
    """Pricing configuration dashboard for the Accounts Department"""
    # Check if user logged out from Accounts portal
    if request.session.get("logged_out_of_accounts"):
        request.session.pop("logged_out_of_accounts", None)

    if request.user.account_type != "ACCOUNTS" and not request.user.is_superuser:
        return redirect("home")

    config = (
        POSHPricingConfig.objects.filter(is_active=True).order_by("-updated_at").first()
    )
    pocso_config = (
        POCSOPricingConfig.objects.filter(is_active=True)
        .order_by("-updated_at")
        .first()
    )

    registrations = POSHRegistration.objects.all().order_by("-created_at")
    pocso_registrations = POCSORegistration.objects.all().order_by("-created_at")

    saved = request.session.pop("pricing_saved", False)
    pocso_saved = request.session.pop("pocso_pricing_saved", False)
    email_saved = request.session.pop("email_templates_saved", False)

    email_tiers = [
        ("PAY_NOW", "Payment Received Confirmation"),
        ("PAYMENT_VERIFIED", "Payment Verified – Onboarding Confirmed"),
        ("EMPLOYEE_WELCOME", "Employee Welcome – Account Credentials"),
    ]

    email_templates = {et.tier_key: et for et in EmailTemplate.objects.all()}

    return render(
        request,
        "accounts_dashboard.html",
        {
            "config": config,
            "pocso_config": pocso_config,
            "registrations": registrations,
            "pocso_registrations": pocso_registrations,
            "saved": saved,
            "pocso_saved": pocso_saved,
            "email_saved": email_saved,
            "email_tiers": email_tiers,
            "email_templates": email_templates,
        },
    )


@login_required(login_url="accounts_login")
def accounts_save_email_templates_view(request):
    """Save updated email templates from the accounts portal"""
    if request.user.account_type != "ACCOUNTS" and not request.user.is_superuser:
        return redirect("home")

    if request.method == "POST":
        tiers = ["PAY_NOW", "PAYMENT_VERIFIED", "EMPLOYEE_WELCOME"]
        for tier in tiers:
            subject = request.POST.get(f"subject_{tier}")
            body = request.POST.get(f"body_{tier}")

            if subject or body:
                template, created = EmailTemplate.objects.get_or_create(tier_key=tier)
                if subject:
                    template.subject = subject
                if body:
                    template.body = body
                template.save()

        request.session["email_templates_saved"] = True
        # messages.success(request, "Email templates updated successfully!")

    from django.urls import reverse

    return redirect(f"{reverse('accounts_dashboard')}?active_tab=emails")


@csrf_exempt
def trigger_tier_email_view(request):
    """AJAX view to trigger a tiered email based on user selection"""
    if request.method == "POST":
        import json

        try:
            data = json.loads(request.body)
            registration_id = data.get("registration_id")
            tier_key = data.get("tier_key")
            registration_type = data.get("registration_type", "POSH")

            if registration_type == "POSH":
                registration = get_object_or_404(POSHRegistration, id=registration_id)
            else:
                registration = get_object_or_404(POCSORegistration, id=registration_id)

            from .email_utils import send_tiered_email

            success = send_tiered_email(registration, tier_key, registration_type)

            if success:
                return JsonResponse({"status": "success"})
            else:
                return JsonResponse(
                    {"status": "error", "message": "Email failed to send"}, status=500
                )
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=400)

    return JsonResponse({"status": "error", "message": "Invalid request"}, status=405)


logger = logging.getLogger(__name__)


@login_required(login_url="accounts_login")
def accounts_verify_payment_view(request, registration_id):
    """Mark a registration as verified by the accounts department"""

    if request.user.account_type != "ACCOUNTS" and not request.user.is_superuser:
        return redirect("home")

    registration = get_object_or_404(POSHRegistration, id=registration_id)

    registration.payment_status = "VERIFIED"
    registration.is_paid = True
    registration.save()

    # Send payment verification email
    try:
        from .email_utils import send_tiered_email

        send_tiered_email(registration, "PAYMENT_VERIFIED", "POSH")

    except Exception as e:
        logger.warning(
            f"Payment verified but email failed for {registration.company_name}: {e}"
        )

    # messages.success(
    #     request,
    #     f"Payment for {registration.company_name} verified successfully!",
    # )

    return redirect("accounts_dashboard")


@login_required(login_url="accounts_login")
def accounts_reject_payment_view(request, registration_id):
    """Reject a payment and return it to pending status"""
    if request.user.account_type != "ACCOUNTS" and not request.user.is_superuser:
        return redirect("home")

    registration = get_object_or_404(POSHRegistration, id=registration_id)
    registration.payment_status = "PENDING"
    registration.save()

    messages.warning(request, f"Payment for {registration.company_name} rejected.")
    return redirect("accounts_dashboard")


@login_required(login_url="accounts_login")
def accounts_registration_detail_view(request, registration_id):
    """Full registration detail for billing review with calculated context"""
    if request.user.account_type != "ACCOUNTS" and not request.user.is_superuser:
        return redirect("home")

    registration = get_object_or_404(POSHRegistration, id=registration_id)
    context = get_posh_pricing_context(registration)
    return render(request, "accounts_registration_detail.html", context)


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


logger = logging.getLogger(__name__)


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
        from .email_utils import send_tiered_email

        send_tiered_email(registration, "PAYMENT_VERIFIED", "POCSO")

    except Exception as e:
        logger.warning(
            f"Payment verified but email failed for {registration.school_name}: {e}"
        )

    # messages.success(
    #     request,
    #     f"Payment for {registration.school_name} verified successfully!",
    # )

    return redirect("accounts_dashboard")


@login_required(login_url="accounts_login")
def accounts_reject_pocso_payment_view(request, registration_id):
    """Reject/reset a POCSO payment status back to PENDING"""
    if request.user.account_type != "ACCOUNTS" and not request.user.is_superuser:
        return redirect("home")
    registration = get_object_or_404(POCSORegistration, id=registration_id)
    registration.payment_status = "PENDING"
    registration.save()
    messages.warning(
        request, f"Payment for {registration.school_name} has been rejected."
    )
    return redirect("accounts_dashboard")


def get_pocso_pricing_context(registration):
    """Refactored helper to calculate POCSO billing context for both customer billing and admin review"""
    from .utils import get_pocso_billing_data

    billing_data = get_pocso_billing_data(registration)

    return {
        "reg": registration,
        "registration": registration,
        "addon_fees": billing_data["addon_fees"],
        "subtotal": billing_data["subtotal"],
        "gst_percentage": billing_data["gst_percentage"],
        "tax": billing_data["gst_amount"],
        "total": billing_data["total_amount"],
        "total_tier_1": billing_data["total_amount"] * 0.8,
        "total_tier_2": billing_data["total_amount"] * 0.9,
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
    return render(request, "accounts_pocso_registration_detail.html", context)


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


def registration_selection_view(request):
    """Simple selection page between POSH and POCSO registration"""
    return render(request, "registration_selection.html")


def posh_registration_view(request):
    """Handle POSH compliance registration submission"""
    if request.method == "POST":
        data = request.POST

        # Determine IC training mode from hidden fields or radio
        ic_training_mode = data.get("requested_ic_training_mode")
        expert_led_type = data.get("requested_expert_led_type")

        reg = POSHRegistration(
            contact_person=data.get("contact_person"),
            designation=data.get("designation"),
            city=data.get("city"),
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

    return render(request, "posh_registration.html", {"registration": registration})


def pocso_registration_view(request):
    """Handle POCSO compliance registration submission"""
    if request.method == "POST":
        data = request.POST
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

    return render(request, "pocso_registration.html", {"registration": registration})


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

    context = get_pocso_pricing_context(registration)
    return render(request, "pocso_billing.html", context)


def submit_payment_view(request, registration_id):
    """Handle payment screenshot upload for POSH/POCSO"""
    # Detect type from URL or session if possible, or try both models
    registration = POSHRegistration.objects.filter(id=registration_id).first()
    reg_type = "POSH"

    if not registration:
        registration = get_object_or_404(POCSORegistration, id=registration_id)
        reg_type = "POCSO"

    if request.method == "POST":
        screenshot = request.FILES.get("payment_screenshot")
        if screenshot:
            registration.payment_screenshot = screenshot
            registration.payment_status = "SUBMITTED"
            registration.save()

            # Send 'PAY_NOW' email
            from .email_utils import send_tiered_email

            send_tiered_email(registration, "PAY_NOW", reg_type)

            # Redirect to the respective billing page to show the success screen
            if reg_type == "POSH":
                return redirect("billing")
            else:
                return redirect("pocso_billing")

    return render(request, "submit_payment.html", {"registration": registration})

    return render(request, "submit_payment.html", {"registration": registration})
