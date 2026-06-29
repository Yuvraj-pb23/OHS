import logging
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def attach_logo_inline(msg):
    from email.mime.image import MIMEImage
    import os
    from django.conf import settings
    try:
        logo_path = os.path.join(settings.BASE_DIR, "static", "img", "logo_new.png")
        if os.path.exists(logo_path):
            with open(logo_path, 'rb') as f:
                logo_data = f.read()
            mime_image = MIMEImage(logo_data)
            mime_image.add_header('Content-ID', '<logo>')
            mime_image.add_header('Content-Disposition', 'inline')
            msg.attach(mime_image)
    except Exception as e:
        logger.error(f"Failed to attach inline logo: {e}", exc_info=True)


def format_email_body(body_content):
    import re
    if not bool(re.search(r'<[a-zA-Z1-6]+[^>]*>', body_content)):
        from django.utils.html import linebreaks
        body_content = linebreaks(body_content)
    return body_content


def send_welcome_email(
    user,
    password,
    is_company_employee=False,
    organization_name=None,
    training_link=None,
    designation=None,
):
    """Send welcome email with login credentials asynchronously.
    """
    import threading

    class SimpleUser:
        def __init__(self, first_name, last_name, email):
            self.first_name = first_name
            self.last_name = last_name
            self.email = email
        def get_full_name(self):
            if self.first_name or self.last_name:
                return f"{self.first_name} {self.last_name}".strip()
            return self.email

    user_data = SimpleUser(user.first_name, user.last_name, user.email)

    def _send_thread():
        from home.models import EmailTemplate
        try:
            template = EmailTemplate.objects.filter(tier_key="EMPLOYEE_WELCOME").first()
        except Exception as db_err:
            logger.warning(f"DB access in thread failed: {db_err}")
            template = None

        site_base = training_link or f"{getattr(settings, 'SITE_URL', 'https://openhandsolutions.com')}/login"

        if template and template.subject and template.body:
            subject = template.subject
            body = template.body.format(
                name=user_data.first_name or user_data.email,
                company_name=organization_name or "Open Hand Solution",
                password=password,
                email=user_data.email,
                login_url=site_base,
                designation=designation or "Employee",
                training_link=site_base,
            )
        elif is_company_employee:
            subject = "Welcome to Open Hand Solution – Your Training Account"
            body = f"""Hello {user_data.first_name},

Welcome to Open Hand Solution!

Your training account has been created by {organization_name}. Here are your login credentials:

Name:               {user_data.get_full_name() or user_data.first_name}
Designation:        {designation or 'Employee'}
Email / Username:   {user_data.email}
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
            body = f"""Hello {user_data.first_name},

Welcome to Open Hand Solution!

Your account has been successfully created. Here are your login credentials:

Name:     {user_data.get_full_name() or user_data.first_name}
Email:    {user_data.email}
Password: {password}

Please keep these credentials safe and secure.

Best regards,
Open Hand Solution Team"""

        try:
            send_mail(
                subject,
                body,
                settings.DEFAULT_FROM_EMAIL,
                [user_data.email],
                fail_silently=False,
            )
        except Exception as e:
            logger.error(f"Error sending async welcome email: {e}")

    threading.Thread(target=_send_thread).start()
    return True


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
    if tier_key == "PAYMENT_VERIFIED":
        subject = "Payment confirmed — Welcome to Open Hand! Your login details inside"
        body_content = """<p>Dear {name},</p>

<p>Greetings from Open Hand Private Limited!</p>

<p>Thank you for your trust in us. We are delighted to confirm that your payment of {amount} has been successfully received. 🎉</p>

<p>You now have full access to the Open Hand Resource Platform — your one-stop portal for all things {type} compliance, training, and workplace safety.</p>

