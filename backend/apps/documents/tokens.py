from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.utils import timezone

SALT = "bems.documents.download.v1"


def ttl():
    return int(settings.BEMS_DOWNLOAD_LINK_TTL_SECONDS)


def issue(version_public_id, facility_public_id, user_public_id, inline):
    token = signing.dumps(
        {"v": str(version_public_id), "f": str(facility_public_id), "u": str(user_public_id),
         "d": "inline" if inline else "attachment"},
        salt=SALT, compress=True,
    )
    return token, timezone.now() + timedelta(seconds=ttl())


def read(token):
    """Raises signing.BadSignature (incl. SignatureExpired) on any problem."""
    data = signing.loads(token, salt=SALT, max_age=ttl())
    if not isinstance(data, dict):
        raise signing.BadSignature("shape")
    return data