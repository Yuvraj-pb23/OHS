import logging
import os
from pathlib import Path
import html

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML

logger = logging.getLogger(__name__)


def generate_certificate(user, course_type="POSH", custom_logo_path=None):
    """
    Generates a PDF certificate for the given user and course type.
    """
    # 1. Determine Template Image
    if course_type == "POSH":
        template_name = "Certificate/Posh Certificate.png"
    else:
        template_name = "Certificate/POCSO CERT.png"

    # Construct absolute path to the image for WeasyPrint
    image_path = Path(settings.MEDIA_ROOT) / template_name
    if not image_path.exists():
        logger.error(f"Certificate template not found at {image_path}")
        return None

    # 2. Prepare Context
    name_str = f"{user.first_name} {user.last_name}".strip() or user.username
    if getattr(user, "designation", None):
        name_str += f" ({user.designation})"

    # Use Path.as_uri() to correctly generate file:///Y:/path/... on Windows
    # (avoids broken file://y:\path\... with backslashes)
    image_uri = image_path.as_uri()

    context = {
        "candidate_name": html.escape(name_str),
        "course_type": html.escape(course_type),
        "completion_date": html.escape(timezone.now().strftime("%d/%m/%Y")),  # e.g. 05/02/2026
        "image_path": image_uri,
    }

    # 3. Handle specific layout details
    if course_type == "POSH":
        # Retrieve company logo
        logo_uri = None
        if custom_logo_path:
            logo_path = Path(custom_logo_path)
            if logo_path.exists():
                logo_uri = logo_path.as_uri()
        else:
            from home.models import OrganizationMember
            membership = OrganizationMember.objects.filter(user=user).first()
            if membership:
                org = membership.organization
                if org.logo:
                    logo_path = Path(org.logo.path)
                    if logo_path.exists():
                        logo_uri = logo_path.as_uri()

        # Render logo container (covers default "COMPANY LOGO" placeholder with white circle background)
        logo_html = ""
        if logo_uri:
            logo_html = f'<div class="logo-container"><img class="logo-img" src="{logo_uri}" /></div>'
        else:
            logo_html = '<div class="logo-container"></div>'

        html_string = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                @page {{
                    size: 297mm 210mm; /* A4 Landscape */
                    margin: 0;
                }}
                body {{
                    margin: 0;
                    padding: 0;
                    width: 297mm;
                    height: 210mm;
                    background-image: url('{context['image_path']}');
                    background-size: cover;
                    background-repeat: no-repeat;
                    font-family: 'Helvetica', 'Arial', sans-serif;
                    position: relative;
                    color: #333;
                }}
                .candidate-name-container {{
                    position: absolute;
                    top: 33%;
                    left: 21%;
                    width: 58%;
                    height: 10%;
                    display: flex;
                    flex-direction: column;
                    justify-content: flex-end;
                    align-items: center;
                    padding-bottom: 8px;
                    box-sizing: border-box;
                    z-index: 10;
                }}
                .candidate-name-text {{
                    font-size: 30pt;
                    font-weight: bold;
                    color: #1e3a8a;
                    font-family: 'Georgia', 'Times New Roman', serif;
                    text-transform: uppercase;
                    margin: 0;
                    line-height: 1;
                }}
                .date-on {{
                    position: absolute;
                    top: 60.5%;
                    left: 41.5%;
                    width: 19%;
                    text-align: center;
                    font-size: 15pt;
                    font-weight: bold;
                    color: #1e3a8a;
                }}
                .date-bottom {{
                    position: absolute;
                    top: 78.5%;
                    left: 67.5%;
                    width: 11.5%;
                    text-align: center;
                    font-size: 14pt;
                    font-weight: bold;
                    color: #333;
                }}
                .logo-container {{
                    position: absolute;
                    top: 9%;
                    left: 82%;
                    width: 11.5%;
                    height: 16%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }}
                .logo-img {{
                    max-width: 90%;
                    max-height: 90%;
                    object-fit: contain;
                }}
            </style>
        </head>
        <body>
            <div class="candidate-name-container">
                <div class="candidate-name-text">{context['candidate_name']}</div>
            </div>
            <div class="date-on">{context['completion_date']}</div>
            <div class="date-bottom">{context['completion_date']}</div>
            {logo_html}
        </body>
        </html>
        """
    else:
        # Determine date position (adjusting based on user request to be after "held on")
        # Tweak these percentages to align with the template's 'Held on' gap
        date_top = "64.3%"
        date_left = "35.3%"

        # Inline CSS for pixel-perfect positioning (based on user requirement)
        html_string = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                @page {{
                    size: 297mm 210mm; /* A4 Landscape */
                    margin: 0;
                }}
                body {{
                    margin: 0;
                    padding: 0;
                    width: 297mm;
                    height: 210mm;
                    background-image: url('{context['image_path']}');
                    background-size: cover;
                    background-repeat: no-repeat;
                    font-family: 'Helvetica', 'Arial', sans-serif;
                    position: relative;
                    color: #333;
                }}
                .candidate-name {{
                    position: absolute;
                    top: 48%; /* Centered in the middle of the certificate */
                    left: 0;
                    width: 100%;
                    text-align: center;
                    font-size: 28pt;
                    font-weight: bold;
                    color: #1e3a8a; /* Using a professional dark blue to match template accents */
                    text-transform: uppercase;
                }}
                .date {{
                    position: absolute;
                    top: {date_top};
                    left: {date_left};
                    font-size: 14pt;
                    font-weight: bold;
                    color: #000;
                    display: inline-block;
                    width: auto;
                }}
            </style>
        </head>
        <body>
            <div class="candidate-name">{context['candidate_name']}</div>
            <div class="date">{context['completion_date']}</div>
        </body>
        </html>
        """

    # 4. Convert to PDF
    try:
        pdf_file = HTML(string=html_string).write_pdf()
        return pdf_file
    except Exception as e:
        logger.error(
            f"WeasyPrint failed to generate certificate for user {user.id}: {e}",
            exc_info=True,
        )
        return None


