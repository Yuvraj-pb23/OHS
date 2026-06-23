from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


# 1. Custom User Model
class User(AbstractUser):
    # AbstractUser has username, email, password, first_name, date_joined
    phone = models.CharField(max_length=15, blank=True, null=True)
    department = models.CharField(max_length=100, blank=True, null=True)

    # NEW: Distinct types for data separation
    USER_TYPES = (
        ("INDIVIDUAL", "Individual Subscriber"),
        ("COMPANY_ADMIN", "Company Admin"),
        ("EMPLOYEE", "Company Employee"),
        ("ACCOUNTS", "Accounts Department"),
    )
    account_type = models.CharField(
        max_length=20, choices=USER_TYPES, default="INDIVIDUAL"
    )

    # Unique user ID
    user_id = models.CharField(max_length=20, unique=True, blank=True, null=True)

    # Job designation / title
    designation = models.CharField(max_length=150, blank=True, null=True)

    # Force password change on first login for company employees
    force_password_change = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.username} ({self.account_type})"

    def generate_user_id(self, organization=None):
        """Generate unique ID based on user type and subscription"""
        # Determine prefix based on account type and subscription
        if self.account_type == "INDIVIDUAL":
            # Check subscription type
            subscription = Subscription.objects.filter(user=self).first()
            if subscription:
                if subscription.plan.type in ["POSH", "BOTH"]:
                    prefix = "PI"  # POSH Individual
                else:
                    prefix = "POI"  # POCSO Individual
            else:
                prefix = "PI"  # Default to POSH
        elif self.account_type in ["EMPLOYEE", "COMPANY_ADMIN"]:
            # If organization is passed directly, use it (avoids querying unsaved relationships)
            if organization:
                org_subscription = Subscription.objects.filter(
                    organization=organization, status="ACTIVE"
                ).first()
                if org_subscription:
                    if org_subscription.plan.type in ["POSH", "BOTH"]:
                        prefix = "PC"  # POSH Company
                    else:
                        prefix = "POC"  # POCSO Company
                else:
                    prefix = "PC"  # Default to POSH Company
            else:
                # Fallback to querying membership
                membership = OrganizationMember.objects.filter(user=self).first()
                if membership:
                    org_subscription = Subscription.objects.filter(
                        organization=membership.organization, status="ACTIVE"
                    ).first()
                    if org_subscription:
                        if org_subscription.plan.type in ["POSH", "BOTH"]:
                            prefix = "PC"  # POSH Company
                        else:
                            prefix = "POC"  # POCSO Company
                    else:
                        prefix = "PC"  # Default to POSH Company
                else:
                    prefix = "PC"  # Default
        else:
            prefix = "PI"  # Fallback

        # Get the last user with this prefix
        last_user = (
            User.objects.filter(user_id__startswith=prefix).order_by("-id").first()
        )

        if last_user and last_user.user_id:
            # Extract number from last ID and increment
            try:
                last_number = int(last_user.user_id[len(prefix):])
                new_number = last_number + 1
            except (ValueError, IndexError):
                new_number = 1
        else:
            new_number = 1

        # Generate new ID with zero-padding
        return f"{prefix}{new_number:05d}"  # e.g., PI00001, PC00123

    def save(self, *args, **kwargs):
        # Don't auto-generate user_id in save() - it's set explicitly in views
        # to avoid issues with unsaved relationships
        super().save(*args, **kwargs)


# 2. Subscription Plan
class SubscriptionPlan(models.Model):
    PLAN_TYPES = (
        ("POSH", "POSH Act"),
        ("POCSO", "POCSO Act"),
        ("BOTH", "POSH & POCSO"),
    )
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=10, choices=PLAN_TYPES, default="POSH")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration_days = models.IntegerField(
        help_text="Duration in days (e.g., 365 for 1 year)"
    )
    description = models.TextField()
    is_active = models.BooleanField(default=True)  # To hide old plans

    def __str__(self):
        return f"{self.name} - ₹{self.price}"


