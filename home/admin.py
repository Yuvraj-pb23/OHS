from django.contrib import admin

from .models import Organization, Payment, Subscription, SubscriptionPlan, User

admin.site.register(User)
admin.site.register(SubscriptionPlan)
admin.site.register(Subscription)
admin.site.register(Organization)
admin.site.register(Payment)
