from django.contrib.auth.backends import ModelBackend
from .models import User


class GSBAuthBackend(ModelBackend):
    """
    Dual-field authentication backend.

    Django's default ModelBackend always looks up users by USERNAME_FIELD
    (which is 'email' on our model). That breaks student login because students
    authenticate via admission number stored in the 'username' column, not email.

    Routing logic (matches LoginView):
      - authenticate(username=<value>, ...)  → lookup by User.username (STUDENT)
      - authenticate(email=<value>, ...)     → lookup by User.email (all other roles)
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if (email := kwargs.get('email')) is not None:
            # Explicit email kwarg — used by LoginView for all non-student roles
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                User().set_password(password)
                return None
        elif username is not None and '@' in username:
            # Django admin passes the typed value via the `username` kwarg.
            # If it looks like an email, route it to the email column so that
            # PLATFORM_ADMIN (and any email-based user) can log in via /admin/.
            try:
                user = User.objects.get(email=username)
            except User.DoesNotExist:
                User().set_password(password)
                return None
        elif username is not None:
            # No @ → admission number; used by LoginView for STUDENT role
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                User().set_password(password)
                return None
        else:
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