# 3. Organization
class Organization(models.Model):
    ORG_TYPE_CHOICES = (
        ("CORPORATE", "Corporate"),
        ("SCHOOL", "School"),
    )
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="owned_organizations"
    )
    organization_type = models.CharField(
        max_length=20, choices=ORG_TYPE_CHOICES, default="CORPORATE"
    )
    max_users = models.IntegerField(default=10)
    created_at = models.DateTimeField(auto_now_add=True)

    # Default password for employees
    default_password = models.CharField(max_length=50, blank=True, null=True)
    logo = models.ImageField(upload_to="company_logos/", null=True, blank=True)

    # Logo customization (as percentages 0-100)
    logo_x = models.FloatField(default=2.0)
    logo_y = models.FloatField(default=2.0)
    logo_width = models.FloatField(default=15.0)  # percentage of poster width

    def __str__(self):
        return self.name

    """
    Generate default password:
    First 4 letters of company + secure random number + special character
    """

    def generate_default_password(self):

        import secrets

        # Get first 4 alphanumeric characters of company name
        company_prefix = "".join(c for c in self.name if c.isalnum())[:4].upper()

        if len(company_prefix) < 4:
            company_prefix = company_prefix.ljust(4, "X")

        # Secure random 4-digit number
        random_number = secrets.randbelow(9000) + 1000

        # Secure random special character
        special_chars = "@#$%&*!"
        special_char = secrets.choice(special_chars)

        return f"{company_prefix}{random_number}{special_char}"


# 4. Subscription
class Subscription(models.Model):
    STATUS_CHOICES = (
        ("ACTIVE", "Active"),
        ("EXPIRED", "Expired"),
        ("PENDING", "Pending Payment"),
    )

    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE)

    # Linked to EITHER User OR Organization
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subscriptions",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subscriptions",
    )

    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")

    class Meta:
        # DB Constraint: A sub must belong to User OR Org, never both, never neither
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gt=models.F("start_date")),
                name="subscription_owner_constraint",
            )
        ]

    def save(self, *args, **kwargs):
        if not self.end_date:
            self.end_date = self.start_date + timedelta(days=self.plan.duration_days)
        super().save(*args, **kwargs)

    @property
    def is_active(self):
        return self.status == "ACTIVE" and self.end_date > timezone.now()


# 5. Organization Members
class OrganizationMember(models.Model):
    ROLE_CHOICES = (
        ("ADMIN", "Admin"),
        ("MEMBER", "Member"),
    )
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="MEMBER")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("organization", "user")  # User can't be in same org twice


# 6. Invitations
class Invitation(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    email = models.EmailField()
    token = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20, default="PENDING")
    expires_at = models.DateTimeField()


# 7. Payment History
class Payment(models.Model):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_id = models.CharField(max_length=100)
    status = models.CharField(max_length=20, default="SUCCESS")
    created_at = models.DateTimeField(auto_now_add=True)


# 8. Training Module (Videos/Content)
class TrainingModule(models.Model):
    MODULE_TYPES = (
        ("POSH", "POSH Act"),
        ("POCSO", "POCSO Act"),
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    video_file = models.FileField(upload_to="training_videos/", blank=True, null=True)
    ppt_file = models.FileField(upload_to="training_ppts/", blank=True, null=True)
    thumbnail = models.ImageField(
        upload_to="training_thumbnails/", blank=True, null=True
    )
    module_type = models.CharField(max_length=10, choices=MODULE_TYPES, default="POSH")
    order = models.IntegerField(default=1)  # To sequence modules 1, 2, 3...
    duration_seconds = models.IntegerField(
        default=0, help_text="Duration in seconds"
    )  # Optional, helpful for progress calc

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.module_type} - {self.order}. {self.title}"


# 9. Module Progress (Per User)
class ModuleProgress(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="module_progress"
    )
    module = models.ForeignKey(TrainingModule, on_delete=models.CASCADE)
    is_completed = models.BooleanField(default=False)
    last_position = models.FloatField(default=0.0, help_text="Last watched position in seconds")
    timestamp = models.DateTimeField(auto_now=True)  # Last watched

    class Meta:
        unique_together = ("user", "module")

    def __str__(self):
        return f"{self.user.username} - {self.module.title} ({'Done' if self.is_completed else 'In Progress'})"


