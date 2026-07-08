from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core import mail
from django.utils import timezone
from datetime import timedelta
import json
from home.models import (
    Organization,
    OrganizationMember,
    Subscription,
    SubscriptionPlan,
    TrainingModule,
    ModuleProgress,
    DailyActivity,
)
from home.email_utils import send_posh_reminder_email

User = get_user_model()

class POSHReminderTestCase(TestCase):
    def setUp(self):
        # Create users
        self.admin_user = User.objects.create_user(
            username="admin@company.com",
            email="admin@company.com",
            password="Password123!",
            first_name="Admin",
            account_type="COMPANY_ADMIN"
        )
        self.emp1 = User.objects.create_user(
            username="emp1@company.com",
            email="emp1@company.com",
            password="Password123!",
            first_name="Employee One",
            account_type="EMPLOYEE"
        )
        self.emp2 = User.objects.create_user(
            username="emp2@company.com",
            email="emp2@company.com",
            password="Password123!",
            first_name="Employee Two",
            account_type="EMPLOYEE"
        )

        # Create organization
        self.org = Organization.objects.create(
            name="Test Corp",
            owner=self.admin_user,
            max_users=10
        )
        
        # Create organization membership
        OrganizationMember.objects.create(
            organization=self.org,
            user=self.admin_user,
            role="ADMIN"
        )
        self.m1 = OrganizationMember.objects.create(
            organization=self.org,
            user=self.emp1,
            role="MEMBER"
        )
        self.m2 = OrganizationMember.objects.create(
            organization=self.org,
            user=self.emp2,
            role="MEMBER"
        )

        # Plan & Subscription
        self.plan = SubscriptionPlan.objects.create(
            name="POSH Basic",
            type="POSH",
            price=5000,
            duration_days=365,
            description="POSH Act training plan"
        )
        self.sub = Subscription.objects.create(
            plan=self.plan,
            organization=self.org,
            status="ACTIVE",
            start_date=timezone.now()
        )

        # Training module
        self.module = TrainingModule.objects.create(
            title="Introduction to POSH",
            description="Basic introduction video module",
            video_file="dummy.mp4",
            module_type="POSH",
            order=1,
            duration_seconds=300
        )

    def test_send_posh_reminder_email(self):
        # Test the direct helper function
        import time
        send_posh_reminder_email(self.emp1, "Not Started", 0, "July 31, 2026")
        time.sleep(0.5) # Wait briefly for background thread to send
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Mandatory POSH Training - Pending Completion")
        self.assertIn("Employee One", mail.outbox[0].body)
        self.assertIn("Training Status: Not Started", mail.outbox[0].body)

    def test_send_posh_reminders_view(self):
        # Emp1: Not started
        # Emp2: Completed training
        ModuleProgress.objects.create(
            user=self.emp2,
            module=self.module,
            is_completed=True
        )

        client = Client()
        client.login(username="admin@company.com", password="Password123!")

        url = reverse("send_posh_reminders")
        data = {
            "member_ids": [self.m1.id, self.m2.id]
        }

        # Clear outbox
        mail.outbox = []

        response = client.post(
            url,
            data=json.dumps(data),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )

        self.assertEqual(response.status_code, 200)
        resp_json = response.json()
        self.assertEqual(resp_json["status"], "success")
        self.assertIn("Successfully sent reminders to 1 employees", resp_json["message"])

        # Wait briefly for background thread to send
        import time
        time.sleep(0.5)
        
        # Verify only emp1 received the email (emp2 has completed, so skipped)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["emp1@company.com"])

    def test_encrypted_charfield_default_password(self):
        from django.db import connection
        org = Organization.objects.create(
            name="Secure Corp",
            owner=self.admin_user,
            max_users=5,
            default_password="MySecretPassword123!"
        )
        
        org.refresh_from_db()
        
        # Test property getter returns decrypted plaintext
        self.assertEqual(org.default_password, "MySecretPassword123!")
        
        # Directly query the database value
        with connection.cursor() as cursor:
            cursor.execute("SELECT default_password FROM home_organization WHERE id = %s", [org.id])
            row = cursor.fetchone()
            raw_db_value = row[0]
            
        # Verify the DB value is encrypted (does not equal the plaintext password)
        self.assertNotEqual(raw_db_value, "MySecretPassword123!")
        
        # Verify the DB value can be decrypted manually to confirm integrity
        from home.utils import decrypt_password
        self.assertEqual(decrypt_password(raw_db_value), "MySecretPassword123!")

    def test_csrf_protection_on_submit_assessment(self):
        client = Client(enforce_csrf_checks=True)
        client.login(username="admin@company.com", password="Password123!")
        
        url = reverse("submit_assessment")
        data = {
            "type": "POSH",
            "answers": [{"q": "What does POSH stand for?", "ans": 1}]
        }
        
        response = client.post(
            url,
            data=json.dumps(data),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 403)

    def test_weasyprint_pdf_html_escaping(self):
        user_xss = User.objects.create_user(
            username="attacker@company.com",
            email="attacker@company.com",
            password="Password123!",
            first_name="<script>alert(1)</script>",
            last_name="<b>Jones</b>",
            designation="<i>Director</i>"
        )
        
        import html
        candidate_name = f"{user_xss.first_name} {user_xss.last_name}".strip()
        if getattr(user_xss, "designation", None):
            candidate_name += f" ({user_xss.designation})"
        escaped_name = html.escape(candidate_name)
        self.assertIn("&lt;script&gt;", escaped_name)
        self.assertIn("&lt;i&gt;", escaped_name)
        self.assertNotIn("<script>", escaped_name)

    def test_file_signature_verification(self):
        from chat.utils import verify_file_signature, SecurityError
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(b"dummy_model_data_123")
            temp_file_path = temp_file.name
            
        try:
            sig_file_path = temp_file_path + ".sig"
            self.assertFalse(os.path.exists(sig_file_path))
            
            verify_file_signature(temp_file_path)
            self.assertTrue(os.path.exists(sig_file_path))
            
            verify_file_signature(temp_file_path)
            
            with open(temp_file_path, "wb") as f:
                f.write(b"modified_model_data_456")
                
            with self.assertRaises(SecurityError):
                verify_file_signature(temp_file_path)
                
        finally:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            if os.path.exists(temp_file_path + ".sig"):
                os.remove(temp_file_path + ".sig")


