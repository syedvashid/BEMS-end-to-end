from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.permissions import BasePermission

from apps.core import audit

from .context import resolve_context

_MISSING = object()


def facility_required_for(view, action):
    fr = getattr(view, "facility_required", True)
    return fr.get(action, True) if isinstance(fr, dict) else bool(fr)


def deny(request, view, action, required, reason=None):
    """Audit ACCESS_DENIED (own autocommit, never inside a caller's atomic block) and raise 403."""
    audit.record(
        request=request, action="ACCESS_DENIED",
        entity_type=getattr(view, "audit_entity_type", None),
        new={"view": view.__class__.__name__, "action": action,
             "required": sorted(required), "reason": reason},
    )
    raise PermissionDenied()


class BemsPermission(BasePermission):
    """Gate order: acting user (401) -> facility context (404) -> permission (403 + audit).
    Views declare `required_permissions = {action: "code" | ("a", "b") | ()}`.
    () means authenticated only. An undeclared action is DENIED (fail closed).
    Optional `facility_required` (bool or {action: bool}); default True."""

    def has_permission(self, request, view):
        user = request.user
        if user is None or not getattr(user, "is_authenticated", False):
            raise NotAuthenticated()
        action = getattr(view, "action", None) or request.method.lower()
        request.bems = resolve_context(request, facility_required_for(view, action))
        spec = getattr(view, "required_permissions", {}).get(action, _MISSING)
        if spec is _MISSING:
            deny(request, view, action, [], reason="undeclared_action")
        needed = (spec,) if isinstance(spec, str) else tuple(spec)
        if any(not request.bems.has(code) for code in needed):
            deny(request, view, action, needed)
        return True