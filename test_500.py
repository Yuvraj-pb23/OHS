import os, sys
sys.path.append('/home/keshav/Documents/OHS/OHS')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'OHS.settings')
import django
django.setup()

from django.test import Client
from home.models import User, Subscription, SubscriptionPlan

sub = Subscription.objects.filter(status="ACTIVE", plan__type__in=["POSH", "BOTH"]).first()
if sub:
    user = sub.user
    if not user and sub.organization:
        from home.models import OrganizationMember
        user = OrganizationMember.objects.filter(organization=sub.organization).first().user

    c = Client()
    c.force_login(user)
    try:
        response = c.get('/tutorial/posh-act/')
        print("Status Code:", response.status_code)
        if response.status_code == 500:
            print(response.content)
    except Exception as e:
        import traceback
        traceback.print_exc()
else:
    print("No active POSH subscription found.")
