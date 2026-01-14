from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

UserModel = get_user_model()

class EmailOrUsernameModelBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        # DEBUG PRINTS - Check your terminal/cmd when you log in
        print(f"--- Login Attempt for: {username} ---") 
        
        try:
            # Check for username OR email
            user = UserModel.objects.get(Q(username__iexact=username) | Q(email__iexact=username))
            print(f"Found User in DB: {user.username} (Email: {user.email})")
        except UserModel.DoesNotExist:
            print("No user found with that username or email.")
            return None
        
        if user.check_password(password) and self.user_can_authenticate(user):
            print("Password matches! Logging in...")
            return user
        else:
            print("Password does not match.")
            return None