"""Signed, expiring download tokens for report files (own salt, separate from document links)."""
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.utils import timezone

SALT = "bems.reports.download.v1"


def ttl_seconds():
    return int(getattr(settings, "BEMS_DOWNLOAD_LINK_TTL_SECONDS", 300))


def issue(run_public_id, facility_public_id, user_public_id):
    token = signing.dumps({"r": str(run_public_id), "f": str(facility_public_id), "u": str(user_public_id)},
                          salt=SALT, compress=True)
    return token, timezone.now() + timedelta(seconds=ttl_seconds())


def read(token):
    """Raises signing.BadSignature (including SignatureExpired) on any problem."""
    return signing.loads(token, salt=SALT, max_age=ttl_seconds())