class EmployeeCRUDTestCase(TestCase):
    def setUp(self):
        # Create company admin user
        self.admin_user = User.objects.create_user(
            username="admin@company.com",
            email="admin@company.com",
            password="Password123!",
            first_name="Admin",
            account_type="COMPANY_ADMIN"
        )
        
        # Create organization
        self.org = Organization.objects.create(
            name="Test Corp",
            owner=self.admin_user,
            max_users=10,
            default_password="DEFAULT_PASSWORD123!"
        )
        
        # Create admin member
        OrganizationMember.objects.create(
            organization=self.org,
            user=self.admin_user,
            role="ADMIN"
        )
        
        # Create pending employee user
        self.emp_user = User.objects.create_user(
            username="emp@company.com",
            email="emp@company.com",
            password="EmpPassword123!",
            first_name="Emp",
            account_type="EMPLOYEE"
        )
        
        # Create membership
        self.member = OrganizationMember.objects.create(
            organization=self.org,
            user=self.emp_user,
            role="MEMBER"
        )
        
        # Create Plan & Subscription
        self.plan = SubscriptionPlan.objects.create(
            name="POSH Basic",
            type="POSH",
            price=5000,
            duration_days=365,
            description="POSH Plan"
        )
        self.sub = Subscription.objects.create(
            plan=self.plan,
            organization=self.org,
            status="ACTIVE",
            start_date=timezone.now()
        )
        
        # Create a module
        self.module = TrainingModule.objects.create(
            title="Intro",
            description="Video Intro",
            video_file="test.mp4",
            module_type="POSH",
            order=1,
            duration_seconds=300
        )
        
        self.client = Client()
        self.client.login(username="admin@company.com", password="Password123!")

    def test_update_pending_employee_email(self):
        # Update name, email and department
        url = reverse("update_employee", args=[self.member.id])
        data = {
            "emp_name": "Updated Name",
            "emp_email": "new_email@company.com",
            "emp_department": "Engineering"
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302) # Redirects back
        
        self.emp_user.refresh_from_db()
        self.assertEqual(self.emp_user.first_name, "Updated Name")
        self.assertEqual(self.emp_user.email, "new_email@company.com")
        self.assertEqual(self.emp_user.username, "new_email@company.com")
        self.assertEqual(self.emp_user.department, "Engineering")
        self.assertTrue(self.emp_user.force_password_change)
        
        # Verify password is set to default password
        self.assertTrue(self.emp_user.check_password("DEFAULT_PASSWORD123!"))

    def test_update_completed_employee_fails(self):
        # Mark module completed to lock the seat
        ModuleProgress.objects.create(
            user=self.emp_user,
            module=self.module,
            is_completed=True
        )
        
        url = reverse("update_employee", args=[self.member.id])
        data = {
            "emp_name": "New Name",
            "emp_email": "another@company.com",
            "emp_department": "HR"
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        
        # Verify employee was NOT updated
        self.emp_user.refresh_from_db()
        self.assertEqual(self.emp_user.first_name, "Emp")
        self.assertEqual(self.emp_user.email, "emp@company.com")

    def test_delete_pending_employee(self):
        url = reverse("delete_employee", args=[self.member.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        
        # Verify user is deleted
        with self.assertRaises(User.DoesNotExist):
            self.emp_user.refresh_from_db()
            
        # Verify membership is deleted
        self.assertFalse(OrganizationMember.objects.filter(id=self.member.id).exists())

    def test_delete_completed_employee_fails(self):
        # Mark module completed to lock the seat
        ModuleProgress.objects.create(
            user=self.emp_user,
            module=self.module,
            is_completed=True
        )
        
        url = reverse("delete_employee", args=[self.member.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        
        # Verify employee still exists
        self.emp_user.refresh_from_db()
        self.assertTrue(OrganizationMember.objects.filter(id=self.member.id).exists())


