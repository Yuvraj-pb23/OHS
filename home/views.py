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
from django.views.decorators.http import require_POST
from PIL import Image




# Models
# Ensure your User model has 'phone' and 'department' fields if you want to save them to the DB.
from .models import (
    AssessmentProgress,
    DailyActivity,
    EmailTemplate,
    ModuleProgress,
    Organization,
    OrganizationMember,
    POCSORegistration,
    POSHRegistration,
    PosterLogoConfig,
    POCSOPricingConfig,
    POSHPricingConfig,
    Subscription,
    SubscriptionPlan,
    TrainingModule,
    User,
    POSHPolicy,
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
        logo = request.FILES.get("company_logo") or request.FILES.get("logo")
        poster_path = request.POST.get("poster_path")
        if logo:
            valid_exts = [".png", ".jpg", ".jpeg", ".webp"]
            ext = os.path.splitext(logo.name)[1].lower()
            is_image_mime = logo.content_type and logo.content_type.startswith("image/")
            if ext not in valid_exts or logo.size > 2 * 1024 * 1024 or not is_image_mime:
                err_msg = "Invalid file. Logo must be a PNG, JPG, JPEG, or WEBP image under 2MB."
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return JsonResponse({"status": "error", "message": err_msg}, status=400)
                messages.error(request, err_msg)
                return redirect("/dashboard/company/?section=posters&open_editor=true")
            
            try:
                from PIL import Image
                img = Image.open(logo)
                img.verify()
                logo.seek(0)
            except Exception:
                err_msg = "Invalid image file. The uploaded file is corrupted or not a valid image."
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return JsonResponse({"status": "error", "message": err_msg}, status=400)
                messages.error(request, err_msg)
                return redirect("/dashboard/company/?section=posters&open_editor=true")

            if poster_path:
                from .models import PosterLogoConfig
                config, created = PosterLogoConfig.objects.get_or_create(
                    organization=org, poster_path=poster_path
                )
                config.logo = logo
                config.save()
                logo_url = config.logo.url
            else:
                org.logo = logo
                org.save()
                logo_url = org.logo.url

            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"status": "success", "logo_url": logo_url})
        else:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse(
                    {"status": "error", "message": "No logo file selected."}, status=400
                )
            messages.error(request, "No logo file selected.")

    return redirect("/dashboard/company/?section=posters&open_editor=true")


@login_required(login_url="login")
def upload_org_logo(request):
    """View to upload organization/custom logo via AJAX for certificates"""
    if request.method == "POST":
        logo = request.FILES.get("logo") or request.FILES.get("company_logo")
        if not logo:
            return JsonResponse({"status": "error", "message": "No logo file selected."}, status=400)

        # Validate file size and extension
        valid_exts = [".png", ".jpg", ".jpeg", ".webp"]
        ext = os.path.splitext(logo.name)[1].lower()
        is_image_mime = logo.content_type and logo.content_type.startswith("image/")
        if ext not in valid_exts or logo.size > 2 * 1024 * 1024 or not is_image_mime:
            return JsonResponse({
                "status": "error", 
                "message": "Invalid file. Logo must be a PNG, JPG, JPEG, or WEBP image under 2MB."
            }, status=400)

        # Verify using Pillow
        try:
            from PIL import Image
            img = Image.open(logo)
            img.verify()
            logo.seek(0)
        except Exception:
            return JsonResponse({
                "status": "error",
                "message": "Invalid image file. The uploaded file is corrupted or not a valid image."
            }, status=400)

        current_user = request.user
        membership = OrganizationMember.objects.filter(user=current_user).first()
        
        if membership:
            # Save to organization
            org = membership.organization
            org.logo = logo
            org.save()
            logo_url = org.logo.url
            # Also store in session for the current download session
            request.session['temp_logo_path'] = org.logo.path
        else:
            # Save to a temporary folder in MEDIA_ROOT for individual users
            from django.core.files.storage import default_storage
            from django.core.files.base import ContentFile
            import uuid
            
            ext = os.path.splitext(logo.name)[1]
            temp_filename = f"temp_logos/{uuid.uuid4()}{ext}"
            path = default_storage.save(temp_filename, ContentFile(logo.read()))
            absolute_path = os.path.join(settings.MEDIA_ROOT, path)
            
            request.session['temp_logo_path'] = absolute_path
            logo_url = default_storage.url(path)

        return JsonResponse({"status": "success", "logo_url": logo_url})
    return JsonResponse({"status": "error", "message": "Invalid request method."}, status=405)


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
    if poster_type == "posh" or poster_type == "posh_1":
        poster_filename = "POSH Poster.webp"
    elif poster_type == "posh_2":
        poster_filename = "POSH Poster 2.webp"
    elif poster_type.startswith("posh_") and poster_type[5:].isdigit() and 3 <= int(poster_type[5:]) <= 9:
        poster_filename = f"POSH Poster {poster_type[5:]}.webp"
    elif poster_type == "posh_company":
        poster_filename = "posh-company.webp"
    elif poster_type == "posh_pocso":
        poster_filename = "posh-pocso.webp"
    elif poster_type == "pocso":
        poster_filename = "POCSO Poster.webp"
    else:
        return HttpResponse("Invalid poster type", status=400)

    poster_key = f"/media/Posters/{poster_filename}"

    poster_path = os.path.join(settings.MEDIA_ROOT, "Posters", poster_filename)

    if not os.path.exists(poster_path):
        return HttpResponse("Base poster not found", status=404)

    try:
        # Open the base poster
        poster_img = Image.open(poster_path).convert("RGBA")
        p_width, p_height = poster_img.size

        # Fetch poster-specific config or fallback to org defaults
        from .models import PosterLogoConfig

        config = PosterLogoConfig.objects.filter(
            organization=org, poster_path=poster_key
        ).first()

        # Determine which logo to use: poster-specific or global org logo
        active_logo = None
        if config and config.logo:
            active_logo = config.logo
        elif org.logo:
            active_logo = org.logo

        if active_logo:
            logo_path = active_logo.path
            if os.path.exists(logo_path):
                logo_img = Image.open(logo_path).convert("RGBA")

                if config:
                    lw_pct = config.logo_width if config.logo_width > 0 else 15.0
                    lx = config.logo_x
                    ly = config.logo_y
                else:
                    lw_pct = org.logo_width if org.logo_width > 0 else 15.0
                    lx = org.logo_x
                    ly = org.logo_y

                # Scale based on lw_pct (percentage of poster width)
                target_width = int(p_width * (lw_pct / 100.0))
                w_percent = target_width / float(logo_img.size[0])
                target_height = int((float(logo_img.size[1]) * float(w_percent)))
                logo_img = logo_img.resize((target_width, target_height), Image.LANCZOS)

                # Positioning based on lx, ly (percentages)
                pos_x = int(p_width * (lx / 100.0))
                pos_y = int(p_height * (ly / 100.0))

                # Paste the logo directly onto the poster (using itself as mask for transparency)
                poster_img.paste(logo_img, (pos_x, pos_y), logo_img)

        # Draw Company Name and Address on the poster
        if config and (config.company_name or config.company_address):
            from PIL import ImageDraw, ImageFont
            font_path = os.path.join(settings.BASE_DIR, 'static', 'fonts', 'Nunito.ttf')
            
            if os.path.exists(font_path):
                draw = ImageDraw.Draw(poster_img)
                tx = config.text_x
                ty = config.text_y
                ts = config.text_size
                
                # Base font size calculated as percentage of poster width
                font_size_base = p_width * (ts / 100.0)
                font_size = max(12, int(font_size_base * 1.25))
                font_size_reg = max(10, int(font_size_base * 0.9))
                
                try:
                    font_bold = ImageFont.truetype(font_path, font_size)
                    font_reg = ImageFont.truetype(font_path, font_size_reg)
                except Exception as font_err:
                    _logger = logging.getLogger(__name__)
                    _logger.error(f"Error loading font: {str(font_err)}")
                    font_bold = ImageFont.load_default()
                    font_reg = ImageFont.load_default()
                
                pos_x = int(p_width * (tx / 100.0))
                pos_y = int(p_height * (ty / 100.0))
                
                # Parse text color (hex to RGBA)
                text_color_hex = getattr(config, "text_color", "#000000") or "#000000"
                try:
                    text_color_hex = text_color_hex.lstrip("#")
                    r_col = int(text_color_hex[0:2], 16)
                    g_col = int(text_color_hex[2:4], 16)
                    b_col = int(text_color_hex[4:6], 16)
                    text_color_rgb = (r_col, g_col, b_col, 255)
                except Exception:
                    r_col, g_col, b_col = 0, 0, 0
                    text_color_rgb = (0, 0, 0, 255)

                # Determine optimal shadow/border color based on text color brightness (luminance)
                luminance = 0.299 * r_col + 0.587 * g_col + 0.114 * b_col
                if luminance > 127:
                    shadow_color = (0, 0, 0, 220)  # Dark shadow for light text
                else:
                    shadow_color = (255, 255, 255, 220)  # Light shadow for dark text
                
                # Calculate widths to support perfect center-alignment
                name_w, name_h = 0, 0
                if config.company_name:
                    try:
                        name_w, name_h = font_bold.getsize(config.company_name)
                    except AttributeError:
                        left, top, right, bottom = font_bold.getbbox(config.company_name)
                        name_w = right - left
                        name_h = bottom - top

                addr_w, addr_h = 0, 0
                spacing_val = 0
                if config.company_address:
                    spacing_val = max(1, int(font_size_reg * 0.08))
                    for char in config.company_address:
                        try:
                            cw, ch = font_reg.getsize(char)
                        except AttributeError:
                            left, top, right, bottom = font_reg.getbbox(char)
                            cw = right - left
                            ch = bottom - top
                        addr_w += cw
                        addr_h = max(addr_h, ch)
                    addr_w += (len(config.company_address) - 1) * spacing_val

                max_w = max(name_w, addr_w)
                
                # Draw text with thin contrast borders/shadow for absolute legibility
                def draw_text_with_shadow(draw, position, text, font, fill, stroke_w=0, shadow_color=shadow_color, spacing=0):
                    x, y = position
                    if spacing > 0:
                        # Helper to draw spaced text
                        def draw_spaced(draw, pos, txt, f, fl, sw=0, sf=None):
                            sx, sy = pos
                            for char in txt:
                                draw.text((sx, sy), char, font=f, fill=fl, stroke_width=sw, stroke_fill=sf)
                                try:
                                    cw, _ = f.getsize(char)
                                except AttributeError:
                                    left, top, right, bottom = f.getbbox(char)
                                    cw = right - left
                                sx += cw + spacing
                        
                        if stroke_w > 0:
                            draw_spaced(draw, (x, y), text, font, shadow_color, sw=stroke_w + 1, sf=shadow_color)
                            draw_spaced(draw, (x, y), text, font, fill, sw=stroke_w, sf=fill)
                        else:
                            draw_spaced(draw, (x + 1, y + 1), text, font, shadow_color)
                            draw_spaced(draw, (x - 1, y + 1), text, font, shadow_color)
                            draw_spaced(draw, (x + 1, y - 1), text, font, shadow_color)
                            draw_spaced(draw, (x - 1, y - 1), text, font, shadow_color)
                            draw_spaced(draw, (x, y), text, font, fill)
                    else:
                        if stroke_w > 0:
                            # Draw shadow with thick stroke first
                            draw.text((x, y), text, font=font, fill=shadow_color, stroke_width=stroke_w + 1, stroke_fill=shadow_color)
                            # Draw main text with stroke on top
                            draw.text((x, y), text, font=font, fill=fill, stroke_width=stroke_w, stroke_fill=fill)
                        else:
                            draw.text((x + 1, y + 1), text, font=font, fill=shadow_color)
                            draw.text((x - 1, y + 1), text, font=font, fill=shadow_color)
                            draw.text((x + 1, y - 1), text, font=font, fill=shadow_color)
                            draw.text((x - 1, y - 1), text, font=font, fill=shadow_color)
                            draw.text((x, y), text, font=font, fill=fill)

                if config.company_name:
                    # Center align relative to the widest element
                    pos_x_name = pos_x + int((max_w - name_w) / 2)
                    stroke_w_name = max(1, int(font_size * 0.06))
                    draw_text_with_shadow(draw, (pos_x_name, pos_y), config.company_name, font=font_bold, fill=text_color_rgb, stroke_w=stroke_w_name)
                    pos_y += font_size + int(font_size * 0.25)
                
                if config.company_address:
                    # Center align relative to the widest element
                    pos_x_addr = pos_x + int((max_w - addr_w) / 2)
                    stroke_w_addr = max(1, int(font_size_reg * 0.04))
                    draw_text_with_shadow(draw, (pos_x_addr, pos_y), config.company_address, font=font_reg, fill=text_color_rgb, stroke_w=stroke_w_addr, spacing=spacing_val)
            else:
                _logger = logging.getLogger(__name__)
                _logger.warning(f"Font file not found at: {font_path}")

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
        _logger = logging.getLogger(__name__)
        _logger.error(f"Error generating poster: {str(e)}")
        return HttpResponse(f"Error generating poster: {str(e)}", status=500)


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
            poster_path = data.get("poster_path")

            if poster_path:
                # Save poster-specific config
                config, created = PosterLogoConfig.objects.get_or_create(
                    organization=org, poster_path=poster_path
                )
                config.logo_x = float(data.get("x", 2.0))
                config.logo_y = float(data.get("y", 2.0))
                config.logo_width = float(data.get("width", 15.0))
                config.company_name = data.get("company_name", "")
                config.company_address = data.get("company_address", "")
                config.text_x = float(data.get("text_x", 3.0))
                config.text_y = float(data.get("text_y", 88.0))
                config.text_size = float(data.get("text_size", 2.2))
                config.text_color = data.get("text_color", "#000000")
                config.save()
            else:
                # Fallback to general org settings if no path provided
                org.logo_x = float(data.get("x", 2.0))
                org.logo_y = float(data.get("y", 2.0))
                org.logo_width = float(data.get("width", 15.0))
                org.save()

            return JsonResponse({"status": "success"})
        except Exception as e:
            # FIX #9: Log internally, return generic message to client
            _logger = logging.getLogger(__name__)
            _logger.exception(f"save_logo_config error for user={request.user.id}: {e}")
            return JsonResponse({"status": "error", "message": "An error occurred saving the configuration."}, status=500)
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
    
    poster_path = request.GET.get("poster_path")
    if poster_path:
        from .models import PosterLogoConfig
        PosterLogoConfig.objects.filter(
            organization=org, poster_path=poster_path
        ).delete()
    else:
        org.logo_x = 2.0
        org.logo_y = 2.0
        org.logo_width = 15.0
        org.save()
        
    return redirect("/dashboard/company/?section=posters")


