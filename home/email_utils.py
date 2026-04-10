from django.core.mail import send_mail
from django.conf import settings


def send_welcome_email(user, password, is_company_employee=False, organization_name=None):
    """Send welcome email with login credentials"""
    subject = 'Welcome to Open Hand Solution - Your Account Details'
    
    if is_company_employee:
        message = f"""
Hello {user.first_name},

Welcome to Open Hand Solution!

Your account has been created by {organization_name}. Here are your login credentials:

Name: {user.get_full_name() or user.first_name}
Email/Username: {user.email}
Temporary Password: {password}

IMPORTANT: For security reasons, you will be required to change your password upon first login.

Please visit your training portal and login with these credentials.

If you have any questions, please contact your HR department or reply to this email.

Best regards,
Open Hand Solution Team
        """
    else:
        message = f"""
Hello {user.first_name},

Welcome to Open Hand Solution!

Your account has been successfully created. Here are your login credentials:

Name: {user.get_full_name() or user.first_name}
Email/Username: {user.email}
Password: {password}

Please keep these credentials safe and secure.

You can now login and access your training materials.

If you have any questions, please feel free to reply to this email.

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


def send_password_change_email(user):
    """Send email notification when password is changed"""
    subject = 'Password Changed Successfully - Open Hand Solution'
    
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

def send_tiered_email(registration, tier_key, registration_type='POSH'):
    """
    Send an automated email based on the selected payment tier.
    Includes registration details and a breakdown of the proforma invoice.
    """
    from .models import EmailTemplate
    from django.template.loader import render_to_string
    from django.utils.html import strip_tags
    from django.core.mail import EmailMultiAlternatives
    from email.mime.image import MIMEImage
    from pathlib import Path
    import os

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
    company_name = getattr(registration, 'company_name', '') or getattr(registration, 'school_name', '') or "Valued Customer"
    name = (
        getattr(registration, 'contact_person', '') or 
        getattr(registration, 'person_name', '') or 
        company_name
    )
    if not name or name == "Valued Customer":
        name = "Valued Customer"
    
    # Calculate amount for placeholder
    from .utils import get_posh_billing_data, get_pocso_billing_data
    if registration_type == 'POSH':
        billing_data = get_posh_billing_data(registration)
    else:
        billing_data = get_pocso_billing_data(registration)
    
    invoice_url = f"https://openhandsolutions.com/billing/" # Link to billing portal

    # Placeholders replacement
    context = {
        'name': name,
        'company_name': company_name,
        'id': registration.id,
        'type': registration_type,
        # amount removed as per user request
        'invoice_url': invoice_url,
    }
    
    # Dynamic placeholder replacement in body and subject
    for key, val in context.items():
        placeholder = f"{{{key}}}"
        subject = subject.replace(placeholder, str(val))
        body_content = body_content.replace(placeholder, str(val))

    # 3. Generate Invoice HTML for Email Body
    # (Billing data already calculated above)

    # 4. Construct Final HTML Email
    html_content = render_to_string('emails/proforma_email.html', {
        'registration': registration,
        'billing_data': billing_data,
        'body_content': body_content,
        'registration_type': registration_type,
        'tier_key': tier_key,
    })
    text_content = strip_tags(html_content)

    # 5. Send Email
    raw_recipients = [registration.email, 'openhandpvtltd@gmail.com']
    recipients = [r for r in set(raw_recipients) if r and isinstance(r, str) and '@' in r]
    
    try:
        msg = EmailMultiAlternatives(
            subject,
            text_content,
            settings.DEFAULT_FROM_EMAIL,
            recipients
        )
        msg.attach_alternative(html_content, "text/html")

        # 6. Attach Proforma Invoice PDF
        from .utils import generate_proforma_invoice_pdf
        try:
            pdf_invoice = generate_proforma_invoice_pdf(registration, registration_type, tier_key)
            msg.attach(f"Proforma_Invoice_{registration.id}.pdf", pdf_invoice, 'application/pdf')
        except Exception as pdf_err:
            print(f"DEBUG: Error generating/attaching PDF: {pdf_err}")
            
        msg.send()
        return True
    except Exception as e:
        print(f"DEBUG: CRITICAL error sending tiered email: {e}")
        return False
