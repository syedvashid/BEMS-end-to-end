"""DEV ONLY. Acting user from header X-Dev-User. The future real authentication
replaces exactly this module and one line in settings.REST_FRAMEWORK."""
import re

from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import User

_USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")


def dev_auth_enabled():
    return bool(settings.DEBUG and getattr(settings, "BEMS_DEV_AUTH", False))


class DevHeaderAuthentication(BaseAuthentication):
    def authenticate(self, request):
        if not dev_auth_enabled():
            return None
        username = request.headers.get("X-Dev-User", "").strip()
        if not username:
            return None
        if not _USERNAME_RE.match(username):
            raise AuthenticationFailed()
        user = User.objects.filter(username=username, is_active=True).first()
        if user is None:
            raise AuthenticationFailed()
        return (user, None)

    def authenticate_header(self, request):
        return "X-Dev-User"   # makes DRF answer 401 instead of 403