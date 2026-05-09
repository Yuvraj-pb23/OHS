import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'OHPL.settings')
django.setup()

from django.test import Client
from home.models import User, OrganizationMember
admin_member = OrganizationMember.objects.filter(role="ADMIN").first()
if not admin_member:
    print("No admin found.")
else:
    user = admin_member.user
    print(f"Testing as user: {user.email}")
    c = Client()
    c.force_login(user)
    response = c.get('/dashboard/company/')
    print("Status Code:", response.status_code)
    if response.status_code == 500:
        print("500 ERROR CAUGHT!")
        print(response.content.decode('utf-8')[:2000]) # Print start of traceback
    elif response.status_code == 302:
        print("Redirected to:", response.url)
