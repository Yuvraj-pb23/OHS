from django.contrib import admin
from .models import Organization, Payment, Subscription, SubscriptionPlan, User, BookTrainingRegistration

admin.site.register(User)
admin.site.register(SubscriptionPlan)
admin.site.register(Subscription)
admin.site.register(Organization)
admin.site.register(Payment)
admin.site.register(BookTrainingRegistration)