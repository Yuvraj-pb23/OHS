import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'OHS.settings')
django.setup()

from home.models import Organization

def run_migration():
    orgs = Organization.objects.all()
    migrated_count = 0
    for org in orgs:
        if org.default_password:
            # Getting the attribute triggers from_db_value which does decryption
            current_pass = org.default_password
            
            # Reassigning and saving triggers get_prep_value which does Fernet encryption
            org.default_password = current_pass
            org.save(update_fields=['default_password'])
            migrated_count += 1
            
    print(f"Successfully migrated {migrated_count} Organization records.")

if __name__ == '__main__':
    run_migration()