<h3 style="color:#0f172a; margin-top: 25px; margin-bottom: 10px;">📖 Login Instructions</h3>
<ol style="margin-bottom: 20px; font-size: 14px; color: #334155; padding-left: 20px;">
  <li style="margin-bottom: 10px;">Click the link below to set up your password and access your dashboard:<br>
    <a href="{setup_link}" style="display: inline-block; padding: 12px 24px; background-color: #6366f1; color: #ffffff !important; text-decoration: none; border-radius: 8px; font-weight: bold; margin-top: 10px; margin-bottom: 10px;">Create Password & Access Portal</a>
  </li>
  <li style="margin-bottom: 5px;">Once logged in, explore your dashboard and all available resources</li>
</ol>
<p style="color: #ef4444; font-weight: bold; font-size: 13px; margin-bottom: 25px;">⚠️ For security reasons, please change your password immediately after first login. Do not share your credentials.</p>

<h3 style="color:#0f172a; margin-top: 25px; margin-bottom: 10px;">📌 What You Get Access To</h3>
<p style="font-size: 14px; color: #334155;">Once logged in, your portal includes:</p>
<table border="1" cellpadding="8" style="border-collapse: collapse; border-color: #e2e8f0; width: 100%; margin-bottom: 20px;">
  <tr style="background-color: #f8fafc;">
    <th style="text-align: left; font-size: 13px; color: #64748b; width: 30%;">Feature</th>
    <th style="text-align: left; font-size: 13px; color: #64748b;">Description</th>
  </tr>
  <tr>
    <td style="font-size: 13px; font-weight: bold; color: #1e293b;">📊 HR Dashboard</td>
    <td style="font-size: 13px; color: #334155;">Track training progress, view compliance status, manage employee records</td>
  </tr>
  <tr>
    <td style="font-size: 13px; font-weight: bold; color: #1e293b;">🖼️ {type} Posters</td>
    <td style="font-size: 13px; color: #334155;">Ready-to-print posters for your office premises — edit text, add logo, and download</td>
  </tr>
  <tr>
    <td style="font-size: 13px; font-weight: bold; color: #1e293b;">📂 Unlimited Resources</td>
    <td style="font-size: 13px; color: #334155;">Training modules, presentations, handbooks, case studies, and more</td>
  </tr>
  <tr>
    <td style="font-size: 13px; font-weight: bold; color: #1e293b;">📝 Blogs & Newsletters</td>
    <td style="font-size: 13px; color: #334155;">Stay updated on {type} amendments, best practices, and industry insights</td>
  </tr>
  <tr>
    <td style="font-size: 13px; font-weight: bold; color: #1e293b;">📄 Forms & Documents</td>
    <td style="font-size: 13px; color: #334155;">Complaint forms, IC meeting templates, inquiry report formats, annual report templates</td>
  </tr>
  <tr>
    <td style="font-size: 13px; font-weight: bold; color: #1e293b;">👥 Manage Employees</td>
    <td style="font-size: 13px; color: #334155;">Add employees individually or upload an Excel sheet in bulk — assign trainings, track completion</td>
  </tr>
  <tr>
    <td style="font-size: 13px; font-weight: bold; color: #1e293b;">📋 IC Training Modules (as applicable)</td>
    <td style="font-size: 13px; color: #334155;">Access all materials for Internal Committee members — inquiry procedures, evidence handling, report writing</td>
  </tr>
  <tr>
    <td style="font-size: 13px; font-weight: bold; color: #1e293b;">📎 And much more!</td>
    <td style="font-size: 13px; color: #334155;">New resources added regularly</td>
  </tr>
</table>

<h3 style="color:#0f172a; margin-top: 25px; margin-bottom: 10px;">📞 Need Help? We're Here for You</h3>
<p style="font-size: 14px; color: #334155;">If you face any issues logging in, changing your password, or navigating the portal, please don't hesitate to reach out:</p>
<p style="font-size: 14px; font-weight: bold; color: #1e293b;">📞 +91- 99889 97555 &nbsp;&nbsp;|&nbsp;&nbsp; 📧 <a href="mailto:openhandpvtltd@gmail.com" style="color: #6366f1; text-decoration: none;">openhandpvtltd@gmail.com</a></p>
<p style="font-size: 13px; color: #64748b;">You can also reply to this email, and our support team will get back to you within 4–6 hours.</p>

