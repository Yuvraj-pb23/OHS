from django.core.mail import send_mail
from django.conf import settings


def send_welcome_email(
    user, password, is_company_employee=False, organization_name=None
):
    """Send welcome email with login credentials"""
    subject = "Welcome to Open Hand Solution - Your Account Details"

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
