from django.db import transaction
from django.db.models import Prefetch
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import audit
from apps.core.errors import Conflict, StaleVersion

from .context import member_facilities
from .filters import AuditLogFilter, FacilityFilter, RoleFilter, UserFilter
from .models import AuditLog, Facility, Permission, Role, RolePermission, User, UserFacilityRole
from .permissions import deny
from .serializers import (
    AuditLogSerializer, FacilityRolesInputSerializer, FacilitySerializer, PermissionSerializer,
    RolePermissionsInputSerializer, RoleSerializer, UserSerializer,
)
from .viewsets import AuditedModelViewSet, ReadOnlyScopedViewSet


def assert_can_grant(request, view, permission_codes, reason):
    """Privilege-escalation guard: you cannot grant/revoke what you do not hold yourself."""
    excess = set(permission_codes) - request.bems.permissions
    if excess:
        deny(request, view, view.action, excess, reason)


class MeView(APIView):
    facility_required = False
    required_permissions = {"get": ()}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        ctx = request.bems
        rows = (
            UserFacilityRole.objects.filter(
                user_id=ctx.user.id, is_active=True, role__is_active=True, facility__is_active=True
            ).select_related("facility", "role").order_by("facility__name", "role__code")
        )
        facilities = {}
        for r in rows:
            entry = facilities.setdefault(r.facility_id, {
                "public_id": str(r.facility.public_id), "code": r.facility.code,
                "name": r.facility.name, "facility_type": r.facility.facility_type, "roles": [],
            })
            entry["roles"].append({"code": r.role.code, "name": r.role.name})
        current = None
        if ctx.facility is not None:
            current = {"public_id": str(ctx.facility.public_id), "code": ctx.facility.code, "name": ctx.facility.name}
        roles = [
            {"code": r.code, "name": r.name}
            for r in Role.objects.filter(code__in=ctx.role_codes, is_active=True).order_by("code")
        ]
        u = ctx.user
        return Response({
            "user": {"public_id": str(u.public_id), "username": u.username, "full_name": u.full_name,
                     "email": u.email, "designation": u.designation},
            "facilities": list(facilities.values()),
            "current_facility": current,
            "roles": roles,
            "permissions": sorted(ctx.permissions),
        })


class FacilityViewSet(AuditedModelViewSet):
    queryset = Facility.objects.select_related("parent_facility")
    serializer_class = FacilitySerializer
    facility_required = {"list": False, "retrieve": False}   # everything else needs X-Facility-Id
    required_permissions = {
        "list": (), "retrieve": (),        # own member facilities only
        "create": "facility.add",
        "update": "facility.change", "partial_update": "facility.change",
        "destroy": "facility.delete",
    }
    include_inactive_permission = "facility.delete"
    filterset_class = FacilityFilter
    ordering_fields = ["name", "code", "created_at"]
    ordering = ["name"]

    def scope_queryset(self, qs):
        if self.action in ("list", "retrieve"):
            return qs.filter(pk__in=member_facilities(self.ctx.user.id))
        return qs.filter(pk=self.ctx.facility.pk)   # update/delete: only the CURRENT facility

    def audit_facility_id(self, instance):
        return instance.id


