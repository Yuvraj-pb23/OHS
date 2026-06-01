from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

UserModel = get_user_model()


class EmailOrUsernameModelBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        # DEBUG PRINTS - Check your terminal/cmd when you log in
        print(f"--- Login Attempt for: {username} ---")

        try:
            # Check for username OR email
            user = UserModel.objects.get(
                Q(username__iexact=username) | Q(email__iexact=username)
            )
            print(f"Found User in DB: {user.username} (Email: {user.email})")
        except UserModel.DoesNotExist:
            print("No user found with that username or email.")
            return None
        except UserModel.MultipleObjectsReturned:
            print("Multiple users found with that username or email. Checking passwords...")
            users = UserModel.objects.filter(
                Q(username__iexact=username) | Q(email__iexact=username)
            )
            for u in users:
                if u.check_password(password) and self.user_can_authenticate(u):
                    print(f"Found matching User among duplicates: {u.username}")
                    return u
            print("Multiple users found, but none matched the password.")
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            print("Password matches! Logging in...")
            return user
        else:
            print("Password does not match.")
            return None