<p>Once again, a heartfelt welcome to the Open Hand community. We are excited to be your partner in building a safer, compliant, and empowered workplace.</p>

<p>Warm regards,</p>

<p>Open Hand Private Limited<br>
<a href="mailto:openhandpvtltd@gmail.com" style="color: #6366f1; text-decoration: none;">openhandpvtltd@gmail.com</a> | <a href="https://openhandsolutions.com" style="color: #6366f1; text-decoration: none;">openhandsolutions.com</a> | <a href="https://in.linkedin.com/company/open-hand-solutions" style="color: #6366f1; text-decoration: none;">LinkedIn</a> | <a href="https://www.facebook.com/openhandsolutions/about/" style="color: #6366f1; text-decoration: none;">Facebook</a> | <a href="https://www.instagram.com/open_hand_solutions/" style="color: #6366f1; text-decoration: none;">Instagram</a></p>"""
    elif not template:
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

    amount = billing_data["total_amount"]
    amount_str = f"₹{amount:,.2f}"

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
        plan_str = "POSH Act" if registration_type == "POSH" else "POCSO Act"
        setup_link = f"{site_base}/subscription/company/{plan_str}/?setup_token={token}"

    # Placeholders replacement
    context = {
        "name": name,
        "company_name": company_name,
        "id": registration.id,
        "type": registration_type,
        "amount": amount_str,
        "invoice_url": invoice_url,
        "setup_link": setup_link,
    }

    # Dynamic placeholder replacement in body and subject
    for key, val in context.items():
        placeholder = f"{{{key}}}"
        subject = subject.replace(placeholder, str(val))
        body_content = body_content.replace(placeholder, str(val))

    body_content = format_email_body(body_content)

    # 3. Logo URL for Email
    logo_url = "https://openhandsolutions.com/static/img/logo_new.png"

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
    raw_recipients = [registration.email, getattr(settings, "SUPPORT_EMAIL", "openhandpvtltd@gmail.com")]
    recipients = [
        r for r in set(raw_recipients) if r and isinstance(r, str) and "@" in r
    ]

    try:
        msg = EmailMultiAlternatives(
            subject, text_content, settings.DEFAULT_FROM_EMAIL, recipients
        )
        msg.attach_alternative(html_content, "text/html")

        # 6. Attach Proforma Invoice PDF
        if tier_key != "PAYMENT_VERIFIED":
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

    body_content = format_email_body(body_content)

    # Get billing data and site URL to render using proforma_email.html
    billing_data = get_posh_billing_data(registration)
    logo_url = "https://openhandsolutions.com/static/img/logo_new.png"

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

    raw_recipients = [registration.email, getattr(settings, "SUPPORT_EMAIL", "openhandpvtltd@gmail.com")]
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


def send_interest_email(registration, registration_type="POSH", request=None):
    from django.core.mail import EmailMultiAlternatives
    from django.template.loader import render_to_string
    from django.utils.html import strip_tags
    from django.conf import settings
    from .utils import get_posh_billing_data, get_pocso_billing_data

    # 1. Fetch Billing Data
    if registration_type == "POSH":
        billing_data = get_posh_billing_data(registration)
    else:
        billing_data = get_pocso_billing_data(registration)

    if request:
        site_url = request.build_absolute_uri('/')[:-1]
    else:
        site_url = getattr(settings, "SITE_URL", "https://openhandsolutions.com")
    payment_link = f"{site_url}/billing/submit-payment/{registration.id}/"
    logo_url = "https://openhandsolutions.com/static/img/logo_new.png"

    # 2. Prepare Email Body content
    recipient_name = registration.contact_person or registration.company_name or "Valued Customer"

    subject = "Thank you for your interest in our services"

    body_content = f"""<p>Dear {recipient_name},</p>

<p>Greetings from Open Hand Private Limited!</p>

