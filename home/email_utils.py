from django.conf import settings
from django.core.mail import send_mail


def send_welcome_email(
    user,
    password,
    is_company_employee=False,
    organization_name=None,
    training_link=None,
    designation=None,
):
    """Send welcome email with login credentials.
    Uses the EMPLOYEE_WELCOME EmailTemplate from DB if available, otherwise falls back to default.
    """
    from home.models import EmailTemplate

    template = EmailTemplate.objects.filter(tier_key="EMPLOYEE_WELCOME").first()

    site_base = training_link or f"{getattr(settings, 'SITE_URL', 'https://openhandsolutions.com')}/login"

    if template and template.subject and template.body:
        subject = template.subject
        body = template.body.format(
            name=user.first_name or user.email,
            company_name=organization_name or "Open Hand Solution",
            password=password,
            email=user.email,
            login_url=site_base,
            designation=designation or "Employee",
            training_link=site_base,
        )
    elif is_company_employee:
        subject = "Welcome to Open Hand Solution – Your Training Account"
        body = f"""Hello {user.first_name},

Welcome to Open Hand Solution!

Your training account has been created by {organization_name}. Here are your login credentials:

Name:               {user.get_full_name() or user.first_name}
Designation:        {designation or 'Employee'}
Email / Username:   {user.email}
Temporary Password: {password}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔗 Access your POSH Training Portal here:
{site_base}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

IMPORTANT: You will be required to change your password upon first login.

If you have any questions, please contact your HR department.

Best regards,
Open Hand Solution Team"""
    else:
        subject = "Welcome to Open Hand Solution – Your Account Details"
        body = f"""Hello {user.first_name},

Welcome to Open Hand Solution!

Your account has been successfully created. Here are your login credentials:

Name:     {user.get_full_name() or user.first_name}
Email:    {user.email}
Password: {password}

Please keep these credentials safe and secure.

Best regards,
Open Hand Solution Team"""

    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


def send_password_change_email(user):
    """Send email notification when password is changed"""
    subject = "Password Changed Successfully - Open Hand Solution"

    message = f"""
Hello {user.first_name},

This is a confirmation that your password has been changed successfully.

If you did not make this change, please contact your administrator immediately or reply to this email.

Account Details:
Name: {user.get_full_name() or user.first_name}
Email: {user.email}
Time: Just now

Best regards,
Open Hand Solution Team
    """

    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


