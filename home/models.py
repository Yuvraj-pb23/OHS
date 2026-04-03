from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from datetime import timedelta
from django.db.models import Q


# 1. Custom User Model
class User(AbstractUser):
    # AbstractUser has username, email, password, first_name, date_joined
    phone = models.CharField(max_length=15, blank=True, null=True)

    # NEW: Distinct types for data separation
    USER_TYPES = (
        ("INDIVIDUAL", "Individual Subscriber"),
        ("COMPANY_ADMIN", "Company Admin"),
        ("EMPLOYEE", "Company Employee"),
    )
    account_type = models.CharField(
        max_length=20, choices=USER_TYPES, default="INDIVIDUAL"
    )
    
    # Unique user ID
    user_id = models.CharField(max_length=20, unique=True, blank=True, null=True)
    
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
                    organization=organization, 
                    status="ACTIVE"
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
                        organization=membership.organization, 
                        status="ACTIVE"
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
        last_user = User.objects.filter(user_id__startswith=prefix).order_by('-id').first()
        
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
    organization_type = models.CharField(max_length=20, choices=ORG_TYPE_CHOICES, default="CORPORATE")
    max_users = models.IntegerField(default=10)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Default password for employees
    default_password = models.CharField(max_length=50, blank=True, null=True)
    logo = models.ImageField(upload_to="company_logos/", null=True, blank=True)
    
    # Logo customization (as percentages 0-100)
    logo_x = models.FloatField(default=2.0)
    logo_y = models.FloatField(default=2.0)
    logo_width = models.FloatField(default=15.0) # percentage of poster width

    def __str__(self):
        return self.name
    
    def generate_default_password(self):
        """Generate default password: First 4 letters of company + random number + special char"""
        import random
        import string
        
        # Get first 4 letters of company name (alphanumeric only)
        company_prefix = ''.join(c for c in self.name if c.isalnum())[:4].upper()
        if len(company_prefix) < 4:
            company_prefix = company_prefix.ljust(4, 'X')
        
        # Generate random 4-digit number
        random_number = random.randint(1000, 9999)
        
        # Pick a random special character
        special_char = random.choice('@#$%&*!')
        
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
    thumbnail = models.ImageField(upload_to="training_thumbnails/", blank=True, null=True)
    module_type = models.CharField(max_length=10, choices=MODULE_TYPES, default="POSH")
    order = models.IntegerField(default=1)  # To sequence modules 1, 2, 3...
    duration_seconds = models.IntegerField(default=0, help_text="Duration in seconds") # Optional, helpful for progress calc

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.module_type} - {self.order}. {self.title}"


# 9. Module Progress (Per User)
class ModuleProgress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="module_progress")
    module = models.ForeignKey(TrainingModule, on_delete=models.CASCADE)
    is_completed = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now=True)  # Last watched

    class Meta:
        unique_together = ("user", "module")

    def __str__(self):
        return f"{self.user.username} - {self.module.title} ({'Done' if self.is_completed else 'In Progress'})"


# 10. Daily Activity (For Charts)
class DailyActivity(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="daily_activity")
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
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="assessment_progress")
    assessment_type = models.CharField(max_length=10, choices=ASSESSMENT_TYPES)
    is_passed = models.BooleanField(default=False)
    score = models.IntegerField(default=0)
    timestamp = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "assessment_type")

    def __str__(self):
        return f"{self.user.username} - {self.assessment_type} - {'Passed' if self.is_passed else 'Failed'}"
