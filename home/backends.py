import logging
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

UserModel = get_user_model()
logger = logging.getLogger(__name__)


class EmailOrUsernameModelBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        logger.debug(f"--- Login Attempt for: {username} ---")

        try:
            # Check for username OR email
            user = UserModel.objects.get(
                Q(username__iexact=username) | Q(email__iexact=username)
            )
            logger.debug(f"Found User in DB: {user.username} (Email: {user.email})")
        except UserModel.DoesNotExist:
            logger.debug("No user found with that username or email.")
            return None
        except UserModel.MultipleObjectsReturned:
            logger.debug("Multiple users found with that username or email. Checking passwords...")
            users = UserModel.objects.filter(
                Q(username__iexact=username) | Q(email__iexact=username)
            )
            for u in users:
                if u.check_password(password) and self.user_can_authenticate(u):
                    logger.debug(f"Found matching User among duplicates: {u.username}")
                    return u
            logger.debug("Multiple users found, but none matched the password.")
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            logger.debug("Password matches! Logging in...")
            return user
        else:
            logger.debug("Password does not match.")
            return None