def validate_image_file(uploaded_file, max_size=5*1024*1024):
    if uploaded_file.size > max_size:
        return False, f"File size exceeds {max_size // (1024 * 1024)}MB limit."
    
    # Verify content type starts with image/
    if not uploaded_file.content_type or not uploaded_file.content_type.startswith("image/"):
        return False, "Invalid file type. Only images are allowed."
        
    try:
        from PIL import Image
        # Open and verify the image
        img = Image.open(uploaded_file)
        img.verify()
        # Verify the format is valid
        if img.format not in ["JPEG", "PNG", "GIF", "WEBP", "BMP"]:
            return False, f"Unsupported image format: {img.format}"
        uploaded_file.seek(0)
    except Exception:
        return False, "Invalid image file. The file is corrupted or not a valid image."
        
    return True, ""

def validate_csv_file(uploaded_file, max_size=5*1024*1024):
    if uploaded_file.size > max_size:
        return False, f"File size exceeds {max_size // (1024 * 1024)}MB limit."
    
    # Check mime type (allow text/csv, text/plain, etc.)
    allowed_mimes = ["text/csv", "text/plain", "application/csv", "application/vnd.ms-excel"]
    if not uploaded_file.content_type or uploaded_file.content_type not in allowed_mimes:
        return False, "Invalid file type. Only CSV files are allowed."
        
    # Read the beginning of the file to check if it's text and does not contain null bytes (binary)
    try:
        chunk = uploaded_file.read(1024)
        uploaded_file.seek(0) # Reset stream
        if b'\x00' in chunk:
            return False, "Invalid file content. Binary files are not allowed."
        # Try to decode it as text
        chunk.decode("utf-8-sig")
    except Exception:
        return False, "Invalid file content. Only UTF-8 encoded text CSV files are allowed."
        
    return True, ""


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


# FIX #4: Generic per-user/IP rate limiter using Django's cache framework
def check_rate_limit(key, limit=30, window=60):
    """Returns True if rate limit exceeded. key should be a unique identifier (e.g. user id)."""
    from django.core.cache import cache
    import time
    cache_key = f"rl_{key}"
    data = cache.get(cache_key, {"count": 0, "reset_at": time.time() + window})
    if time.time() > data["reset_at"]:
        data = {"count": 1, "reset_at": time.time() + window}
    else:
        data["count"] += 1
    cache.set(cache_key, data, timeout=window)
    return data["count"] > limit


def check_login_lockout(username, ip):
    from django.core.cache import cache
    import time
    
    lockout_key = f"login_lockout_{username}_{ip}"
    lockout_expiry = cache.get(lockout_key)
    if lockout_expiry:
        remaining = int(lockout_expiry - time.time())
        if remaining > 0:
            return True, remaining
    return False, 0

def increment_login_attempts(username, ip):
    from django.core.cache import cache
    import time
    
    attempts_key = f"login_attempts_{username}_{ip}"
    lockout_key = f"login_lockout_{username}_{ip}"
    
    attempts = cache.get(attempts_key, 0) + 1
    cache.set(attempts_key, attempts, timeout=900) # 15 mins window
    
    if attempts >= 5:
        cache.set(lockout_key, time.time() + 900, timeout=900) # Lock for 15 mins
        cache.delete(attempts_key)

def clear_login_attempts(username, ip):
    from django.core.cache import cache
    attempts_key = f"login_attempts_{username}_{ip}"
    lockout_key = f"login_lockout_{username}_{ip}"
    cache.delete(attempts_key)
    cache.delete(lockout_key)


# --- 0. CUSTOM LOGIN VIEW ---
def custom_login_view(request):
    from django.contrib.auth import authenticate, get_user_model, login
    from django.db.models import Q

    from .models import Organization

    if request.method == "POST":
        u = request.POST.get("username", "").strip()
        p = request.POST.get("password")
        ip = get_client_ip(request)

        is_locked, remaining = check_login_lockout(u, ip)
        if is_locked:
            minutes = (remaining + 59) // 60
            error_msg = f"Too many failed login attempts. Locked for {minutes} minute(s)."
            return render(request, "login.html", {"error_message": error_msg})

        # Try standard authentication first
        user = authenticate(username=u, password=p)
        if user is not None:
            clear_login_attempts(u, ip)
            login(request, user)
            if "hr_as_employee" in request.session:
                del request.session["hr_as_employee"]
            return redirect("custom_login_redirect")

        # Fallback error
        increment_login_attempts(u, ip)
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
        if user.force_password_change:
            return redirect("force_password_change")

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

        from django.urls import reverse
        return redirect(reverse("company_dashboard") + "?login=true")

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



# --- CUSTOM CAPTCHA VIEWS ---
def generate_captcha_image(request):
    """Generate a random alphanumeric + symbols CAPTCHA image using Pillow."""
    import secrets
    import string
    import io
    from PIL import Image, ImageDraw, ImageFont
    from django.http import HttpResponse

    sys_random = secrets.SystemRandom()

    # Generate a random 6-character code containing alphanumeric characters and select symbols
    symbols = "!@#$*?"
    chars = string.ascii_letters + string.digits + symbols
    captcha_text = "".join(sys_random.choice(chars) for _ in range(6))
    
    # Save the expected code in session
    request.session["captcha_text"] = captcha_text
    request.session.modified = True
    
    # Create the captcha image
    width, height = 180, 50
    image = Image.new("RGB", (width, height), color=(248, 250, 252)) # Light slate/gray background
    draw = ImageDraw.Draw(image)
    
    # Try to load a standard system font, fallback to default
    try:
        font_paths = [
            "arial.ttf", "calibri.ttf", "LiberationSans-Regular.ttf", "DejaVuSans.ttf"
        ]
        font = None
        for fp in font_paths:
            try:
                font = ImageFont.truetype(fp, 28)
                break
            except IOError:
                continue
        if not font:
            font = ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
        
    # Draw noise lines
    for _ in range(8):
        x1 = sys_random.randint(0, width)
        y1 = sys_random.randint(0, height)
        x2 = sys_random.randint(0, width)
        y2 = sys_random.randint(0, height)
        line_color = (sys_random.randint(150, 220), sys_random.randint(150, 220), sys_random.randint(150, 220))
        draw.line((x1, y1, x2, y2), fill=line_color, width=2)
        
    # Draw noise dots
    for _ in range(100):
        x = sys_random.randint(0, width)
        y = sys_random.randint(0, height)
        dot_color = (sys_random.randint(100, 200), sys_random.randint(100, 200), sys_random.randint(100, 200))
        draw.point((x, y), fill=dot_color)
        
    # Draw each character with random rotation/offset/color
    char_width = width / 7
    for i, char in enumerate(captcha_text):
        char_color = (sys_random.randint(15, 90), sys_random.randint(15, 90), sys_random.randint(15, 90))
        x_pos = 10 + i * char_width + sys_random.randint(-4, 4)
        y_pos = 10 + sys_random.randint(-5, 5)
        draw.text((x_pos, y_pos), char, fill=char_color, font=font)
        
    # Return as PNG HttpResponse
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    
    return HttpResponse(buf.read(), content_type="image/png")