def get_posh_billing_data(registration):
    """Refactored helper to calculate POSH billing context without HTTP request"""
    from .models import POSHPricingConfig

    config = (
        POSHPricingConfig.objects.filter(is_active=True).order_by("-updated_at").first()
    )
    if not config:
        config = POSHPricingConfig()

    emp_count = registration.employee_count

    # 1. Determine Tier (t0 to t4)
    if emp_count <= config.price_tier_0_max:
        tier = "t0"
        per_employee_rate = config.price_tier_0_rate
    elif emp_count <= config.price_tier_1_max:
        tier = "t1"
        per_employee_rate = config.price_tier_1_rate
    elif emp_count <= config.price_tier_2_max:
        tier = "t2"
        per_employee_rate = config.price_tier_2_rate
    elif emp_count <= config.price_tier_3_max:
        tier = "t3"
        per_employee_rate = config.price_tier_3_rate
    else:
        tier = "t4"
        per_employee_rate = config.price_tier_4_rate

    # 2. Build Add-on Fees
    addon_fees = []
    training_cost = float(emp_count * per_employee_rate)

    # 2a. Base Subscription
    addon_fees.append(
        {
            "label": f"POSH Act Compliance ({emp_count} Employees)",
            "amount": training_cost,
            "points": [
                "Awareness Education",
                "Certification Support",
                "Compliance Records",
            ],
        }
    )

    # 2b. Policy Drafting
    if not registration.has_posh_policy:
        fee = float(getattr(config, f"fee_no_posh_policy_{tier}", 0))
        addon_fees.append(
            {
                "label": "POSH Protection Policy Drafting",
                "amount": fee,
                "points": [
                    "Full Policy Drafting",
                    "Legal Verification",
                    "Final Document Provision",
                ],
            }
        )

    # 2c. IC Formation
    if not registration.has_ic:
        fee = float(getattr(config, f"fee_no_ic_{tier}", 0))
        addon_fees.append(
            {
                "label": "Internal Committee (IC) Formation",
                "amount": fee,
                "points": [
                    "Member Appointment",
                    "Roles & Responsibilities",
                    "Statutory Documentation",
                ],
            }
        )

    # 2d. IC Training (Simplified for PDF)
    if registration.require_ic_training:
        req_mode = registration.requested_ic_training_mode
        if req_mode == "ONLINE":
            rate_field = "fee_ic_requested_online"
            display_mode = "Online"
        elif req_mode == "EXPERT_LED":
            req_type = registration.requested_expert_led_type
            if req_type == "PHYSICAL":
                rate_field = "fee_ic_requested_physical"
                display_mode = "Physical"
            else:
                rate_field = "fee_ic_requested_virtual"
                display_mode = "Virtual"
        else:
            rate_field = "fee_ic_history_other"
            display_mode = "Standard"

        fee = float(getattr(config, f"{rate_field}_{tier}", 0))
        addon_fees.append(
            {
                "label": f"IC Specialized Training ({display_mode})",
                "amount": fee,
                "points": [
                    "Expert-Led Session",
                    "Case Study Analysis",
                    "Legal Framework",
                ],
            }
        )

    # 2e. External Member Support
    if registration.require_external_member_support:
        fee = float(getattr(config, f"fee_no_external_member_{tier}", 0))
        addon_fees.append(
            {
                "label": "External Member Matchmaking",
                "amount": fee,
                "points": [
                    "Authorized Expert Search",
                    "Statutory Compliance",
                    "Yearly Support",
                ],
            }
        )

    # 2f. Statutory Portal (SHe Box)
    if (
        not registration.she_box_registered
        or registration.require_nodal_officer_support
    ):
        fee = float(getattr(config, f"fee_not_she_box_{tier}", 0))
        addon_fees.append(
            {
                "label": "Statutory Portal Compliance (SHe Box)",
                "amount": fee,
                "points": [
                    "Portal Registration",
                    "Digital Onboarding",
                    "Compliance Maintenance",
                ],
            }
        )

    subtotal = sum(item["amount"] for item in addon_fees)
    gst_rate = float(config.gst_percentage) / 100

    return {
        "addon_fees": addon_fees,
        "subtotal": subtotal,
        "gst_percentage": config.gst_percentage,
        "gst_amount": subtotal * gst_rate,
        "total_amount": subtotal * (1 + gst_rate),
        "training_total": training_cost,
        "total_add_ons": subtotal - training_cost,
    }


