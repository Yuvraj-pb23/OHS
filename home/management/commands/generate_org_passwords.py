from django.core.management.base import BaseCommand
from home.models import Organization


class Command(BaseCommand):
    help = 'Generate default passwords for existing organizations'

    def handle(self, *args, **options):
        orgs_without_password = Organization.objects.filter(default_password__isnull=True)
        count = orgs_without_password.count()
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS('All organizations already have default passwords'))
            return
        
        self.stdout.write(f'Found {count} organizations without default passwords. Generating...')
        
        for org in orgs_without_password:
            org.default_password = org.generate_default_password()
            org.save()
            self.stdout.write(f'Generated password {org.default_password} for organization {org.name}')
        
        self.stdout.write(self.style.SUCCESS(f'Successfully generated passwords for {count} organizations'))
