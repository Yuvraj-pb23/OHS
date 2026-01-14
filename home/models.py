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
        ('INDIVIDUAL', 'Individual Subscriber'),
        ('COMPANY_ADMIN', 'Company Admin'),
        ('EMPLOYEE', 'Company Employee'),
    )
    account_type = models.CharField(max_length=20, choices=USER_TYPES, default='INDIVIDUAL')
    
    def __str__(self):
        return f"{self.username} ({self.account_type})"

# 2. Subscription Plan
class SubscriptionPlan(models.Model):
    PLAN_TYPES = (
        ('POSH', 'POSH Act'),
        ('POCSO', 'POCSO Act'),
        ('BOTH', 'POSH & POCSO'),
    )
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=10, choices=PLAN_TYPES, default='POSH')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration_days = models.IntegerField(help_text="Duration in days (e.g., 365 for 1 year)")
    description = models.TextField()
    is_active = models.BooleanField(default=True) # To hide old plans

    def __str__(self):
        return f"{self.name} - ₹{self.price}"

# 3. Organization
class Organization(models.Model):
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_organizations')
    max_users = models.IntegerField(default=10)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

# 4. Subscription
class Subscription(models.Model):
    STATUS_CHOICES = (
        ('ACTIVE', 'Active'),
        ('EXPIRED', 'Expired'),
        ('PENDING', 'Pending Payment'),
    )
    
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE)
    
    # Linked to EITHER User OR Organization
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='subscriptions')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True, related_name='subscriptions')
    
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')

    class Meta:
        # DB Constraint: A sub must belong to User OR Org, never both, never neither
        constraints = [
          models.CheckConstraint(
    condition=models.Q(end_date__gt=models.F('start_date')),
    name='subscription_owner_constraint'
)

        ]

    def save(self, *args, **kwargs):
        if not self.end_date:
            self.end_date = self.start_date + timedelta(days=self.plan.duration_days)
        super().save(*args, **kwargs)

    @property
    def is_active(self):
        return self.status == 'ACTIVE' and self.end_date > timezone.now()

# 5. Organization Members
class OrganizationMember(models.Model):
    ROLE_CHOICES = (
        ('ADMIN', 'Admin'),
        ('MEMBER', 'Member'),
    )
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='MEMBER')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('organization', 'user') # User can't be in same org twice

# 6. Invitations
class Invitation(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    email = models.EmailField()
    token = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20, default='PENDING')
    expires_at = models.DateTimeField()

# 7. Payment History
class Payment(models.Model):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_id = models.CharField(max_length=100)
    status = models.CharField(max_length=20, default='SUCCESS')
    created_at = models.DateTimeField(auto_now_add=True)
    