from django.contrib import admin
from .models import User, SubscriptionPlan, Subscription, Organization, Payment

admin.site.register(User)
admin.site.register(SubscriptionPlan)
admin.site.register(Subscription)
admin.site.register(Organization)
admin.site.register(Payment)