def verify_captcha_view(request):
    """Verify the submitted CAPTCHA value against session dynamically."""
    if request.method == "POST":
        import json
        try:
            data = json.loads(request.body)
            code = data.get("captcha", "").strip()
        except Exception:
            code = request.POST.get("captcha", "").strip()

        session_code = request.session.get("captcha_text", "")
        # FIX #12: Case-sensitive comparison (preserves the security of mixed-case CAPTCHA)
        if session_code and code == session_code:
            return JsonResponse({"success": True})

        # FIX #12: Regenerate CAPTCHA on every failed attempt to prevent reuse
        import secrets, string
        sys_random = secrets.SystemRandom()
        symbols = "!@#$*?"
        chars = string.ascii_letters + string.digits + symbols
        new_captcha = "".join(sys_random.choice(chars) for _ in range(6))
        request.session["captcha_text"] = new_captcha
        request.session.modified = True

        return JsonResponse({"success": False, "error": "Incorrect CAPTCHA code. Please try again."})
    return JsonResponse({"success": False, "error": "Invalid request method."}, status=405)


# --- 2. COMPANY SUBSCRIPTION (FORM) ---
def company_subscription(request, plan_type):
    db_type = "POSH" if "POSH" in plan_type else "POCSO"
    plan = SubscriptionPlan.objects.filter(type=db_type).first()

    if request.method == "POST":
        comp_name = request.POST.get("company_name", "").strip()
        seats = request.POST.get("seats", 10)
        fullname = request.POST.get("fullname", "").strip()
        password = request.POST.get("password", "").strip()
        setup_token = request.POST.get("setup_token", "").strip()

        if not setup_token:
            messages.error(
                request, "Access denied. A valid setup link is required to create a corporate account."
            )
            return redirect("registration_selection")

        try:
            from django.core import signing

            payload = signing.loads(
                setup_token, salt="posh-admin-setup", max_age=60 * 60 * 72
            )  # 72h
            email = payload["email"]
            # Auto-populate company name from the POSH or POCSO registration
            logger = logging.getLogger(__name__)
            if not comp_name:
                try:
                    posh_reg = POSHRegistration.objects.get(id=payload["reg_id"])
                    comp_name = posh_reg.company_name
                    seats = posh_reg.employee_count or seats
                except POSHRegistration.DoesNotExist:
                    try:
                        pocso_reg = POCSORegistration.objects.get(id=payload["reg_id"])
                        comp_name = pocso_reg.company_name
                        seats = pocso_reg.employee_count or seats
                    except POCSORegistration.DoesNotExist:
                        logger.warning(
                            f"POSHRegistration or POCSORegistration not found for reg_id={payload.get('reg_id')}"
                        )
                except Exception as e:
                    logger.exception(
                        f"Unexpected error while fetching registration: {e}"
                    )
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.exception(f"Invalid setup link payload: {e}")
            messages.error(
                request, "Invalid or expired setup link. Please contact support."
            )
            return redirect(request.path)

        if not comp_name:
            comp_name = f"{fullname}'s Organization"

        # Restriction: Ensure all info is compulsory
        if not all([fullname, email, password]):
            messages.error(
                request, "All fields are compulsory. Please fill out the entire form."
            )
            return redirect(request.get_full_path())

        # Strict backend validation matching frontend regexes
        import re
        if not re.match(r"^[a-zA-Z\s]{3,50}$", fullname):
            messages.error(request, "Please enter a valid full name (letters and spaces only, 3-50 characters).")
            return redirect(request.get_full_path())

        if not re.match(r"^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$", password):
            messages.error(request, "Password must be at least 8 characters long, containing at least one letter, one number, and one special character (@$!%*?&).")
            return redirect(request.get_full_path())

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already registered.")
            return redirect(request.get_full_path())
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
            return redirect("/dashboard/company/?login=true")

        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.exception(f"Error during company subscription setup: {e}")
            messages.error(request, f"Error: {str(e)}")
            return redirect(request.get_full_path())

    # --- GET ---
    else:
        if request.user.is_authenticated:
            logout(request)
        list(messages.get_messages(request))

    setup_token = request.GET.get("setup_token", "").strip()
    if not setup_token:
        messages.error(
            request, "Access denied. A valid setup link is required to create a corporate account."
        )
        return redirect("registration_selection")

    locked_email = None
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
        return redirect("registration_selection")

    response = render(
        request,
        "company_admin_setup.html",
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
        emp_department = request.POST.get("emp_department", "").strip()

        posh_reg = POSHRegistration.objects.filter(email=org.owner.email).first()
        pocso_reg = POCSORegistration.objects.filter(email=org.owner.email).first()
        reg = posh_reg or pocso_reg
        seat_limit = reg.employee_count if reg else org.max_users

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
                new_user.department = emp_department or None
                new_user.force_password_change = (
                    True  # Force password change on first login
                )
                # Generate user_id by passing org directly (avoids querying unsaved relationships)
                new_user.user_id = new_user.generate_user_id(organization=org)
                new_user.save()

                OrganizationMember.objects.create(
                    organization=org, user=new_user, role="MEMBER"
                )

            # Send welcome email OUTSIDE transaction so email failure doesn't roll back user creation
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
            )

            messages.success(request, f"✅ {emp_name} added successfully! Login credentials sent to {emp_email}.")

        except Exception as e:
            _logger = logging.getLogger(__name__)
            _logger.exception(f"Error adding employee for org {org.id}: {e}")
            messages.error(request, "Failed to add employee. Please try again or contact support.")

        return redirect("company_dashboard")
    return redirect("company_dashboard")


# --- 3.5. UPDATE AND DELETE EMPLOYEE ---
@login_required(login_url="login")
def update_employee(request, member_id):
    if request.method != "POST":
        return redirect("company_dashboard")

    current_user = request.user
    admin_membership = OrganizationMember.objects.filter(
        user=current_user, role="ADMIN"
    ).first()
    if not admin_membership:
        messages.error(request, "Unauthorized.")
        return redirect("tutorial")

    org = admin_membership.organization

    # Fetch the target member
    try:
        member = OrganizationMember.objects.get(id=member_id, organization=org, role="MEMBER")
    except OrganizationMember.DoesNotExist:
        messages.error(request, "Employee not found in your organization.")
        return redirect("company_dashboard")

    user_obj = member.user

    # Enforce seat lock rule: check if they have completed training
    active_sub = Subscription.objects.filter(organization=org, status="ACTIVE").first()
    training_type = "POSH"
    if active_sub and active_sub.plan.type in ["POCSO", "BOTH"]:
        if active_sub.plan.type == "POCSO":
            training_type = "POCSO"

    # Fetch visible modules count
    all_modules = TrainingModule.objects.filter(module_type=training_type)
    visible_modules = [
        m for m in all_modules 
        if m.video_file or (m.ppt_file and not m.video_file and "quiz" in m.title.lower())
    ]
    visible_module_ids = [m.id for m in visible_modules]
    total_modules_count = len(visible_modules)

    is_completed = False
    if total_modules_count > 0:
        completed_modules = ModuleProgress.objects.filter(
            user=user_obj, module_id__in=visible_module_ids, is_completed=True
        ).count()
        is_completed = (completed_modules == total_modules_count)

    if is_completed:
        messages.error(request, "This employee has already completed the training. Their seat is locked and cannot be edited.")
        return redirect("company_dashboard")

    # Process the edit request
    emp_name = request.POST.get("emp_name", "").strip()
    emp_email = request.POST.get("emp_email", "").strip().lower()
    emp_department = request.POST.get("emp_department", "").strip()

    if not emp_name or not emp_email:
        messages.error(request, "Name and Email are required.")
        return redirect("company_dashboard")

    # Check if another user already has the new email
    if User.objects.filter(email=emp_email).exclude(id=user_obj.id).exists():
        messages.error(request, "A user with this email address already exists.")
        return redirect("company_dashboard")

    try:
        with transaction.atomic():
            email_changed = (user_obj.email.lower() != emp_email)
            user_obj.first_name = emp_name
            user_obj.department = emp_department or None

            if email_changed:
                user_obj.email = emp_email
                user_obj.username = emp_email

                # Reset password to company default password
                if not org.default_password:
                    org.default_password = org.generate_default_password()
                    org.save()

                user_obj.set_password(org.default_password)
                user_obj.force_password_change = True

            user_obj.save()

        if email_changed:
            # Send welcome email to the new email address with credentials
            from home.email_utils import send_welcome_email
            from django.conf import settings as django_settings

            site_base = getattr(
                django_settings, "SITE_URL", "https://openhandsolutions.com"
            )
            training_link = f"{site_base}/login/"

            posh_reg = POSHRegistration.objects.filter(email=org.owner.email).first()
            pocso_reg = POCSORegistration.objects.filter(email=org.owner.email).first()
            company_name = posh_reg.company_name if posh_reg else (pocso_reg.company_name if pocso_reg else org.name)

            try:
                send_welcome_email(
                    user_obj,
                    org.default_password,
                    is_company_employee=True,
                    organization_name=company_name,
                    training_link=training_link,
                )
                messages.success(request, f"Employee updated successfully. Login credentials sent to {emp_email}.")
            except Exception as email_err:
                _logger = logging.getLogger(__name__)
                _logger.error(f"Error sending email: {email_err}")
                messages.warning(request, f"Employee updated successfully, but failed to send notification email: {str(email_err)}")
        else:
            messages.success(request, "Employee updated successfully.")

    except Exception as e:
        _logger = logging.getLogger(__name__)
        _logger.exception(f"Error updating employee member_id={member_id}: {e}")
        messages.error(request, "Failed to update employee. Please try again or contact support.")

    return redirect("company_dashboard")


@login_required(login_url="login")
def delete_employee(request, member_id):
    if request.method != "POST":
        return redirect("company_dashboard")

    current_user = request.user
    admin_membership = OrganizationMember.objects.filter(
        user=current_user, role="ADMIN"
    ).first()
    if not admin_membership:
        messages.error(request, "Unauthorized.")
        return redirect("tutorial")

    org = admin_membership.organization

    # Fetch the target member
    try:
        member = OrganizationMember.objects.get(id=member_id, organization=org, role="MEMBER")
    except OrganizationMember.DoesNotExist:
        messages.error(request, "Employee not found in your organization.")
        return redirect("company_dashboard")

    user_obj = member.user

    # Enforce seat lock rule: check if they have completed training
    active_sub = Subscription.objects.filter(organization=org, status="ACTIVE").first()
    training_type = "POSH"
    if active_sub and active_sub.plan.type in ["POCSO", "BOTH"]:
        if active_sub.plan.type == "POCSO":
            training_type = "POCSO"

    # Fetch visible modules count
    all_modules = TrainingModule.objects.filter(module_type=training_type)
    visible_modules = [
        m for m in all_modules 
        if m.video_file or (m.ppt_file and not m.video_file and "quiz" in m.title.lower())
    ]
    visible_module_ids = [m.id for m in visible_modules]
    total_modules_count = len(visible_modules)

    is_completed = False
    if total_modules_count > 0:
        completed_modules = ModuleProgress.objects.filter(
            user=user_obj, module_id__in=visible_module_ids, is_completed=True
        ).count()
        is_completed = (completed_modules == total_modules_count)

    if is_completed:
        messages.error(request, "This employee has already completed the training. Their seat is locked and cannot be deleted.")
        return redirect("company_dashboard")

    try:
        emp_name = user_obj.get_full_name() or user_obj.first_name
        # Delete the User model, cascading will delete the member, progress, etc.
        user_obj.delete()
        messages.success(request, f"Employee {emp_name} has been deleted successfully.")
    except Exception as e:
        _logger = logging.getLogger(__name__)
        _logger.exception(f"Error deleting employee member_id={member_id}: {e}")
        messages.error(request, "Failed to delete employee. Please try again or contact support.")

    return redirect("company_dashboard")