# 10. Daily Activity (For Charts)
class DailyActivity(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="daily_activity"
    )
    date = models.DateField(default=timezone.now)
    minutes_watched = models.IntegerField(default=0)
    seconds_watched = models.IntegerField(default=0)

    class Meta:
        unique_together = ("user", "date")

    def __str__(self):
        return f"{self.user.username} - {self.date} - {self.minutes_watched} min"


# 11. Assessment Progress (Final Quiz)
class AssessmentProgress(models.Model):
    ASSESSMENT_TYPES = (
        ("POSH", "POSH Act"),
        ("POCSO", "POCSO Act"),
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="assessment_progress"
    )
    assessment_type = models.CharField(max_length=10, choices=ASSESSMENT_TYPES)
    is_passed = models.BooleanField(default=False)
    score = models.IntegerField(default=0)
    timestamp = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "assessment_type")


# 12. POSH Registration Form Data
class POSHRegistration(models.Model):
    # Basic Company Details
    company_name = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    contact_person = models.CharField(max_length=255, blank=True, null=True)
    designation = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    website = models.URLField(blank=True, null=True)

    # Company Information
    employee_count = models.IntegerField()
    trained_employee_count = models.IntegerField()
    last_training_year = models.CharField(max_length=20, blank=True, null=True)

    TRAINING_TYPE_CHOICES = [
        ("OFFLINE", "Offline"),
        ("VIRTUAL", "Virtual"),
        ("E_LEARNING", "E-learning"),
    ]
    training_type = models.CharField(
        max_length=20, choices=TRAINING_TYPE_CHOICES, null=True, blank=True
    )

    # Compliance Details
    has_posh_policy = models.BooleanField(default=False)
    has_ic = models.BooleanField(default=False)

    # Conditional IC Fields
    require_ic_training = models.BooleanField(default=False)
    requested_ic_training_mode = models.CharField(
        max_length=20, null=True, blank=True
    )  # EXPERT_LED, ONLINE
    requested_expert_led_type = models.CharField(
        max_length=20, null=True, blank=True
    )  # PHYSICAL, VIRTUAL
    ic_specialized_training = models.BooleanField(default=False)
    ic_last_training_year = models.CharField(max_length=20, null=True, blank=True)
    ic_training_mode = models.CharField(
        max_length=20, choices=TRAINING_TYPE_CHOICES, null=True, blank=True
    )

    external_member_support = models.BooleanField(default=False)
    require_external_member_support = models.BooleanField(default=False)
    she_box_registered = models.BooleanField(default=False)

    # Conditional SHE Box Field
    nodal_officer_appointed = models.BooleanField(default=False)
    require_nodal_officer_support = models.BooleanField(default=False)

    annual_report_submitted = models.BooleanField(default=False)

    # Payment Tracking
    payment_screenshot = models.ImageField(
        upload_to="posh_payments/", null=True, blank=True
    )
    PAYMENT_STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("SUBMITTED", "Submitted"),
        ("VERIFIED", "Verified"),
        ("REJECTED", "Rejected"),
    ]
    payment_status = models.CharField(
        max_length=20, choices=PAYMENT_STATUS_CHOICES, default="PENDING"
    )

    # User association
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="posh_registrations",
    )
    is_paid = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.company_name} - {self.created_at.date()}"