<p>We are truly pleased to have you here and thank you for taking the time to visit our website and register for POSH training. At Open Hand, we believe that every workplace deserves to be safe, respectful, and compliant — and we're honoured that you've chosen to partner with us on this important journey.</p>

<p>To confirm your booking, please click the link below to make the payment:<br>
➡ <a href="{payment_link}" style="display: inline-block; padding: 12px 24px; background-color: #6366f1; color: #ffffff !important; text-decoration: none; border-radius: 8px; font-weight: bold; margin-top: 10px; margin-bottom: 10px;">Pay Now – Secure Payment Link</a></p>

<p>Once the payment is received, our team will reach out to you within 24 hours to finalise the training schedule and share pre-training materials.</p>

<p><strong>OR</strong></p>

<p>📞 <strong>Prefer to discuss first? We're just a call away!</strong><br>
If you'd like to discuss the training modules, understand the content in more detail, or explore customisation options, feel free to call us at:<br>
<strong>+91- 99889 97555</strong></p>

<p>Once you complete the payment, you will be provided a user name and password to login to our Training module.</p>

<p>Once again, thank you for your trust and interest in us. We look forward to supporting your organisation in creating a safer, more empowered workplace.</p>

<p>Warm regards,</p>

<p>Open Hand Private Limited<br>
<a href="mailto:openhandpvtltd@gmail.com" style="color: #6366f1; text-decoration: none;">openhandpvtltd@gmail.com</a> | <a href="https://openhandsolutions.com" style="color: #6366f1; text-decoration: none;">openhandsolutions.com</a> | <a href="https://in.linkedin.com/company/open-hand-solutions" style="color: #6366f1; text-decoration: none;">LinkedIn</a> | <a href="https://www.facebook.com/openhandsolutions/about/" style="color: #6366f1; text-decoration: none;">Facebook</a> | <a href="https://www.instagram.com/open_hand_solutions/" style="color: #6366f1; text-decoration: none;">Instagram</a></p>"""

    body_content = format_email_body(body_content)

    # 3. Construct HTML content
    html_content = render_to_string(
        "emails/proforma_email.html",
        {
            "registration": registration,
            "billing_data": billing_data,
            "body_content": body_content,
            "registration_type": registration_type,
            "logo_url": logo_url,
        },
    )
    text_content = strip_tags(html_content)

    raw_recipients = [registration.email, getattr(settings, "SUPPORT_EMAIL", "openhandpvtltd@gmail.com")]
    recipients = [
        r for r in set(raw_recipients) if r and isinstance(r, str) and "@" in r
    ]

    try:
        msg = EmailMultiAlternatives(
            subject, text_content, settings.DEFAULT_FROM_EMAIL, recipients
        )
        msg.attach_alternative(html_content, "text/html")

        # Attach Proforma Invoice PDF
        from .utils import generate_proforma_invoice_pdf
        try:
            pdf_invoice = generate_proforma_invoice_pdf(
                registration, registration_type, "PAY_NOW"
            )
            msg.attach(
                f"Proforma_Invoice_{registration.id}.pdf",
                pdf_invoice,
                "application/pdf",
            )
        except Exception as pdf_err:
            logger.error(f"Error generating/attaching PDF: {pdf_err}", exc_info=True)

        msg.send()
        return True
    except Exception as e:
        logger.error(f"Error sending interest email: {e}", exc_info=True)
        return False


def send_payment_confirmed_email(registration, username, password, registration_type="POSH", request=None):
    from django.core.mail import EmailMultiAlternatives
    from django.template.loader import render_to_string
    from django.utils.html import strip_tags
    from django.conf import settings
    from .utils import get_posh_billing_data, get_pocso_billing_data

    # 1. Fetch Billing Data to get Total amount
    if registration_type == "POSH":
        billing_data = get_posh_billing_data(registration)
    else:
        billing_data = get_pocso_billing_data(registration)
    
    amount = billing_data["total_amount"]
    if request:
        site_url = request.build_absolute_uri('/')[:-1]
    else:
        site_url = getattr(settings, "SITE_URL", "https://openhandsolutions.com")
    portal_url = f"{site_url}/login"
    logo_url = "https://openhandsolutions.com/static/img/logo_new.png"

    recipient_name = registration.contact_person or registration.company_name or "Valued Customer"

    subject = "Payment confirmed — Welcome to Open Hand! Your login details inside"

    # We will build a beautiful HTML table for credentials and benefits inside the email.
    body_content = f"""<p>Dear {recipient_name},</p>