# --- 4. COMPANY DASHBOARD ---
@login_required(login_url="login")
def company_dashboard(request):
    _logger = logging.getLogger(__name__)
    _logger.debug("COMPANY DASHBOARD VIEW IS CALLED")
    # Check if user logged out from HR portal
    if request.session.get("logged_out_of_hr"):
        request.session.pop("logged_out_of_hr", None)

    user = request.user
    if user.force_password_change:
        return redirect("force_password_change")

    membership = OrganizationMember.objects.filter(user=user, role="ADMIN").first()

    if not membership:
        messages.error(request, "Access Denied. Admin only.")
        return redirect("tutorial")

    org = membership.organization
    active_sub = Subscription.objects.filter(organization=org, status="ACTIVE").first()
    members = list(OrganizationMember.objects.filter(
        organization=org, role="MEMBER"
    ).select_related("user"))

    # --- DATA CALCULATION FOR HTML ---
    total_employees = len(members)

    # Identify Training Type based on Plan
    training_type = "POSH"  # Default
    if active_sub and active_sub.plan.type in ["POCSO", "BOTH"]:
        if active_sub.plan.type == "POCSO":
            training_type = "POCSO"

    # Fetch total modules for calculation
    all_modules = TrainingModule.objects.filter(module_type=training_type).order_by(
        "order"
    )
    # Filter to only include modules visible to employees (consistent with corp_act_page logic)
    visible_modules = [
        m for m in all_modules 
        if m.video_file or (m.ppt_file and not m.video_file and "quiz" in m.title.lower())
    ]
    visible_module_ids = [m.id for m in visible_modules]
    total_modules_count = len(visible_modules)

    training_completed_count = 0

    # Annotate members with progress
    for mem in members:
        user_obj = mem.user

        # Get progress for this user (only for visible modules)
        completed_modules = ModuleProgress.objects.filter(
            user=user_obj, module_id__in=visible_module_ids, is_completed=True
        ).count()

        total_progress = 0.0
        user_progress_map = set(
            ModuleProgress.objects.filter(
                user=user_obj, module__module_type=training_type, is_completed=True
            ).values_list("module_id", flat=True)
        )
        for m in visible_modules:
            if m.id in user_progress_map:
                total_progress += 100.0
            elif m.video_file:  # Only video modules have partial progress
                prog = ModuleProgress.objects.filter(user=user_obj, module=m).first()
                if prog and m.duration_seconds > 0:
                    percent_watched = (prog.last_position / m.duration_seconds) * 100.0
                    percent_watched = min(99.0, max(0.0, percent_watched))
                    total_progress += percent_watched

        mem.percent_complete = (
            int(total_progress / total_modules_count)
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

        completed_ppt_count = sum(1 for m in ppt_mods if m.id in user_progress_map)

        total_vid_progress = 0.0
        for m in vid_mods:
            if m.id in user_progress_map:
                total_vid_progress += 100.0
            else:
                prog = ModuleProgress.objects.filter(user=user_obj, module=m).first()
                if prog and m.duration_seconds > 0:
                    percent_watched = (prog.last_position / m.duration_seconds) * 100.0
                    percent_watched = min(99.0, max(0.0, percent_watched))
                    total_vid_progress += percent_watched
                else:
                    total_vid_progress += 0.0

        mem.video_percent = (
            int(total_vid_progress / total_vid_count)
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

        # Fallback/addition based on actual video progress
        video_progress_seconds = 0
        for m in all_modules:
            if m.video_file:  # Only count video modules for watch time
                if m.id in user_progress_map:
                    video_progress_seconds += m.duration_seconds
                else:
                    prog = ModuleProgress.objects.filter(user=user_obj, module=m).first()
                    if prog:
                        video_progress_seconds += int(prog.last_position)

        grand_total_seconds = max(grand_total_seconds, video_progress_seconds)
        hours = grand_total_seconds // 3600
        minutes = (grand_total_seconds % 3600) // 60
        mem.total_active_time = f"{hours}h {minutes}m"
        mem.employee_id = user_obj.user_id if user_obj else None

        # Check if user has started training
        has_started = False
        if grand_total_seconds > 0:
            has_started = True
        else:
            has_started = ModuleProgress.objects.filter(
                user=user_obj,
                module_id__in=visible_module_ids
            ).filter(
                Q(is_completed=True) | Q(last_position__gt=0.0)
            ).exists()

        if mem.is_training_completed:
            mem.training_status = "completed"
        elif has_started:
            mem.training_status = "in_progress"
        else:
            mem.training_status = "not_started"
        # Check if employee has passed the final quiz (for certificate eligibility)
        if training_type == "POSH":
            # For POSH corporate employees, coursework (video + interactive quiz) complete is certificate eligible.
            quiz_module = next((m for m in all_modules if "quiz" in m.title.lower() and m.ppt_file and not m.video_file), None)
            quiz_completed = False
            if quiz_module:
                quiz_prog = ModuleProgress.objects.filter(user=user_obj, module=quiz_module).first()
                quiz_completed = quiz_prog.is_completed if quiz_prog else False
            has_passed_quiz = quiz_completed
        else:
            # For POCSO and other training types, check the standard AssessmentProgress
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

    posh_reg = POSHRegistration.objects.filter(email=org.owner.email).first()
    pocso_reg = POCSORegistration.objects.filter(email=org.owner.email).first()
    reg = posh_reg or pocso_reg
    posh_company_name = reg.company_name if reg else org.name

    # If org name is still the auto-generated fallback, update it + regenerate password
    if reg and (
        org.name == f"{org.owner.first_name}'s Organization" or not org.name
    ):
        org.name = reg.company_name
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

    poster_configs = {
        "posh_1": PosterLogoConfig.objects.filter(organization=org, poster_path="/media/Posters/POSH Poster.webp").first(),
        "posh_2": PosterLogoConfig.objects.filter(organization=org, poster_path="/media/Posters/POSH Poster 2.webp").first(),
        "posh_company": PosterLogoConfig.objects.filter(organization=org, poster_path="/media/Posters/posh-company.webp").first(),
        "posh_pocso": PosterLogoConfig.objects.filter(organization=org, poster_path="/media/Posters/posh-pocso.webp").first(),
        "pocso": PosterLogoConfig.objects.filter(organization=org, poster_path="/media/Posters/POCSO Poster.webp").first(),
    }
    for i in range(3, 10):
        poster_configs[f"posh_{i}"] = PosterLogoConfig.objects.filter(
            organization=org, poster_path=f"/media/Posters/POSH Poster {i}.webp"
        ).first()

    raw_posters = [
        ("posh_1", "/media/Posters/POSH Poster.webp", "POSH Act Guidelines"),
        ("posh_2", "/media/Posters/POSH Poster 2.webp", "Spot It – Stop It"),
        ("posh_3", "/media/Posters/POSH Poster 3.webp", "Respectful Workplace"),
        ("posh_4", "/media/Posters/POSH Poster 4.webp", "Zero Tolerance Policy"),
        ("posh_6", "/media/Posters/POSH Poster 6.webp", "Compliance & Care"),
        ("posh_7", "/media/Posters/POSH Poster 7.webp", "Types of Harassment (Hindi)"),
        ("posh_8", "/media/Posters/POSH Poster 8.webp", "Respect is Non-Negotiable"),
        ("posh_9", "/media/Posters/POSH Poster 9.webp", "Culture & Safety"),
        ("posh_pocso", "/media/Posters/posh-pocso.webp", "Combined POSH & POCSO"),
        ("posh_5", "/media/Posters/POSH Poster 5.webp", "Equality vs Equity"),
        ("posh_company", "/media/Posters/posh-company.webp", "POSH Corporate Guidelines"),
    ]
    from home.models import DeletedPoster
    deleted_paths = list(DeletedPoster.objects.values_list('poster_path', flat=True))

    posters_list = []
    for key, path, title in raw_posters:
        if path in deleted_paths:
            continue
        config = poster_configs.get(key)
        posters_list.append({
            "key": key,
            "path": path,
            "title": title,
            "logo_x": config.logo_x if config else org.logo_x,
            "logo_y": config.logo_y if config else org.logo_y,
            "logo_width": config.logo_width if config else org.logo_width,
            "logo_url": config.logo.url if (config and config.logo) else (org.logo.url if org.logo else None),
            "company_name": config.company_name if config else "",
            "company_address": config.company_address if config else "",
            "text_x": config.text_x if config else 3.0,
            "text_y": config.text_y if config else 88.0,
            "text_size": config.text_size if config else 2.2,
            "text_color": config.text_color if config else "#000000",
        })

    posh_policy = POSHPolicy.objects.filter(organization=org).first()
    show_policy_form = (training_type == "POSH" and posh_policy is None)

    context = {
        "organization": org,
        "poster_configs": poster_configs,
        "posters_list": posters_list,
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
        "posh_policy": posh_policy,
        "show_policy_form": show_policy_form,
        "has_organization": True,
        "org_logo_url": org.logo.url if org.logo else None,
        "deleted_posters": deleted_paths,
    }


    # --- LOGIC TO SWITCH TEMPLATES BASED ON PLAN ---
    if active_sub and active_sub.plan.type == "POCSO":
        return render(request, "pocso/pocso_company_dashboard.html", context)
    else:
        # Default to POSH dashboard
        return render(request, "posh/posh_company_dashboard.html", context)


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
            
            # Enforce security threshold cap (max 15 seconds per request)
            if seconds_delta > 15:
                seconds_delta = 15
            elif seconds_delta < 0:
                seconds_delta = 0

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


@login_required
def mod_complete(request, module_id):
    """
    API called when a video ends. Marks module as complete.
    Security: Verifies the module belongs to the user's active subscription type.
    """
    _logger = logging.getLogger(__name__)
    _logger.debug(f"mod_complete called: method={request.method}, module_id={module_id}, user={request.user.id}")
    if request.method == "POST":
        try:
            # --- FIX #4: Module ownership verification ---
            # Determine the training type the user is subscribed to
            active_sub = Subscription.objects.filter(
                Q(user=request.user) | Q(organization__organizationmember__user=request.user),
                status="ACTIVE",
            ).first()
            allowed_types = []
            if active_sub:
                if active_sub.plan.type in ["POSH", "BOTH"]:
                    allowed_types.append("POSH")
                if active_sub.plan.type in ["POCSO", "BOTH"]:
                    allowed_types.append("POCSO")
            else:
                # Fallback: allow any module if no active sub found (edge case)
                allowed_types = ["POSH", "POCSO"]

            try:
                module = TrainingModule.objects.get(id=module_id, module_type__in=allowed_types)
            except TrainingModule.DoesNotExist:
                _logger.warning(f"mod_complete denied: module {module_id} not in allowed types {allowed_types} for user {request.user.id}")
                return JsonResponse(
                    {"status": "error", "message": "Module not found"}, status=404
                )

            _logger.debug(f"mod_complete: Found module: {module.title} (type={module.module_type})")
            prog, created = ModuleProgress.objects.get_or_create(
                user=request.user, module=module
            )
            prog.is_completed = True
            prog.save()
            _logger.debug(f"mod_complete: Saved is_completed=True for user={request.user.id}, module={module_id}")
            return JsonResponse({"status": "success", "module_id": module_id})
        except Exception as e:
            _logger.exception(f"mod_complete unexpected error for user={request.user.id}, module={module_id}: {e}")
            return JsonResponse({"status": "error", "message": "An unexpected error occurred."}, status=500)
    return JsonResponse({"status": "error"}, status=400)


@login_required
def save_video_progress(request):
    _logger = logging.getLogger(__name__)
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            module_id = data.get("module_id")
            position = float(data.get("position", 0.0))
            if module_id:
                # FIX #5 (BOLA): Verify the module belongs to a course the user has access to
                user = request.user
                active_subs = Subscription.objects.filter(
                    Q(user=user) | Q(organization__organizationmember__user=user),
                    status="ACTIVE",
                )
                allowed_types = set()
                for sub in active_subs:
                    t = sub.plan.type
                    if t == "BOTH":
                        allowed_types |= {"POSH", "POCSO"}
                    elif t in ("POSH", "POCSO"):
                        allowed_types.add(t)

                module = TrainingModule.objects.filter(
                    id=module_id, module_type__in=allowed_types
                ).first()
                if not module:
                    return JsonResponse(
                        {"status": "error", "message": "Module not accessible."}, status=403
                    )

                progress, created = ModuleProgress.objects.get_or_create(
                    user=user, module=module
                )
                progress.last_position = position
                progress.save()
                return JsonResponse({"status": "success"})
        except Exception as e:
            # FIX #9: Log internally, return generic message to client
            _logger.exception(f"save_video_progress error for user={request.user.id}: {e}")
            return JsonResponse({"status": "error", "message": "An error occurred saving progress."}, status=500)
    return JsonResponse({"status": "error"}, status=400)


@login_required
def reset_progress(request):
    """
    Resets all module progress for the given course type (POSH/POCSO).
    Called when a user fails an intermediate quiz.
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            course_type = data.get("type", "POSH")
            ModuleProgress.objects.filter(
                user=request.user, 
                module__module_type=course_type
            ).delete()
            return JsonResponse({"status": "success"})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=500)
    return JsonResponse({"status": "error", "message": "Invalid method"}, status=400)


@login_required
def get_assessment_questions(request):
    """
    Return the list of questions and options (without correct answers) 
    for the requested assessment type.
    """
    assessment_type = request.GET.get("type", "POSH").upper()  # POSH, POCSO, or POCSO_CORP
    if assessment_type not in ["POSH", "POCSO", "POCSO_CORP"]:
        return JsonResponse({"status": "error", "message": "Invalid assessment type"}, status=400)
    
    try:
        json_path = os.path.join(settings.BASE_DIR, "home", "quiz_questions.json")
        with open(json_path, "r", encoding="utf-8") as f:
            all_data = json.load(f)
        
        questions_pool = all_data.get(assessment_type, [])
        # Strip out correct answer index 'c' for security
        safe_questions = []
        for q in questions_pool:
            if assessment_type == "POCSO_CORP":
                safe_questions.append({
                    "question": q["q"],
                    "options": q["a"]
                })
            else:
                safe_questions.append({
                    "q": q["q"],
                    "a": q["a"]
                })
            
        return JsonResponse({"status": "success", "questions": safe_questions})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@login_required
def submit_assessment(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            assessment_type = data.get("type", "POSH").upper()  # POSH, POCSO, or POCSO_CORP
            submitted_answers = data.get("answers", [])
            
            if not isinstance(submitted_answers, list) or not submitted_answers:
                return JsonResponse({"status": "error", "message": "No answers submitted"}, status=400)
            
            if assessment_type not in ["POSH", "POCSO", "POCSO_CORP"]:
                return JsonResponse({"status": "error", "message": "Invalid assessment type"}, status=400)
            
            # Load correct answers
            json_path = os.path.join(settings.BASE_DIR, "home", "quiz_questions.json")
            with open(json_path, "r", encoding="utf-8") as f:
                all_data = json.load(f)
            questions_pool = all_data.get(assessment_type, [])
            
            # Create a lookup map of questions to correct answers
            correct_answers_map = {q["q"].strip().lower(): q["c"] for q in questions_pool}
            
            # Grade
            score_raw = 0
            results = []
            for ans_obj in submitted_answers:
                # Support both key formats: 'q' and 'question'
                q_text = ans_obj.get("q") or ans_obj.get("question")
                # Support both answer index keys: 'ans' or 'answer' or 'userAnswer'
                user_ans = ans_obj.get("ans")
                if user_ans is None:
                    user_ans = ans_obj.get("answer")
                if user_ans is None:
                    user_ans = ans_obj.get("userAnswer")
                
                if q_text and user_ans is not None:
                    q_clean = q_text.strip().lower()
                    is_correct = False
                    correct_idx = None
                    if q_clean in correct_answers_map:
                        correct_idx = correct_answers_map[q_clean]
                        is_correct = correct_idx == int(user_ans)
                        if is_correct:
                            score_raw += 1
                    results.append({
                        "q": q_text,
                        "is_correct": is_correct,
                        "correct_index": correct_idx
                    })
            
            # Use the actual pool size from database/config pool as the total count
            total_q = len(questions_pool)
            if total_q == 0:
                return JsonResponse({"status": "error", "message": "Quiz pool is empty"}, status=500)
            
            # The database field uses type 'POCSO' for corporate training too
            db_type = "POCSO" if assessment_type in ["POCSO", "POCSO_CORP"] else assessment_type
 
            percentage = round((score_raw / total_q) * 100) if total_q > 0 else 0
            
            is_employee = OrganizationMember.objects.filter(
                user=request.user, role="MEMBER"
            ).exists()
            if is_employee:
                passed = percentage >= 80
            else:
                passed = percentage == 100
 
            progress, created = AssessmentProgress.objects.get_or_create(
                user=request.user, assessment_type=db_type
            )
            # Only update score if this attempt is better (or first attempt)
            if created or percentage > progress.score or passed:
                progress.score = percentage  # Store percentage as score for HR dashboard
                progress.is_passed = passed
                progress.save()
 
            return JsonResponse({
                "status": "success", 
                "message": "Result saved", 
                "passed": passed, 
                "score_percent": percentage,
                "score_raw": score_raw,
                "total": total_q,
                "results": results
            })
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=500)
    return JsonResponse({"status": "error", "message": "Invalid method"}, status=400)



@login_required
def member_progress_api(request, member_id):
    try:
        # Check if the user is an admin for some organization
        membership = OrganizationMember.objects.filter(user=request.user, role="ADMIN").first()
        if not membership:
            return JsonResponse({"status": "error", "message": "Unauthorized"}, status=403)
            
        org = membership.organization
        member = OrganizationMember.objects.filter(id=member_id, organization=org).first()
        if not member:
            return JsonResponse({"status": "error", "message": "Member not found"}, status=404)
            
        user_obj = member.user
        
        # Identify Training Type based on Plan
        active_sub = Subscription.objects.filter(organization=org, status="ACTIVE").first()
        training_type = "POSH"
        if active_sub and active_sub.plan.type in ["POCSO", "BOTH"]:
            if active_sub.plan.type == "POCSO":
                training_type = "POCSO"
                
        all_modules = TrainingModule.objects.filter(module_type=training_type).order_by("order")
        user_progress_map = set(
            ModuleProgress.objects.filter(
                user=user_obj, module__module_type=training_type, is_completed=True
            ).values_list("module_id", flat=True)
        )
        
        vid_mods = [m for m in all_modules if m.video_file]
        ppt_mods = [m for m in all_modules if m.ppt_file and not m.video_file]
        
        total_vid_count = len(vid_mods)
        total_ppt_count = len(ppt_mods)
        
        completed_ppt_count = sum(1 for m in ppt_mods if m.id in user_progress_map)
        
        total_vid_progress = 0.0
        for m in vid_mods:
            if m.id in user_progress_map:
                total_vid_progress += 100.0
            else:
                prog = ModuleProgress.objects.filter(user=user_obj, module=m).first()
                if prog and m.duration_seconds > 0:
                    percent_watched = (prog.last_position / m.duration_seconds) * 100.0
                    percent_watched = min(99.0, max(0.0, percent_watched))
                    total_vid_progress += percent_watched
                else:
                    total_vid_progress += 0.0
                    
        video_percent = int(total_vid_progress / total_vid_count) if total_vid_count > 0 else 0
        ppt_percent = int((completed_ppt_count / total_ppt_count) * 100) if total_ppt_count > 0 else 0
        
        # Calculate Total Active Time
        total_mins_agg = DailyActivity.objects.filter(user=user_obj).aggregate(Sum("minutes_watched"))["minutes_watched__sum"] or 0
        total_secs_agg = DailyActivity.objects.filter(user=user_obj).aggregate(Sum("seconds_watched"))["seconds_watched__sum"] or 0
        grand_total_seconds = (total_mins_agg * 60) + total_secs_agg

        # Fallback/addition based on actual video progress
        video_progress_seconds = 0
        for m in all_modules:
            if m.video_file:  # Only count video modules for watch time
                if m.id in user_progress_map:
                    video_progress_seconds += m.duration_seconds
                else:
                    prog = ModuleProgress.objects.filter(user=user_obj, module=m).first()
                    if prog:
                        video_progress_seconds += int(prog.last_position)

        grand_total_seconds = max(grand_total_seconds, video_progress_seconds)
        hours = grand_total_seconds // 3600
        minutes = (grand_total_seconds % 3600) // 60
        total_active_time = f"{hours}h {minutes}m"
        
        # Check quiz completion
        quiz_module = next((m for m in all_modules if "quiz" in m.title.lower() and m.ppt_file and not m.video_file), None)
        quiz_completed = False
        if quiz_module:
            quiz_prog = ModuleProgress.objects.filter(user=user_obj, module=quiz_module).first()
            quiz_completed = quiz_prog.is_completed if quiz_prog else False
            
        assessment = AssessmentProgress.objects.filter(user=user_obj, assessment_type=training_type).first()
        quiz_score = assessment.score if assessment else None
        quiz_passed = assessment.is_passed if assessment else False
        
        # Video lesson modules list
        video_lesson_modules = []
        for i, mod in enumerate(vid_mods):
            if "quiz" not in mod.title.lower():
                video_lesson_modules.append({
                    "id": mod.id,
                    "title": mod.title,
                    "is_completed": mod.id in user_progress_map,
                    "thumbnail_url": mod.thumbnail.url if mod.thumbnail else ""
                })
                
        # PPT modules list (useful for POCSO dashboard)
        ppt_modules_list = []
        for mod in ppt_mods:
            ppt_modules_list.append({
                "id": mod.id,
                "title": mod.title,
                "is_completed": mod.id in user_progress_map,
                "is_quiz": "quiz" in mod.title.lower(),
                "thumbnail_url": mod.thumbnail.url if mod.thumbnail else ""
            })
            
        return JsonResponse({
            "status": "success",
            "video_percent": video_percent,
            "ppt_percent": ppt_percent,
            "total_active_time": total_active_time,
            "quiz_completed": quiz_completed,
            "quiz_score": quiz_score,
            "quiz_passed": quiz_passed,
            "video_lesson_modules": video_lesson_modules,
            "ppt_modules": ppt_modules_list,
            "training_type": training_type
        })
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)




# --- 6b. COMPANY EMPLOYEE TRAINING PAGES (No Certificate) ---






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




def workplace(request):
    return render(request, "workplace.html")


def legal(request):
    return render(request, "legal.html")




def why_choose_ohs(request):
    return render(request, "why_choose_ohs.html")




# --- UPDATED TUTORIAL VIEW ---
def tutorial_view(request):
    # Default to showing both for non-logged in users
    show_posh = True
    show_pocso = True

    is_accounts_user = request.user.is_authenticated and getattr(request.user, "account_type", None) == "ACCOUNTS"

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
        "is_accounts_user": is_accounts_user,
        "logout_url": "training_logout",
    }
    return render(request, "training_portal.html", context)
















# --- 8. BULK IMPORT FEATURES ---


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
    writer.writerow(["Name", "Last name", "Department", "Email", "Mobile (Optional)"])
    writer.writerow(["John", "Doe", "IT", "john.doe@company.com", "9999999999"])
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
        pocso_reg = POCSORegistration.objects.filter(email=org.owner.email).first()
        reg = posh_reg or pocso_reg
        seat_limit = reg.employee_count if reg else org.max_users
        csv_file = request.FILES["employee_file"]

        # Validate CSV file size and actual content/mime type
        is_valid, err_msg = validate_csv_file(csv_file)
        if not is_valid:
            messages.error(request, err_msg)
            return redirect("company_dashboard")

        try:
            file_data = csv_file.read().decode("utf-8-sig")
            csv_data = io.StringIO(file_data)
            reader = csv.DictReader(csv_data)

            if reader.fieldnames:
                reader.fieldnames = [name.strip() for name in reader.fieldnames]

            added_count = 0
            skipped_count = 0
            errors = []

            current_count = OrganizationMember.objects.filter(
                organization=org, role="MEMBER"
            ).count()

            for row in reader:
                if current_count >= seat_limit:
                    messages.warning(
                        request,
                        f"⚠️ Seat limit reached ({seat_limit}). Stopped after adding {added_count} employee(s).",
                    )
                    break

                first_name = row.get("Name", "").strip()
                last_name = row.get("Last name", "").strip()
                department = row.get("Department", "").strip()
                email = row.get("Email", "").strip()
                password = row.get("Default password", "").strip()
                phone = row.get("Mobile")
                if phone is None: 
                    phone = row.get("Mobile (Optional)")
                if phone is None:
                    phone = row.get("Mobile Number")
                if phone is None:
                    phone = row.get("Phone")
                if phone is None:
                    phone = ""
                phone = phone.strip()

                # Use organization's default password if not provided in CSV
                if not password:
                    password = org.default_password

                if not email:
                    skipped_count += 1
                    continue

                if not password:
                    skipped_count += 1
                    errors.append(f"{email}: No password available.")
                    continue

                if User.objects.filter(email=email).exists():
                    skipped_count += 1
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
                    if phone:
                        user.phone = phone

                    if hasattr(user, "department"):
                        user.department = department

                    user.save()

                    OrganizationMember.objects.create(
                        organization=org, user=user, role="MEMBER"
                    )

                    # Regenerate user_id after membership is created (pass org to avoid lookup)
                    user.user_id = user.generate_user_id(organization=org)
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
                    current_count += 1
                except Exception as e:
                    skipped_count += 1
                    errors.append(f"{email}: {str(e)}")
                    logger.warning(f"Skipping employee import row: {e}")
                    continue

            if added_count > 0:
                msg = f"✅ Successfully imported {added_count} employee(s)."
                if skipped_count > 0:
                    msg += f" {skipped_count} row(s) skipped (duplicates or missing data)."
                messages.success(request, msg)
            else:
                if errors:
                    messages.error(request, f"Import failed. Errors: {'; '.join(errors[:3])}")
                else:
                    messages.warning(
                        request, "⚠️ No new employees were added. Check for duplicate emails or empty rows in your CSV."
                    )

        except Exception as e:
            messages.error(request, f"Error processing file: {str(e)}")

    else:
        messages.error(request, "No file was uploaded. Please select a CSV file and try again.")

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


def tab_close_logout(request):
    """
    Called via navigator.sendBeacon() when the user closes a dashboard tab.
    Removes the closed tab ID from active tabs tracking in the cache. If no active tabs remain,
    marks the session for logout in the cache after a 15-second grace period.
    """
    import time
    from django.core.cache import cache
    
    if request.method == "POST" and request.user.is_authenticated:
        session_key = request.session.session_key
        if session_key:
            page_load_id = request.GET.get('page_load_id')
            active_tabs = cache.get(f"active_tabs_{session_key}", [])
            
            if page_load_id:
                if page_load_id in active_tabs:
                    active_tabs.remove(page_load_id)
                    cache.set(f"active_tabs_{session_key}", active_tabs, timeout=86400)
                
                # If no active tabs remain, mark session for unload in the cache
                if not active_tabs:
                    cache.set(f"unload_pending_at_{session_key}", time.time(), timeout=60)
            else:
                # Fallback for pages that did not pass page_load_id (immediate pending unload)
                cache.set(f"unload_pending_at_{session_key}", time.time(), timeout=60)
            
    return HttpResponse(status=204)  # No Content — beacon doesn't need a body


def custom_logout(request):
    # Accepts GET or POST (used by tab-close beacon and some direct links)
    logout(request)
    return redirect("home")


# FIX #13: Require POST for logout to prevent CSRF-based logout via GET links
@require_POST
def accounts_logout(request):
    """Fully log out the accounts user and clear the session."""
    logout(request)
    return redirect("home")


# FIX #13: Require POST for logout to prevent CSRF-based logout via GET links
@require_POST
def hr_logout(request):
    """Fully log out the user from all portals and clear authentication."""
    logout(request)
    return redirect("home")


# FIX #13: Require POST for logout to prevent CSRF-based logout via GET links
@require_POST
def training_logout(request):
    """Fully log out the user from all portals and clear authentication."""
    logout(request)
    return redirect("home")


def download_certificate(request, course_type="POSH"):
    import logging
    cert_logger = logging.getLogger("home.certificate")

    if not request.user.is_authenticated:
        return redirect("login")

    # Check if downloading for another user (company admin)
    user_id = request.GET.get("user_id")
    is_admin_download = bool(user_id)

    if user_id:
        # Verify that the requester is an admin of the organization
        try:
            target_user = User.objects.get(id=user_id)
            # Check if current user is admin
            is_admin = OrganizationMember.objects.filter(
                user=request.user, role="ADMIN"
            ).exists()

            if not is_admin:
                cert_logger.warning(f"Non-admin {request.user.id} tried to download cert for user {user_id}")
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
                cert_logger.warning(f"Admin {request.user.id} tried to download cert for user {user_id} in different org")
                messages.error(
                    request,
                    "Cannot download certificate for user outside your organization.",
                )
                return redirect("company_dashboard")

            certificate_user = target_user
        except User.DoesNotExist:
            cert_logger.error(f"Certificate download: User {user_id} not found")
            messages.error(request, "User not found.")
            return redirect("company_dashboard")
    else:
        certificate_user = request.user

    cert_logger.info(f"Certificate download: user={certificate_user.id}, course={course_type}, is_admin_download={is_admin_download}")

    # 1. Check Completion
    # When HR admin downloads for employee, only check assessment (quiz passed).
    # The employee is already shown in the certified_employees list which requires both.
    # Skip module count check for admin downloads to avoid live DB inconsistencies.
    if course_type == "POSH":
        if not is_admin_download:
            # Self-download: strict module check
            modules = TrainingModule.objects.filter(module_type="POSH")
            visible_modules = [
                m for m in modules
                if m.video_file or (m.ppt_file and not m.video_file and "quiz" in m.title.lower())
            ]
            visible_ids = [m.id for m in visible_modules]
            total = len(visible_modules)
            completed = ModuleProgress.objects.filter(
                user=certificate_user, module_id__in=visible_ids, is_completed=True
            ).count()
            cert_logger.info(f"POSH self-download: total={total}, completed={completed}")
            if total == 0 or completed < total:
                messages.error(request, "Training must be completed before downloading the certificate.")
                return redirect("posh_act_page")

        # Assessment check (applies to both self and admin downloads)
        is_employee = OrganizationMember.objects.filter(user=certificate_user, role="MEMBER").exists()
        if is_employee:
            if is_admin_download:
                # If downloading from company dashboard, they are already certified (completed coursework)
                has_passed_assessment = True
            else:
                # POSH corporate training has no separate final assessment; coursework complete is certificate eligible.
                modules = TrainingModule.objects.filter(module_type="POSH")
                visible_modules = [
                    m for m in modules
                    if m.video_file or (m.ppt_file and not m.video_file and "quiz" in m.title.lower())
                ]
                visible_ids = [m.id for m in visible_modules]
                total = len(visible_modules)
                completed = ModuleProgress.objects.filter(
                    user=certificate_user, module_id__in=visible_ids, is_completed=True
                ).count()
                has_passed_assessment = (total > 0 and completed == total)
        else:
            has_passed_assessment = AssessmentProgress.objects.filter(
                user=certificate_user, assessment_type="POSH", is_passed=True
            ).exists()
            
        cert_logger.info(f"POSH assessment passed: {has_passed_assessment} for user {certificate_user.id}")
        if not has_passed_assessment:
            messages.error(request, "Final Quiz must be passed to download the certificate.")
            return (
                redirect("posh_act_page")
                if not is_admin_download
                else redirect("company_dashboard")
            )

    elif course_type == "POCSO":
        if not is_admin_download:
            # Self-download: strict module check
            modules = TrainingModule.objects.filter(module_type="POCSO")
            visible_modules = [
                m for m in modules
                if m.video_file or (m.ppt_file and not m.video_file and "quiz" in m.title.lower())
            ]
            visible_ids = [m.id for m in visible_modules]
            total = len(visible_modules)
            completed = ModuleProgress.objects.filter(
                user=certificate_user, module_id__in=visible_ids, is_completed=True
            ).count()
            cert_logger.info(f"POCSO self-download: total={total}, completed={completed}")
            if total == 0 or completed < total:
                messages.error(request, "Training must be completed before downloading the certificate.")
                return redirect("pocso_act_page")

        has_passed_assessment = AssessmentProgress.objects.filter(
            user=certificate_user, assessment_type="POCSO", is_passed=True
        ).exists()
        cert_logger.info(f"POCSO assessment passed: {has_passed_assessment} for user {certificate_user.id}")
        if not has_passed_assessment:
            messages.error(request, "Final Quiz must be passed to download the certificate.")
            return (
                redirect("pocso_act_page")
                if not is_admin_download
                else redirect("company_dashboard")
            )

    # 2. Check if company logo is uploaded (mandatory for organization members)
    membership = OrganizationMember.objects.filter(user=certificate_user).first()
    if membership:
        org = membership.organization
        custom_logo_path = request.session.get('temp_logo_path')
        if not org.logo and not custom_logo_path:
            cert_logger.warning(f"Download blocked: Organization '{org.name}' has no logo uploaded.")
            messages.error(request, "A company logo is required before downloading certificates. Please upload a logo first.")
            return (
                redirect("company_dashboard")
                if is_admin_download
                else redirect("posh_act_page" if course_type == "POSH" else "pocso_act_page")
            )

    # 3. Generate PDF
    custom_logo_path = request.session.get('temp_logo_path')
    pdf_content = generate_certificate(certificate_user, course_type, custom_logo_path=custom_logo_path)

    if not pdf_content:
        cert_logger.error(f"generate_certificate returned None for user {certificate_user.id}, course {course_type}")
        messages.error(request, "Error generating certificate. Please contact support.")
        return (
            redirect("posh_act_page") if not is_admin_download else redirect("company_dashboard")
        )

    # 3. Serve PDF
    cert_logger.info(f"Certificate successfully generated for user {certificate_user.id}")
    response = HttpResponse(pdf_content, content_type="application/pdf")
    filename = f"Certificate_{course_type}_{certificate_user.username}.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def custom_404(request, exception):
    return render(request, "error_page.html", status=404)


def custom_403(request, exception):
    return render(request, "error_page.html", status=403)


def custom_500(request):
    return render(request, "error_page.html", status=500)


def custom_402(request, exception=None):
    return render(request, "error_page.html", status=402)






def accounts_login_view(request):
    """Custom login for accounts department"""
    if request.method == "POST":
        u = request.POST.get("username", "").strip()
        p = request.POST.get("password")
        ip = get_client_ip(request)

        is_locked, remaining = check_login_lockout(u, ip)
        if is_locked:
            minutes = (remaining + 59) // 60
            error_msg = f"Too many failed login attempts. Locked for {minutes} minute(s)."
            return render(request, "accounts_login.html", {"error_message": error_msg})

        user = authenticate(username=u, password=p)
        if user is not None and (user.account_type == "ACCOUNTS" or user.is_superuser):
            clear_login_attempts(u, ip)
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            return redirect("accounts_dashboard")
        else:
            increment_login_attempts(u, ip)
            return render(
                request,
                "accounts_login.html",
                {"form": type("F", (), {"errors": True})(), "error_message": "Invalid credentials. Please try again."},
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

    # Initialize default templates if they don't exist in the database
    from home.models import EmailTemplate
    
    defaults = {
        "PAY_NOW": {
            "subject": "Thank you for your interest in our services",
            "body": """Dear {name},

Greetings from Open Hand Private Limited!

We are truly pleased to have you here and thank you for taking the time to visit our website and register for {type} training. At Open Hand, we believe that every workplace deserves to be safe, respectful, and compliant — and we're honoured that you've chosen to partner with us on this important journey.

To confirm your booking, please click the link below to make the payment:
➡ {payment_link}

Once the payment is received, our team will reach out to you within 24 hours to finalise the training schedule and share pre-training materials.

OR

📞 Prefer to discuss first? We're just a call away!
If you'd like to discuss the training modules, understand the content in more detail, or explore customisation options, feel free to call us at:
+91- 99889 97555

Once you complete the payment, you will be provided a user name and password to login to our Training module.

Once again, thank you for your trust and interest in us. We look forward to supporting your organisation in creating a safer, more empowered workplace.

Warm regards,

Open Hand Private Limited
openhandpvtltd@gmail.com | openhandsolutions.com"""
        },
        "PAYMENT_VERIFIED": {
            "subject": "Payment confirmed — Welcome to Open Hand! Your login details inside",
            "body": """Dear {name},

Greetings from Open Hand Private Limited!

Thank you for your trust in us. We are delighted to confirm that your payment of {amount} has been successfully received. 🎉

You now have full access to the Open Hand Resource Platform — your one-stop portal for all things {type} compliance, training, and workplace safety.

📖 Login Instructions
1. Click the link below to set up your password and access your dashboard:
{setup_link}
2. Once logged in, explore your dashboard and all available resources

⚠️ For security reasons, please change your password immediately after first login. Do not share your credentials.

📌 What You Get Access To
Once logged in, your portal includes:
- HR Dashboard: Track training progress, view compliance status, manage employee records
- {type} Posters: Ready-to-print posters for your office premises — edit text, add logo, and download
- Unlimited Resources: Training modules, presentations, handbooks, case studies, and more
- Blogs & Newsletters: Stay updated on amendments, best practices, and industry insights
- Forms & Documents: Complaint forms, IC meeting templates, inquiry report formats, annual report templates
- Manage Employees: Add employees individually or upload an Excel sheet in bulk — assign trainings, track completion
- IC Training Modules (as applicable): Access all materials for Internal Committee members — inquiry procedures, evidence handling, report writing
- And much more!

📞 Need Help? We're Here for You
If you face any issues logging in, changing your password, or navigating the portal, please don't hesitate to reach out:
📞 +91- 99889 97555  |  📧 openhandpvtltd@gmail.com

You can also reply to this email, and our support team will get back to you within 4–6 hours.

Once again, a heartfelt welcome to the Open Hand community. We are excited to be your partner in building a safer, compliant, and empowered workplace.

Warm regards,

Open Hand Private Limited
openhandpvtltd@gmail.com | openhandsolutions.com"""
        },
        "EMPLOYEE_WELCOME": {
            "subject": "Enrolled in Compliance Training Program – Open Hand Private Limited",
            "body": """Dear {name},

Greetings from Open Hand Private Limited (OHPL)

You have been successfully enrolled in the {training_module_name} on the OHPL Learning Portal.

This interactive training module will help you understand:
- The fundamentals of the Prevention of Sexual Harassment (POSH) Act and what constitutes sexual harassment at the workplace.
- Different forms of sexual harassment, including physical, verbal, non-verbal, and digital conduct.
- Appropriate workplace behaviour, professional boundaries, and respectful communication.
- Practical workplace scenarios and case studies to reinforce your learning.

Training Requirement
Please complete the training within {training_duration}.
At the end of the module, you will be required to complete a short assessment quiz.
Upon successful meeting the assessment criteria, your Certificate of Completion will be available for download from the company dashboard.

Login Credentials
Portal Link: {login_url}
Username: {email}
Temporary Password: {password}

Please log in using the above credentials and change your password upon your first login.

If you require any assistance, please contact us at {support_email}.

We look forward to your active participation in creating a safe, respectful, and inclusive workplace.

Warm regards,
Learning & Compliance Team
Open Hand Private Limited (OHPL)"""
        },
        "EMPLOYEE_REMINDER": {
            "subject": "Mandatory POSH Training - Pending Completion",
            "body": """Dear {name},

This is a friendly reminder that your mandatory POSH (Prevention of Sexual Harassment) training is still pending.

As of today:
Training Status: {status}
Completion Percentage: {completion_percentage}%
Due Date: {due_date}

Please log in to the learning portal and complete your assigned training and assessment before the due date.

Completing the training is mandatory and forms an important part of our organization's commitment to maintaining a safe, respectful, and legally compliant workplace.

If you have already completed the training recently, please disregard this email.

For any technical assistance, please contact {support_email} or +91- 99889 97555.

Thank you for your prompt attention and cooperation.

Warm regards,
Learning & Compliance Team
Open Hand Private Limited"""
        }
    }
    
    for tier, content in defaults.items():
        template, created = EmailTemplate.objects.get_or_create(tier_key=tier)
        if tier == "PAY_NOW" and not created and template.body and "successfully registering and completing the payment" in template.body:
            # Revert PAY_NOW to default and copy the custom text to PAYMENT_VERIFIED if PAYMENT_VERIFIED is default
            pv_template, pv_created = EmailTemplate.objects.get_or_create(tier_key="PAYMENT_VERIFIED")
            if pv_created or not pv_template.body or "📖 Login Instructions" in pv_template.body:
                pv_template.body = template.body
                pv_template.subject = template.subject
                pv_template.save()
            
            # Reset PAY_NOW to its correct default
            template.subject = content["subject"]
            template.body = content["body"]
            template.save()
        elif created or not template.body or "<p>" in template.body or "<table>" in template.body:
            template.subject = content["subject"]
            template.body = content["body"]
            template.save()

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
        ("PAY_NOW", "Registration Interest & Payment Link"),
        ("PAYMENT_VERIFIED", "Payment Verified & Onboarding Link"),
        ("EMPLOYEE_WELCOME", "Employee Welcome – Account Credentials"),
        ("EMPLOYEE_REMINDER", "Training Reminder – Pending Completion"),
    ]

    from home.models import EmailTemplate, DeletedPoster
    email_templates = {et.tier_key: et for et in EmailTemplate.objects.all()}
    deleted_posters = list(DeletedPoster.objects.values_list('poster_path', flat=True))

    # Collect any custom posters uploaded via the Add Poster feature
    posters_dir = os.path.join(settings.MEDIA_ROOT, "Posters")
    custom_posters = []
    if os.path.isdir(posters_dir):
        for fname in sorted(os.listdir(posters_dir)):
            if fname.startswith("Custom Poster"):
                media_path = f"/media/Posters/{fname}"
                name_no_ext = os.path.splitext(fname)[0]
                custom_posters.append({"path": media_path, "title": name_no_ext})

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
            "deleted_posters": deleted_posters,
            "custom_posters": custom_posters,
        },
    )


@login_required(login_url="accounts_login")
def accounts_save_email_templates_view(request):
    """Save updated email templates from the accounts portal"""
    if request.user.account_type != "ACCOUNTS" and not request.user.is_superuser:
        return redirect("home")

    if request.method == "POST":
        tiers = ["PAY_NOW", "PAYMENT_VERIFIED", "EMPLOYEE_WELCOME", "EMPLOYEE_REMINDER"]
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

        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
            from django.http import JsonResponse
            return JsonResponse({'status': 'success'})

    from django.urls import reverse

    return redirect(f"{reverse('accounts_dashboard')}?active_tab=emails")


@login_required(login_url="accounts_login")
def delete_registrations_view(request):
    """Permanently delete selected registrations from the database"""
    if request.user.account_type != "ACCOUNTS" and not request.user.is_superuser:
        from django.http import JsonResponse
        return JsonResponse({"status": "error", "message": "Unauthorized."}, status=403)

    if request.method == "POST":
        import json
        from django.http import JsonResponse
        try:
            data = json.loads(request.body)
            reg_ids = data.get("ids", [])
            reg_type = data.get("type", "")

            if not reg_ids:
                return JsonResponse({"status": "error", "message": "No registrations selected."}, status=400)

            if reg_type == "posh":
                from home.models import POSHRegistration
                POSHRegistration.objects.filter(id__in=reg_ids).delete()
            elif reg_type == "pocso":
                from home.models import POCSORegistration
                POCSORegistration.objects.filter(id__in=reg_ids).delete()
            else:
                return JsonResponse({"status": "error", "message": "Invalid registration type."}, status=400)

            return JsonResponse({"status": "success"})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=500)

    from django.shortcuts import redirect
    return redirect("accounts_dashboard")


@login_required(login_url="accounts_login")
def delete_poster_view(request):
    """Permanently delete an awareness poster from the system"""
    if request.user.account_type != "ACCOUNTS" and not request.user.is_superuser:
        return redirect("home")

    if request.method == "POST":
        from home.models import DeletedPoster
        poster_path = request.POST.get("poster_path")

        if poster_path:
            # For custom uploaded posters — delete the actual file from disk
            import urllib.parse
            decoded_path = urllib.parse.unquote(poster_path)
            # poster_path is like /media/Posters/Custom Poster abc123.webp
            relative = decoded_path.lstrip("/")  # media/Posters/...
            abs_path = os.path.join(settings.MEDIA_ROOT, *relative.split("/")[1:])  # strip "media/"
            if os.path.isfile(abs_path):
                try:
                    os.remove(abs_path)
                except OSError:
                    pass

            # Mark as permanently deleted in DB so static posters also disappear
            DeletedPoster.objects.get_or_create(poster_path=poster_path)

    from django.urls import reverse
    return redirect(f"{reverse('accounts_dashboard')}?active_tab=posters")


# FIX #2: Added @login_required to prevent unauthenticated access
@login_required(login_url="accounts_login")
def add_poster_view(request):
    """Upload a new awareness poster image to the Posters library (Accounts portal only)"""
    if request.user.account_type != "ACCOUNTS" and not request.user.is_superuser:
        return redirect("home")

    if request.method == "POST":
        poster_image = request.FILES.get("poster_image")
        if poster_image:
            # Validate file type and size (max 10 MB)
            valid_exts = [".png", ".jpg", ".jpeg", ".webp"]
            ext = os.path.splitext(poster_image.name)[1].lower()
            is_image_mime = poster_image.content_type and poster_image.content_type.startswith("image/")

            if ext not in valid_exts or poster_image.size > 10 * 1024 * 1024 or not is_image_mime:
                messages.error(request, "Invalid file. Poster must be a PNG, JPG, JPEG, or WebP image under 10MB.")
                from django.urls import reverse
                return redirect(f"{reverse('accounts_dashboard')}?active_tab=posters")

            try:
                from PIL import Image as PILImage
                img = PILImage.open(poster_image)
                img.verify()
                poster_image.seek(0)
            except Exception:
                messages.error(request, "Invalid image file. The file is corrupted or not a valid image.")
                from django.urls import reverse
                return redirect(f"{reverse('accounts_dashboard')}?active_tab=posters")

            # Save to /media/Posters/
            posters_dir = os.path.join(settings.MEDIA_ROOT, "Posters")
            os.makedirs(posters_dir, exist_ok=True)

            # Use a safe filename based on the original name
            import uuid
            safe_name = f"Custom Poster {uuid.uuid4().hex[:8]}{ext}"
            save_path = os.path.join(posters_dir, safe_name)

            with open(save_path, "wb+") as destination:
                for chunk in poster_image.chunks():
                    destination.write(chunk)

    from django.urls import reverse
    return redirect(f"{reverse('accounts_dashboard')}?active_tab=posters")


# FIX #1: Added @login_required and accounts-role check to prevent unauthenticated email sending
@login_required(login_url="accounts_login")
def trigger_tier_email_view(request):
    """AJAX view to trigger a tiered email based on user selection (Accounts portal only)"""
    # Only ACCOUNTS users or superusers may trigger emails
    if request.user.account_type != "ACCOUNTS" and not request.user.is_superuser:
        return JsonResponse({"status": "error", "message": "Unauthorized."}, status=403)

    # FIX #4: Rate limit — max 20 emails per accounts user per hour
    if check_rate_limit(f"email_trigger_{request.user.id}", limit=20, window=3600):
        return JsonResponse({"status": "error", "message": "Too many emails sent. Please wait before sending more."}, status=429)

    if request.method == "POST":
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
                    {"status": "error", "message": "Email failed to send."}, status=500
                )
        except Exception as e:
            _logger = logging.getLogger(__name__)
            _logger.exception(f"trigger_tier_email_view error: {e}")
            return JsonResponse({"status": "error", "message": "An error occurred processing your request."}, status=400)

    return JsonResponse({"status": "error", "message": "Invalid request"}, status=405)


logger = logging.getLogger(__name__)










logger = logging.getLogger(__name__)












def registration_selection_view(request):
    """Simple selection page between POSH and POCSO registration"""
    return render(request, "registration_selection.html")








def submit_payment_view(request, token):
    """Handle payment screenshot upload for POSH/POCSO.
    FIX #2 (IDOR): The registration_id is no longer exposed in the URL.
    Instead, the email contains a cryptographically signed token that
    embeds the registration ID. This prevents enumeration / unauthorized uploads.
    """
    from django.core import signing

    # Verify signed token (max 7 days)
    try:
        payload = signing.loads(token, salt="submit-payment", max_age=60 * 60 * 24 * 7)
        registration_id = payload["reg_id"]
        reg_type = payload["reg_type"]
    except signing.SignatureExpired:
        return render(request, "error_page.html", {
            "error_title": "Link Expired",
            "error_message": "This payment link has expired. Please contact support to receive a new link."
        }, status=410)
    except Exception:
        return render(request, "error_page.html", {
            "error_title": "Invalid Link",
            "error_message": "This payment link is invalid or has been tampered with. Please contact support."
        }, status=400)

    if reg_type == "POSH":
        registration = get_object_or_404(POSHRegistration, id=registration_id)
    else:
        registration = get_object_or_404(POCSORegistration, id=registration_id)

    from .utils import get_posh_billing_data, get_pocso_billing_data
    if reg_type == "POSH":
        billing_data = get_posh_billing_data(registration)
    else:
        billing_data = get_pocso_billing_data(registration)

    if request.method == "POST":
        screenshot = request.FILES.get("payment_screenshot")
        if screenshot:
            is_valid, err_msg = validate_image_file(screenshot)
            if not is_valid:
                messages.error(request, err_msg)
                return redirect("submit_payment", token=token)
            registration.payment_screenshot = screenshot
            registration.payment_status = "SUBMITTED"
            registration.save()

            messages.success(request, "Payment proof uploaded successfully! Our accounts team will review and verify your payment.")
            return redirect("submit_payment", token=token)

    context = {
        "registration": registration,
        "reg_type": reg_type,
        "billing_data": billing_data,
        "total_amount": billing_data["total_amount"],
    }
    return render(request, "submit_payment.html", context)


@login_required(login_url="login")
def send_posh_reminders(request):
    """
    AJAX view called by the HR Admin to send training reminders to selected employees.
    """
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Method not allowed."}, status=405)

    # FIX #4: Rate limit — max 10 reminder batches per admin per 10 minutes
    if check_rate_limit(f"reminders_{request.user.id}", limit=10, window=600):
        return JsonResponse({"status": "error", "message": "Too many requests. Please wait before sending more reminders."}, status=429)

    # 1. Authorize Admin
    membership = OrganizationMember.objects.filter(user=request.user, role="ADMIN").first()
    if not membership:
        return JsonResponse({"status": "error", "message": "Unauthorized. Admin only."}, status=403)

    org = membership.organization
    active_sub = Subscription.objects.filter(organization=org, status="ACTIVE").first()

    try:
        data = json.loads(request.body)
        member_ids = data.get("member_ids", [])
    except Exception:
        return JsonResponse({"status": "error", "message": "Invalid request body."}, status=400)

    if not member_ids:
        return JsonResponse({"status": "error", "message": "No employees selected."}, status=400)

    # Get modules to calculate progress
    training_type = "POSH"
    if active_sub and active_sub.plan.type in ["POCSO", "BOTH"]:
        if active_sub.plan.type == "POCSO":
            training_type = "POCSO"

    all_modules = TrainingModule.objects.filter(module_type=training_type).order_by("order")
    visible_modules = [
        m for m in all_modules
        if m.video_file or (m.ppt_file and not m.video_file and "quiz" in m.title.lower())
    ]
    visible_module_ids = [m.id for m in visible_modules]
    total_modules_count = len(visible_modules)

    sent_count = 0
    from home.email_utils import send_posh_reminder_email

    for m_id in member_ids:
        mem = OrganizationMember.objects.filter(id=m_id, organization=org, role="MEMBER").first()
        if not mem:
            continue

        user_obj = mem.user

        # Calculate progress
        completed_modules = ModuleProgress.objects.filter(
            user=user_obj, module_id__in=visible_module_ids, is_completed=True
        ).count()

        total_progress = 0.0
        user_progress_map = set(
            ModuleProgress.objects.filter(
                user=user_obj, module__module_type=training_type, is_completed=True
            ).values_list("module_id", flat=True)
        )
        for m in visible_modules:
            if m.id in user_progress_map:
                total_progress += 100.0
            elif m.video_file:  # Only video modules have partial progress
                prog = ModuleProgress.objects.filter(user=user_obj, module=m).first()
                if prog and m.duration_seconds > 0:
                    percent_watched = (prog.last_position / m.duration_seconds) * 100.0
                    percent_watched = min(99.0, max(0.0, percent_watched))
                    total_progress += percent_watched

        percent_complete = (
            int(total_progress / total_modules_count)
            if total_modules_count > 0
            else 0
        )
        is_completed = (completed_modules == total_modules_count) and (total_modules_count > 0)

        # Do not send reminders to completed employees
        if is_completed:
            continue

        # Check status
        total_mins_agg = DailyActivity.objects.filter(user=user_obj).aggregate(Sum("minutes_watched"))["minutes_watched__sum"] or 0
        total_secs_agg = DailyActivity.objects.filter(user=user_obj).aggregate(Sum("seconds_watched"))["seconds_watched__sum"] or 0
        grand_total_seconds = (total_mins_agg * 60) + total_secs_agg

        has_started = False
        if grand_total_seconds > 0:
            has_started = True
        else:
            has_started = ModuleProgress.objects.filter(
                user=user_obj,
                module_id__in=visible_module_ids
            ).filter(
                Q(is_completed=True) | Q(last_position__gt=0.0)
            ).exists()

        status_str = "In Progress" if has_started else "Not Started"

        # Determine due date
        due_date_val = (mem.joined_at + timedelta(days=30)).strftime("%B %d, %Y")

        send_posh_reminder_email(user_obj, status_str, percent_complete, due_date_val)
        sent_count += 1

    return JsonResponse({"status": "success", "message": f"Successfully sent reminders to {sent_count} employees."})