# 13. POSH Pricing Configuration (managed by Accounts Dept)
class POSHPricingConfig(models.Model):
    # Base platform fee
    base_platform_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=5000.00
    )
    gst_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=18.00, help_text="Global GST percentage"
    )

    # Per-employee pricing tiers
    price_tier_0_max = models.IntegerField(
        default=10, help_text="Max employees for Tier 1 (1-10)"
    )
    price_tier_0_rate = models.DecimalField(
        max_digits=8, decimal_places=2, default=200.00
    )

    price_tier_1_max = models.IntegerField(
        default=25, help_text="Max employees for Tier 2"
    )
    price_tier_1_rate = models.DecimalField(
        max_digits=8, decimal_places=2, default=163.00
    )

    price_tier_2_max = models.IntegerField(
        default=100, help_text="Max employees for Tier 3"
    )
    price_tier_2_rate = models.DecimalField(
        max_digits=8, decimal_places=2, default=154.00
    )

    price_tier_3_max = models.IntegerField(
        default=200, help_text="Max employees for Tier 4 (101-200)"
    )
    price_tier_3_rate = models.DecimalField(
        max_digits=8, decimal_places=2, default=145.00
    )

    price_tier_4_max = models.IntegerField(
        default=500, help_text="Max employees for Tier 5 (201-500)"
    )
    price_tier_4_rate = models.DecimalField(
        max_digits=8, decimal_places=2, default=127.00
    )

    # Compliance add-on fees per tier (t0=Tier1 1-10, t1=Tier2 11-25, t2=Tier3 26-100, t3=Tier4 101-200)
    # No POSH Policy
    fee_no_posh_policy_t0 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_no_posh_policy_t1 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_no_posh_policy_t2 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_no_posh_policy_t3 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_no_posh_policy_t4 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    # No IC
    fee_no_ic_t0 = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    fee_no_ic_t1 = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    fee_no_ic_t2 = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    fee_no_ic_t3 = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    fee_no_ic_t4 = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    # External Member Support Required
    fee_no_external_member_t0 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_no_external_member_t1 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_no_external_member_t2 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_no_external_member_t3 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_no_external_member_t4 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    # Not SHe Box Registered
    fee_not_she_box_t0 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_not_she_box_t1 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_not_she_box_t2 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_not_she_box_t3 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_not_she_box_t4 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )

    # IC No Specialized Training (Deprecated in favor of historical_other)
    fee_ic_no_specialized_training_t0 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_no_specialized_training_t1 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_no_specialized_training_t2 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_no_specialized_training_t3 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_no_specialized_training_t4 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )

    # IC Specialized Training Outdated (Deprecated in favor of historical_21_23)
    fee_ic_training_outdated_t0 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_training_outdated_t1 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_training_outdated_t2 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_training_outdated_t3 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_training_outdated_t4 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )

    # NEW GRANULAR IC PRICING
    # Requested Mode: Online
    fee_ic_requested_online_t0 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_requested_online_t1 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_requested_online_t2 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_requested_online_t3 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_requested_online_t4 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )

    # Requested Mode: Physical
    fee_ic_requested_physical_t0 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_requested_physical_t1 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_requested_physical_t2 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_requested_physical_t3 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_requested_physical_t4 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )

    # Requested Mode: Virtual
    fee_ic_requested_virtual_t0 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_requested_virtual_t1 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_requested_virtual_t2 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_requested_virtual_t3 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_requested_virtual_t4 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )

    # Historical: 2021-2023
    fee_ic_history_21_23_t0 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_history_21_23_t1 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_history_21_23_t2 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_history_21_23_t3 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_history_21_23_t4 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )

    # Historical: 2024-2025 (Refresher)
    fee_ic_history_24_25_t0 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_history_24_25_t1 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_history_24_25_t2 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_history_24_25_t3 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_history_24_25_t4 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )

    # Historical: Other (Full IC Training)
    fee_ic_history_other_t0 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_history_other_t1 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_history_other_t2 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_history_other_t3 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_ic_history_other_t4 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    # Requires Nodal Officer Support
    fee_nodal_officer_t0 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_nodal_officer_t1 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_nodal_officer_t2 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_nodal_officer_t3 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    fee_nodal_officer_t4 = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )

    # Metadata
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(
        default=True, help_text="Only ONE active config should exist"
    )

    class Meta:
        verbose_name = "POSH Pricing Configuration"
        verbose_name_plural = "POSH Pricing Configurations"

    def __str__(self):
        return f"Pricing Config (Updated: {self.updated_at.date()}) - Active: {self.is_active}"