def get_pocso_billing_data(registration):
    """Refactored helper to calculate POCSO billing context without HTTP request"""
    from .models import POCSOPricingConfig

    config = (
        POCSOPricingConfig.objects.filter(is_active=True)
        .order_by("-updated_at")
        .first()
    )
    if not config:
        config = POCSOPricingConfig()

    gst_pct = float(config.gst_percentage)
    addon_fees = []

    if not registration.has_policy:
        addon_fees.append(
            {
                "label": "Child Protection Policy Drafting",
                "amount": float(config.fee_no_policy),
                "points": [
                    "Drafting & Customization",
                    "Statutory Review",
                    "Institutional Integration",
                ],
            }
        )
    if not registration.has_committee:
        addon_fees.append(
            {
                "label": "Child Safety Committee Formation",
                "amount": float(config.fee_no_committee),
                "points": [
                    "Member Selection Support",
                    "Appointment Letters",
                    "Statutory Documentation",
                ],
            }
        )

    if not registration.teaching_staff_trained:
        mode = (registration.teaching_training_mode or "ONLINE").upper()
        rate_attr = f'teacher_rate_{mode.lower().replace("_", "")}'
        rate = float(getattr(config, rate_attr, config.teacher_rate_online))

        if mode == "E_LEARNING":
            amount = registration.teachers_count * rate
            label = f"POCSO Awareness: Teaching Staff (Per Head x {registration.teachers_count})"
        else:
            amount = rate
            label = f"POCSO Awareness: Teaching Staff ({mode.title()} - Fixed Fee)"

        addon_fees.append(
            {
                "label": label,
                "amount": amount,
                "points": [
                    "Educational Resource Access",
                    "Certification Support",
                    "Compliance Reporting",
                ],
            }
        )

    if not registration.non_teaching_staff_trained:
        mode = (registration.non_teaching_training_mode or "ONLINE").upper()
        rate_attr = f'staff_rate_{mode.lower().replace("_", "")}'
        rate = float(getattr(config, rate_attr, config.staff_rate_online))

        if mode == "E_LEARNING":
            amount = registration.non_teaching_staff_count * rate
            label = f"POCSO Awareness: Non-Teaching Staff (Per Head x {registration.non_teaching_staff_count})"
        else:
            amount = rate
            label = f"POCSO Awareness: Non-Teaching Staff ({mode.title()} - Fixed Fee)"

        addon_fees.append(
            {
                "label": label,
                "amount": amount,
                "points": [
                    "Educational Resource Access",
                    "Certification Support",
                    "Compliance Reporting",
                ],
            }
        )

    student_workshop_total = 0
    if not registration.students_trained:
        student_workshop_total = registration.students_count * float(
            config.student_rate
        )
        addon_fees.append(
            {
                "label": "Student Body Safety Workshop",
                "amount": student_workshop_total,
                "points": [
                    "Student Outreach",
                    "Safety Awareness Curriculum",
                    "Institutional Safety Audit",
                ],
            }
        )

    subtotal = sum(f["amount"] for f in addon_fees)
    gst_amount = subtotal * (gst_pct / 100.0)

    return {
        "addon_fees": addon_fees,
        "subtotal": subtotal,
        "gst_percentage": gst_pct,
        "gst_amount": gst_amount,
        "total_amount": subtotal + gst_amount,
        "flat_fees_total": subtotal - student_workshop_total,
        "student_workshop_total": student_workshop_total,
    }


