import uuid
from dataclasses import dataclass

from rest_framework.exceptions import NotFound

from apps.core.errors import FacilityRequired

from .models import RolePermission, UserFacilityRole


@dataclass(frozen=True)
class RequestContext:
    user: object
    facility: object            # Facility or None
    role_codes: frozenset
    permissions: frozenset

    def has(self, code):
        return code in self.permissions


def member_facilities(user_id):
    """values('facility_id') queryset of facilities the user actively belongs to."""
    return UserFacilityRole.objects.filter(
        user_id=user_id, is_active=True, role__is_active=True, facility__is_active=True
    ).values("facility_id")


def resolve_context(request, facility_required):
    user = request.user
    empty = RequestContext(user, None, frozenset(), frozenset())
    raw = (request.headers.get("X-Facility-Id") or "").strip()
    if not raw:
        if facility_required:
            raise FacilityRequired()
        return empty
    try:
        fid = uuid.UUID(raw)
    except ValueError:
        if facility_required:
            raise NotFound()
        return empty
    rows = list(
        UserFacilityRole.objects.filter(
            user_id=user.id, is_active=True, role__is_active=True,
            facility__public_id=fid, facility__is_active=True,
        ).select_related("facility", "role")
    )
    if not rows:  # unknown facility and "not a member" are indistinguishable by design
        if facility_required:
            raise NotFound()
        return empty
    codes = set(
        RolePermission.objects.filter(
            role_id__in=[r.role_id for r in rows], permission__is_active=True
        ).values_list("permission__code", flat=True)
    )
    return RequestContext(user, rows[0].facility, frozenset(r.role.code for r in rows), frozenset(codes))