# 14. POCSO Registration Form Data
class POCSORegistration(models.Model):
    # Basic Details
    person_name = models.CharField(max_length=255)
    designation = models.CharField(max_length=100)
    school_name = models.CharField(max_length=255)

    # Counts
    students_count = models.IntegerField(default=0)
    teachers_count = models.IntegerField(default=0)
    non_teaching_staff_count = models.IntegerField(default=0)

    # Location & Contact
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    address = models.TextField()
    pin_code = models.CharField(max_length=20)
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    contact_person = models.CharField(max_length=255, blank=True, null=True)

    # POCSO Module
    has_policy = models.BooleanField(default=False)
    has_committee = models.BooleanField(default=False)

    # Training details
    teaching_staff_trained = models.BooleanField(default=False)
    TRAINING_MODE_CHOICES = [
        ("E_LEARNING", "E-Learning"),
        ("OFFLINE", "Offline"),
        ("ONLINE", "Online"),
    ]
    teaching_training_mode = models.CharField(
        max_length=20, choices=TRAINING_MODE_CHOICES, null=True, blank=True
    )

    non_teaching_staff_trained = models.BooleanField(default=False)
    non_teaching_training_mode = models.CharField(
        max_length=20, choices=TRAINING_MODE_CHOICES, null=True, blank=True
    )

    # Vendor & Transport
    vendors_access_premises = models.BooleanField(default=False)
    has_vendor_policy = models.BooleanField(default=False)
    has_transport = models.BooleanField(default=False)
    aware_of_transport_policy = models.BooleanField(default=False)

    # Student Training
    students_trained = models.BooleanField(default=False)

    # Payment Tracking
    payment_screenshot = models.ImageField(
        upload_to="pocso_payments/", null=True, blank=True
    )
    PAYMENT_STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("SUBMITTED", "Submitted"),
        ("VERIFIED", "Verified"),
        ("REJECTED", "Rejected"),
    ]
    payment_status = models.CharField(
        max_length=20, choices=PAYMENT_STATUS_CHOICES, default="PENDING"
    )

    # User association
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pocso_registrations",
    )
    is_paid = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"POCSO: {self.school_name} - {self.created_at.date()}"


# 15. POCSO Pricing Configuration
# 15. POCSO Pricing Configuration
class POCSOPricingConfig(models.Model):
    # [1] Granular Training Rates (Per Head)
    teacher_rate_online = models.DecimalField(
        max_digits=10, decimal_places=2, default=136.00
    )
    teacher_rate_offline = models.DecimalField(
        max_digits=10, decimal_places=2, default=136.00
    )
    teacher_rate_elearning = models.DecimalField(
        max_digits=10, decimal_places=2, default=136.00
    )

    staff_rate_online = models.DecimalField(
        max_digits=10, decimal_places=2, default=91.00
    )
    staff_rate_offline = models.DecimalField(
        max_digits=10, decimal_places=2, default=91.00
    )
    staff_rate_elearning = models.DecimalField(
        max_digits=10, decimal_places=2, default=91.00
    )

    student_rate = models.DecimalField(max_digits=10, decimal_places=2, default=55.00)

    # Deprecated single rates
    teacher_rate = models.DecimalField(max_digits=10, decimal_places=2, default=136.00)
    staff_rate = models.DecimalField(max_digits=10, decimal_places=2, default=91.00)

    # [2] Flat Compliance Fees
    fee_no_policy = models.DecimalField(
        max_digits=10, decimal_places=2, default=5000.00
    )
    fee_no_committee = models.DecimalField(
        max_digits=10, decimal_places=2, default=5000.00
    )
    fee_no_training = models.DecimalField(
        max_digits=10, decimal_places=2, default=5000.00
    )
    fee_no_transport = models.DecimalField(
        max_digits=10, decimal_places=2, default=5000.00
    )
    fee_no_vendor = models.DecimalField(
        max_digits=10, decimal_places=2, default=5000.00
    )
    fee_no_student_training = models.DecimalField(
        max_digits=10, decimal_places=2, default=5000.00
    )

    # Global Settings
    gst_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=18.00)

    # Metadata
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(
        default=True, help_text="Only ONE active config should exist"
    )

    class Meta:
        verbose_name = "POCSO Pricing Configuration"
        verbose_name_plural = "POCSO Pricing Configurations"

    def __str__(self):
        return f"POCSO Pricing Config (Updated: {self.updated_at.date()}) - Active: {self.is_active}"