def generate_proforma_invoice_pdf(
    registration, registration_type="POSH", tier_key=None
):
    """Generates a Proforma Invoice PDF using WeasyPrint"""
    if registration_type == "POSH":
        billing_data = get_posh_billing_data(registration)
    else:
        billing_data = get_pocso_billing_data(registration)

    # Calculate tiered totals (matching logic in views.py)
    total_amount = billing_data["total_amount"]

    context = {
        "registration": registration,
        "billing_data": billing_data,
        "registration_type": registration_type,
        "tier_key": tier_key,
        "date": timezone.now().strftime("%d %b %Y"),
        "invoice_no": f"PRO-{registration_type[:3]}-{registration.id:05d}",
        "total_tier_1": total_amount,
        "total_tier_2": total_amount,
        "total_tier_3": total_amount,
        "base_url": (
            getattr(settings, "BASE_URL", None)
            or getattr(settings, "SITE_URL", "https://openhandsolutions.com")
        ),
        "logo_path": os.path.join(settings.BASE_DIR, "static", "img", "logo_new.png"),
    }

    html_string = render_to_string("emails/invoice_pdf.html", context)
    return HTML(string=html_string, base_url=settings.STATIC_ROOT).write_pdf()


import base64
import hashlib

# FIX #3: Replace insecure XOR cipher with Fernet authenticated symmetric encryption.
# The 32-byte key is derived from SECRET_KEY using SHA-256 — no extra env vars needed.

def _get_fernet():
    """Returns a Fernet instance keyed from the Django SECRET_KEY."""
    from cryptography.fernet import Fernet
    key_bytes = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def encrypt_password(plain_text):
    """Encrypt a plain-text password using Fernet (AES-128-CBC + HMAC-SHA256)."""
    if not plain_text:
        return None
    try:
        return _get_fernet().encrypt(plain_text.encode("utf-8")).decode("utf-8")
    except Exception:
        return None


def decrypt_password(cipher_text):
    """Decrypt a Fernet-encrypted password, with fallback for legacy XOR values."""
    if not cipher_text:
        return None
    try:
        return _get_fernet().decrypt(cipher_text.encode("utf-8")).decode("utf-8")
    except Exception:
        # Fallback: attempt old XOR decryption for values stored before this change.
        # After a migration period you can remove this fallback.
        try:
            key = settings.SECRET_KEY.encode("utf-8")
            decoded = base64.b64decode(cipher_text.encode("utf-8"))
            decrypted = bytes([c ^ key[i % len(key)] for i, c in enumerate(decoded)])
            return decrypted.decode("utf-8")
        except Exception:
            return cipher_text

