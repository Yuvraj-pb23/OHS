from django.core.management.base import BaseCommand
from home.models import User


class Command(BaseCommand):
    help = 'Generate user IDs for existing users who do not have one'

    def handle(self, *args, **options):
        users_without_id = User.objects.filter(user_id__isnull=True)
        count = users_without_id.count()
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS('All users already have IDs'))
            return
        
        self.stdout.write(f'Found {count} users without IDs. Generating...')
        
        for user in users_without_id:
            user.user_id = user.generate_user_id()
            user.save()
            self.stdout.write(f'Generated ID {user.user_id} for user {user.username}')
        
        self.stdout.write(self.style.SUCCESS(f'Successfully generated IDs for {count} users'))