# 16. Email Templates for Registrations
class EmailTemplate(models.Model):
    TIER_CHOICES = (
        ("PAY_NOW", "Payment Received Confirmation"),
        ("PAYMENT_VERIFIED", "Payment Verified – Onboarding Confirmed"),
        ("EMPLOYEE_WELCOME", "Employee Welcome – Account Credentials"),
    )
    tier_key = models.CharField(max_length=20, choices=TIER_CHOICES, unique=True)
    subject = models.CharField(max_length=255)
    body = models.TextField(
        help_text="Placeholders: {name}, {company_name}, {amount}, {invoice_url}, {id}"
    )

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Email: {self.get_tier_key_display()}"
# 16. Poster-specific Logo Configuration
class PosterLogoConfig(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="poster_configs"
    )
    poster_path = models.CharField(
        max_length=500
    )  # e.g. "/media/Posters/POSH Poster.webp"
    logo_x = models.FloatField(default=2.0)
    logo_y = models.FloatField(default=2.0)
    logo_width = models.FloatField(default=15.0)
    logo = models.ImageField(upload_to="poster_logos/", null=True, blank=True)

    # Company text overlay fields
    company_name = models.CharField(max_length=200, blank=True, default="")
    company_address = models.CharField(max_length=500, blank=True, default="")
    text_x = models.FloatField(default=3.0)   # % left from poster left edge
    text_y = models.FloatField(default=88.0)  # % top from poster top edge
    text_size = models.FloatField(default=2.2)  # % of poster width for font size
    text_color = models.CharField(max_length=7, default="#000000")

    class Meta:
        unique_together = ("organization", "poster_path")

    def __str__(self):
        return f"{self.organization.name} - {self.poster_path}"


# 17. POSH Policy Model for Dynamic Generation
class POSHPolicy(models.Model):
    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name="posh_policy")
    
    # Section A - Company Details
    company_name = models.CharField(max_length=255)
    registered_address = models.TextField()
    hr_email = models.EmailField()
    posh_email = models.EmailField(default="")
    effective_date = models.DateField()
    district_name = models.CharField(max_length=100)
    
    # Section B - IC Details
    po_name = models.CharField(max_length=255)
    po_email = models.EmailField()
    po_phone = models.CharField(max_length=20)
    
    m1_name = models.CharField(max_length=255)
    m1_email = models.EmailField()
    m1_phone = models.CharField(max_length=20)
    
    m2_name = models.CharField(max_length=255)
    m2_email = models.EmailField()
    m2_phone = models.CharField(max_length=20)

    m3_name = models.CharField(max_length=255, default="")
    m3_email = models.EmailField(default="")
    m3_phone = models.CharField(max_length=20, default="")

    m4_name = models.CharField(max_length=255, default="")
    m4_email = models.EmailField(default="")
    m4_phone = models.CharField(max_length=20, default="")
    
    ext_name = models.CharField(max_length=255)
    ext_email = models.EmailField()
    ext_phone = models.CharField(max_length=20)
    
    # Section C - HR Head
    hr_head_name = models.CharField(max_length=255)

    # Section C.2 - Escalation Matrix
    escalation_officer_name = models.CharField(max_length=255, default="")
    escalation_officer_designation = models.CharField(max_length=255, default="")
    
    # Section D - Approval
    approver_name = models.CharField(max_length=255)
    approver_designation = models.CharField(max_length=255)
    approval_date = models.DateField()
    
    # Brand/Logo
    company_logo = models.ImageField(upload_to="policy_logos/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"POSH Policy for {self.company_name}"