def send_tiered_email(registration, tier_key, registration_type="POSH"):
    """
    Send an automated email based on the selected payment tier.
    Includes registration details and a breakdown of the proforma invoice.
    """
    from django.core.mail import EmailMultiAlternatives
    from django.template.loader import render_to_string
    from django.utils.html import strip_tags

    from .models import EmailTemplate

    # 1. Fetch Template
    template = EmailTemplate.objects.filter(tier_key=tier_key).first()
    if not template:
        # Fallback to basic subject if no template found
        subject = f"Registration Update - {registration_type} Compliance"
        body_content = f"Thank you for registering for {registration_type} compliance."
    else:
        subject = template.subject
        body_content = template.body

    # 2. Context for Placeholders
    company_name = (
        getattr(registration, "company_name", "")
        or getattr(registration, "school_name", "")
        or "Valued Customer"
    )
    name = (
        getattr(registration, "contact_person", "")
        or getattr(registration, "person_name", "")
        or company_name
    )
    if not name or name == "Valued Customer":
        name = "Valued Customer"

    # Calculate amount for placeholder
    from .utils import get_pocso_billing_data, get_posh_billing_data

    if registration_type == "POSH":
        billing_data = get_posh_billing_data(registration)
    else:
        billing_data = get_pocso_billing_data(registration)

    site_url = getattr(settings, "SITE_URL", "https://openhandsolutions.com")
    invoice_url = f"{site_url}/billing/"  # Link to billing portal

    # Generate signed setup link for PAYMENT_VERIFIED emails
    setup_link = ""
    if tier_key == "PAYMENT_VERIFIED":
        from django.conf import settings as django_settings
        from django.core import signing

        token = signing.dumps(
            {"email": registration.email, "reg_id": registration.id},
            salt="posh-admin-setup",
        )
        site_base = getattr(
            django_settings, "SITE_URL", "https://openhandsolutions.com"
        )
        setup_link = f"{site_base}/subscription/company/POSH%20Act/?setup_token={token}"

    # Placeholders replacement
    context = {
        "name": name,
        "company_name": company_name,
        "id": registration.id,
        "type": registration_type,
        # amount removed as per user request
        "invoice_url": invoice_url,
        "setup_link": setup_link,
    }

    # Dynamic placeholder replacement in body and subject
    for key, val in context.items():
        placeholder = f"{{{key}}}"
        subject = subject.replace(placeholder, str(val))
        body_content = body_content.replace(placeholder, str(val))

    # 3. Logo URL for Email
    logo_url = f"{site_url}/static/img/logo_new.png"

    # 3. Generate Invoice HTML for Email Body
    # (Billing data already calculated above)

    # 4. Construct Final HTML Email
    html_content = render_to_string(
        "emails/proforma_email.html",
        {
            "registration": registration,
            "billing_data": billing_data,
            "body_content": body_content,
            "registration_type": registration_type,
            "tier_key": tier_key,
            "logo_url": logo_url,
        },
    )
    text_content = strip_tags(html_content)

    # 5. Send Email
    raw_recipients = [registration.email, "openhandpvtltd@gmail.com"]
    recipients = [
        r for r in set(raw_recipients) if r and isinstance(r, str) and "@" in r
    ]

    try:
        msg = EmailMultiAlternatives(
            subject, text_content, settings.DEFAULT_FROM_EMAIL, recipients
        )
        msg.attach_alternative(html_content, "text/html")

        # 6. Attach Proforma Invoice PDF
        from .utils import generate_proforma_invoice_pdf

        try:
            pdf_invoice = generate_proforma_invoice_pdf(
                registration, registration_type, tier_key
            )
            msg.attach(
                f"Proforma_Invoice_{registration.id}.pdf",
                pdf_invoice,
                "application/pdf",
            )
        except Exception as pdf_err:
            print(f"DEBUG: Error generating/attaching PDF: {pdf_err}")

        msg.send()
        return True
    except Exception as e:
        print(f"DEBUG: CRITICAL error sending tiered email: {e}")
        return False


def send_payment_rejected_email(registration):
    """
    Send an email when a payment is rejected by the accounts department for the POSH queue.
    """
    from django.core.mail import EmailMultiAlternatives
    from django.template.loader import render_to_string
    from django.utils.html import strip_tags
    from django.conf import settings
    from .utils import get_posh_billing_data

    hr_name = registration.contact_person or "HR Team"
    subject = "Payment Rejected - POSH Act Compliance Training Program"
    
    body_content = f"""Dear {hr_name},

Thank you for your interest in the POSH Act Compliance Training Program and for completing the registration process.

We would like to inform you that we are currently unable to confirm your nomination/registration as we have not yet received the payment. There may have been a processing delay or an issue with the transaction.

We request you to kindly verify the payment status and share the transaction details or proof of payment with us. Once the payment is received and verified, we will be happy to confirm your registration and share the joining details.

Thank you for your cooperation. We look forward to your participation.

Warm regards,

Open Hand Solutions"""

    # Get billing data and site URL to render using proforma_email.html
    billing_data = get_posh_billing_data(registration)
    site_url = getattr(settings, "SITE_URL", "https://openhandsolutions.com")
    logo_url = f"{site_url}/static/img/logo_new.png"

    # Construct HTML email
    html_content = render_to_string(
        "emails/proforma_email.html",
        {
            "registration": registration,
            "billing_data": billing_data,
            "body_content": body_content,
            "registration_type": "POSH",
            "tier_key": "PAYMENT_REJECTED",
            "logo_url": logo_url,
        },
    )
    text_content = strip_tags(html_content)

    raw_recipients = [registration.email, "openhandpvtltd@gmail.com"]
    recipients = [
        r for r in set(raw_recipients) if r and isinstance(r, str) and "@" in r
    ]

    try:
        msg = EmailMultiAlternatives(
            subject, text_content, settings.DEFAULT_FROM_EMAIL, recipients
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send()
        return True
    except Exception as e:
        print(f"DEBUG: Error sending payment rejection email: {e}")
        return False