<p>Greetings from Open Hand Private Limited!</p>

<p>Thank you for your trust in us. We are delighted to confirm that your payment of ₹{amount:,.2f} has been successfully received. 🎉</p>

<p>You now have full access to the Open Hand Resource Platform — your one-stop portal for all things POSH compliance, training, and workplace safety.</p>

<h3 style="color:#0f172a; margin-top: 25px; margin-bottom: 10px;">🔐 Your Login Credentials</h3>
<table border="1" cellpadding="8" style="border-collapse: collapse; border-color: #e2e8f0; width: 100%; max-width: 500px; margin-bottom: 20px;">
  <tr style="background-color: #f8fafc;">
    <th style="text-align: left; font-size: 13px; color: #64748b;">Field</th>
    <th style="text-align: left; font-size: 13px; color: #64748b;">Details</th>
  </tr>
  <tr>
    <td style="font-size: 14px; font-weight: bold; color: #1e293b;">Portal URL</td>
    <td style="font-size: 14px;"><a href="{portal_url}" style="color: #6366f1; text-decoration: underline; font-weight: bold;">{portal_url}</a></td>
  </tr>
  <tr>
    <td style="font-size: 14px; font-weight: bold; color: #1e293b;">Username</td>
    <td style="font-size: 14px; font-family: monospace; color: #1e293b;">{username}</td>
  </tr>
  <tr>
    <td style="font-size: 14px; font-weight: bold; color: #1e293b;">Password</td>
    <td style="font-size: 14px; font-family: monospace; color: #1e293b;">{password}</td>
  </tr>
</table>

<h3 style="color:#0f172a; margin-top: 25px; margin-bottom: 10px;">📖 Login Instructions</h3>
<ol style="margin-bottom: 20px; font-size: 14px; color: #334155;">
  <li style="margin-bottom: 5px;">Visit <a href="{portal_url}" style="color: #6366f1; font-weight: bold;">{portal_url}</a></li>
  <li style="margin-bottom: 5px;">Enter your Username and Password (provided above)</li>
  <li style="margin-bottom: 5px;">You will be prompted to change your password on first login — choose a strong, memorable password</li>
  <li style="margin-bottom: 5px;">Once logged in, explore your dashboard and all available resources</li>
</ol>
<p style="color: #ef4444; font-weight: bold; font-size: 13px; margin-bottom: 25px;">⚠️ For security reasons, please change your password immediately after first login. Do not share your credentials.</p>

