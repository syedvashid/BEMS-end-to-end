"""Audit writer. Same-transaction (strict): callers invoke record() inside transaction.atomic()
together with the change. The DB trigger fills chain_seq/prev_hash/row_hash."""
import ipaddress
import json
import re

from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection

UNSET = object()
REDACTED = "[REDACTED]"
# Central redaction list (matched case-insensitively on dict keys, at any depth).
REDACTED_FIELDS = frozenset({
    "password", "password_hash", "new_password", "old_password",
    "token", "access_token", "refresh_token", "secret", "api_key",
})
SNAPSHOT_SKIP = frozenset({"id", "created_at", "created_by", "updated_at", "updated_by", "row_version", "facility"})
_ACTION_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

_INSERT = """
INSERT INTO audit_log
  (facility_id, actor_user_id, actor_username, action, entity_type, entity_public_id,
   previous_value, new_value, changed_fields, request_id, ip_address, user_agent,
   http_method, request_path)
VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::text[], %s, %s::inet, %s, %s, %s)
RETURNING id
"""


def redact(value):
    if isinstance(value, dict):
        return {k: (REDACTED if str(k).lower() in REDACTED_FIELDS else redact(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


def snapshot(instance):
    """Raw dict of an instance's business fields. FKs appear as the related public_id."""
    out = {}
    for f in instance._meta.concrete_fields:
        if f.name in SNAPSHOT_SKIP:
            continue
        if f.is_relation:
            rel = getattr(instance, f.name, None)
            out[f.name] = str(rel.public_id) if rel is not None else None
        else:
            out[f.name] = getattr(instance, f.attname)
    return out


def diff(before, after):
    keys = set(before or {}) | set(after or {})
    return sorted(k for k in keys if (before or {}).get(k) != (after or {}).get(k))


def _dumps(value):
    if value is None:
        return None
    return json.dumps(redact(value), cls=DjangoJSONEncoder, sort_keys=True)


def _request_info(request):
    if request is None:
        return {}
    http = getattr(request, "_request", request)
    ctx = getattr(request, "bems", None)
    try:
        user = request.user
    except Exception:
        user = None
    ip = http.META.get("REMOTE_ADDR")  # X-Forwarded-For is spoofable; trusted-proxy handling is a hardening item
    try:
        ip = str(ipaddress.ip_address(ip)) if ip else None
    except ValueError:
        ip = None
    return {
        "facility_id": ctx.facility.id if ctx is not None and ctx.facility is not None else None,
        "actor_user_id": getattr(user, "id", None),
        "actor_username": getattr(user, "username", None),
        "request_id": getattr(http, "request_id", None),
        "ip": ip,
        "user_agent": (http.META.get("HTTP_USER_AGENT") or "")[:255] or None,
        "method": http.method,
        "path": (http.path or "")[:500],
    }


def record(*, action, request=None, facility_id=UNSET, entity_type=None, entity_public_id=None,
           previous=None, new=None, changed_fields=None):
    if not _ACTION_RE.match(action or ""):
        raise ValueError("Invalid audit action name.")
    info = _request_info(request)
    if facility_id is UNSET:
        facility_id = info.get("facility_id")
    with connection.cursor() as cur:
        cur.execute(_INSERT, [
            facility_id, info.get("actor_user_id"), info.get("actor_username"), action, entity_type,
            str(entity_public_id) if entity_public_id is not None else None,
            _dumps(previous), _dumps(new), list(changed_fields) if changed_fields is not None else None,
            info.get("request_id"), info.get("ip"), info.get("user_agent"), info.get("method"), info.get("path"),
        ])
        return cur.fetchone()[0]