class UserViewSet(AuditedModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    required_permissions = {
        "list": "user.view", "retrieve": "user.view", "create": "user.add",
        "update": "user.change", "partial_update": "user.change",
        "destroy": "user.delete", "set_facility_roles": "user.change",
    }
    include_inactive_permission = "user.delete"
    filterset_class = UserFilter
    ordering_fields = ["username", "full_name", "created_at"]
    ordering = ["username"]

    def scope_queryset(self, qs):
        if self.action == "set_facility_roles":
            return qs   # needed so a user without a membership yet can be assigned (id is a non-guessable uuid)
        return qs.filter(pk__in=UserFacilityRole.objects.filter(
            facility_id=self.ctx.facility.id, is_active=True, role__is_active=True
        ).values("user_id"))

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action in ("list", "retrieve") and not getattr(self, "swagger_fake_view", False):
            qs = qs.prefetch_related(Prefetch(
                "facility_roles",
                queryset=UserFacilityRole.objects.filter(
                    facility_id=self.ctx.facility.id, is_active=True, role__is_active=True
                ).select_related("role", "facility"),
                to_attr="current_facility_roles",
            ))
        return qs

    def check_can_modify(self, instance, action):
        if action == "SOFT_DELETE" and instance.pk == self.request.user.pk:
            raise Conflict("You cannot deactivate your own account.")

    @extend_schema(request=FacilityRolesInputSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"], url_path="facility-roles")
    def set_facility_roles(self, request, public_id=None):
        """Replace the set of roles this user has in ONE facility (empty list = remove membership)."""
        ctx = request.bems
        self.reject_unknown_fields(request.data, allowed={"facility", "roles"})
        inp = FacilityRolesInputSerializer(data=request.data)
        inp.is_valid(raise_exception=True)
        target_user = self.get_object()

        facility = ctx.facility
        wanted = inp.validated_data.get("facility")
        if wanted and wanted != ctx.facility.public_id:
            # Bootstrap path: only holders of BOTH facility.add and user.change may assign in another facility.
            if not (ctx.has("facility.add") and ctx.has("user.change")):
                raise NotFound()
            facility = Facility.objects.filter(public_id=wanted, is_active=True).first()
            if facility is None:
                raise NotFound()

        role_ids = inp.validated_data["roles"]
        roles = list(Role.objects.filter(public_id__in=role_ids, is_active=True))
        if len(roles) != len(role_ids):
            raise ValidationError({"roles": ["Unknown role."]})

        current_ids = set(UserFacilityRole.objects.filter(
            user_id=target_user.id, facility_id=facility.id, is_active=True
        ).values_list("role_id", flat=True))
        changed = current_ids ^ {r.id for r in roles}
        if changed:
            codes = RolePermission.objects.filter(
                role_id__in=changed, permission__is_active=True
            ).values_list("permission__code", flat=True)
            assert_can_grant(request, self, codes, "role_exceeds_own_permissions")   # 403 + audit, outside atomic

        uid = request.user.id
        with transaction.atomic():
            locked = list(UserFacilityRole.objects.select_for_update(of=("self",)).filter(
                user_id=target_user.id, facility_id=facility.id, is_active=True
            ).select_related("role"))
            before_codes = sorted(l.role.code for l in locked)
            after_codes = sorted(r.code for r in roles)
            if before_codes != after_codes:
                desired = {r.id for r in roles}
                have = {l.role_id for l in locked}
                for l in locked:
                    if l.role_id not in desired:
                        l.is_active = False
                        l.updated_by = uid
                        l.save(update_fields=["is_active", "updated_by"])
                for r in roles:
                    if r.id not in have:
                        UserFacilityRole.objects.create(
                            user=target_user, facility=facility, role=r, created_by=uid, updated_by=uid
                        )
                fpid = str(facility.public_id)
                audit.record(
                    request=request, action="USER_FACILITY_ROLE_CHANGE", facility_id=facility.id,
                    entity_type="User", entity_public_id=target_user.public_id,
                    previous={"facility": fpid, "roles": before_codes},
                    new={"facility": fpid, "roles": after_codes}, changed_fields=["roles"],
                )
        return Response({
            "facility": str(facility.public_id),
            "roles": [{"public_id": str(r.public_id), "code": r.code, "name": r.name} for r in roles],
        })


class RoleViewSet(AuditedModelViewSet):
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    required_permissions = {
        "list": "role.view", "retrieve": "role.view", "create": "role.manage",
        "update": "role.manage", "partial_update": "role.manage", "destroy": "role.manage",
        "set_permissions": "role.manage",
    }
    include_inactive_permission = "role.manage"
    filterset_class = RoleFilter
    ordering_fields = ["code", "name", "created_at"]
    ordering = ["code"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action in ("list", "retrieve") and not getattr(self, "swagger_fake_view", False):
            qs = qs.prefetch_related(Prefetch(
                "role_permissions",
                queryset=RolePermission.objects.filter(permission__is_active=True).select_related("permission"),
                to_attr="prefetched_perms",
            ))
        return qs

    def server_fields(self, action):
        data = super().server_fields(action)
        if action == "create":
            data["is_system"] = False
        return data

    def check_can_modify(self, instance, action):
        if instance.is_system:
            raise Conflict("System roles cannot be changed or deleted.")

    @extend_schema(request=RolePermissionsInputSerializer, responses=RoleSerializer)
    @action(detail=True, methods=["put"], url_path="permissions")
    def set_permissions(self, request, public_id=None):
        self.reject_unknown_fields(request.data, allowed={"permission_codes", "row_version"})
        inp = RolePermissionsInputSerializer(data=request.data)
        inp.is_valid(raise_exception=True)
        codes = set(inp.validated_data["permission_codes"])
        perms = {p.code: p for p in Permission.objects.filter(code__in=codes, is_active=True)}
        unknown = sorted(codes - perms.keys())
        if unknown:
            raise ValidationError({"permission_codes": [f"Unknown permission: {c}" for c in unknown]})

        role = self.get_object()
        self.check_can_modify(role, "ROLE_PERMISSIONS_CHANGE")
        current = set(RolePermission.objects.filter(role_id=role.id).values_list("permission__code", flat=True))
        assert_can_grant(request, self, codes ^ current, "permission_exceeds_own_permissions")

        uid = request.user.id
        with transaction.atomic():
            role = self.get_object_for_update()
            if role.row_version != inp.validated_data["row_version"]:
                raise StaleVersion(current_row_version=role.row_version)
            current = set(RolePermission.objects.filter(role_id=role.id).values_list("permission__code", flat=True))
            removed, added = current - codes, codes - current
            if removed:
                ids = list(RolePermission.objects.filter(
                    role_id=role.id, permission__code__in=removed).values_list("id", flat=True))
                RolePermission.objects.filter(id__in=ids).delete()
            if added:
                RolePermission.objects.bulk_create(
                    [RolePermission(role=role, permission=perms[c], created_by=uid) for c in sorted(added)]
                )
            role.updated_by = uid
            role.save(update_fields=["updated_by"])           # bumps row_version via trigger
            role.refresh_from_db(fields=["updated_at", "row_version"])
            audit.record(
                request=request, action="ROLE_PERMISSIONS_CHANGE", entity_type="Role",
                entity_public_id=role.public_id,
                previous={"permission_codes": sorted(current)}, new={"permission_codes": sorted(codes)},
                changed_fields=["permission_codes"] if (removed or added) else [],
            )
        return Response(RoleSerializer(role, context=self.get_serializer_context()).data)


class PermissionViewSet(ReadOnlyScopedViewSet):
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    required_permissions = {"list": "role.view", "retrieve": "role.view"}
    pagination_class = None          # small fixed catalogue
    ordering = ["module", "code"]
    ordering_fields = ["module", "code"]


class AuditLogViewSet(ReadOnlyScopedViewSet):
    """Basic endpoint to prove audit works (full viewer is Phase 10)."""
    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    required_permissions = {"list": "audit.view", "retrieve": "audit.view"}
    hide_inactive = False
    lookup_field = "id"
    lookup_value_regex = r"[0-9]+"
    filterset_class = AuditLogFilter
    ordering = ["-chain_seq"]
    ordering_fields = ["occurred_at", "chain_seq"]

    def scope_queryset(self, qs):
        return qs.filter(facility_id=self.ctx.facility.id)