<h3 style="color:#0f172a; margin-top: 25px; margin-bottom: 10px;">📌 What You Get Access To</h3>
<p style="font-size: 14px; color: #334155;">Once logged in, your portal includes:</p>
<table border="1" cellpadding="8" style="border-collapse: collapse; border-color: #e2e8f0; width: 100%; margin-bottom: 20px;">
  <tr style="background-color: #f8fafc;">
    <th style="text-align: left; font-size: 13px; color: #64748b; width: 30%;">Feature</th>
    <th style="text-align: left; font-size: 13px; color: #64748b;">Description</th>
  </tr>
  <tr>
    <td style="font-size: 13px; font-weight: bold; color: #1e293b;">📊 HR Dashboard</td>
    <td style="font-size: 13px; color: #334155;">Track training progress, view compliance status, manage employee records</td>
  </tr>
  <tr>
    <td style="font-size: 13px; font-weight: bold; color: #1e293b;">🖼️ POSH Posters</td>
    <td style="font-size: 13px; color: #334155;">Ready-to-print posters for your office premises — edit text, add logo, and download</td>
  </tr>
  <tr>
    <td style="font-size: 13px; font-weight: bold; color: #1e293b;">📂 Unlimited Resources</td>
    <td style="font-size: 13px; color: #334155;">Training modules, presentations, handbooks, case studies, and more</td>
  </tr>
  <tr>
    <td style="font-size: 13px; font-weight: bold; color: #1e293b;">📝 Blogs & Newsletters</td>
    <td style="font-size: 13px; color: #334155;">Stay updated on POSH amendments, best practices, and industry insights</td>
  </tr>
  <tr>
    <td style="font-size: 13px; font-weight: bold; color: #1e293b;">📄 Forms & Documents</td>
    <td style="font-size: 13px; color: #334155;">Complaint forms, IC meeting templates, inquiry report formats, annual report templates</td>
  </tr>
  <tr>
    <td style="font-size: 13px; font-weight: bold; color: #1e293b;">👥 Manage Employees</td>
    <td style="font-size: 13px; color: #334155;">Add employees individually or upload an Excel sheet in bulk — assign trainings, track completion</td>
  </tr>
  <tr>
    <td style="font-size: 13px; font-weight: bold; color: #1e293b;">📋 IC Training Modules</td>
    <td style="font-size: 13px; color: #334155;">Access all materials for Internal Committee members — inquiry procedures, evidence handling, report writing</td>
  </tr>
  <tr>
    <td style="font-size: 13px; font-weight: bold; color: #1e293b;">📎 And much more!</td>
    <td style="font-size: 13px; color: #334155;">New resources added regularly</td>
  </tr>
</table>

<h3 style="color:#0f172a; margin-top: 25px; margin-bottom: 10px;">📞 Need Help? We're Here for You</h3>
<p style="font-size: 14px; color: #334155;">If you face any issues logging in, changing your password, or navigating the portal, please don't hesitate to reach out:</p>
<p style="font-size: 14px; font-weight: bold; color: #1e293b;">📞 +91- 99889 97555 &nbsp;&nbsp;|&nbsp;&nbsp; 📧 <a href="mailto:openhandpvtltd@gmail.com" style="color: #6366f1; text-decoration: none;">openhandpvtltd@gmail.com</a></p>
<p style="font-size: 13px; color: #64748b;">You can also reply to this email, and our support team will get back to you within 4–6 hours.</p>

<p>Once again, a heartfelt welcome to the Open Hand community. We are excited to be your partner in building a safer, compliant, and empowered workplace.</p>

<p>Warm regards,</p>

<p>Open Hand Private Limited<br>
<a href="mailto:openhandpvtltd@gmail.com" style="color: #6366f1; text-decoration: none;">openhandpvtltd@gmail.com</a> | <a href="https://openhandsolutions.com" style="color: #6366f1; text-decoration: none;">openhandsolutions.com</a> | <a href="https://in.linkedin.com/company/open-hand-solutions" style="color: #6366f1; text-decoration: none;">LinkedIn</a> | <a href="https://www.facebook.com/openhandsolutions/about/" style="color: #6366f1; text-decoration: none;">Facebook</a> | <a href="https://www.instagram.com/open_hand_solutions/" style="color: #6366f1; text-decoration: none;">Instagram</a></p>"""

    body_content = format_email_body(body_content)

    # We send this using proforma_email.html as the base container
    html_content = render_to_string(
        "emails/proforma_email.html",
        {
            "registration": registration,
            "billing_data": billing_data,
            "body_content": body_content,
            "registration_type": registration_type,
            "logo_url": logo_url,
        },
    )
    text_content = strip_tags(html_content)

    raw_recipients = [registration.email, getattr(settings, "SUPPORT_EMAIL", "openhandpvtltd@gmail.com")]
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
        print(f"DEBUG: Error sending welcome credentials email: {e}")
        return False

