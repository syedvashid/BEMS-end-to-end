"""Reusable, documented ViewSet machinery.

ScopedQuerysetMixin  - scope_queryset() hook, hides inactive rows unless
                       ?include_inactive=true AND the user holds `include_inactive_permission`.
AuditedWriteMixin    - create/update/destroy with: server-set fields, strict unknown-field
                       rejection, optimistic locking (row_version), soft delete, and audit
                       written in the SAME transaction (CREATE / UPDATE / SOFT_DELETE).
AuditedModelViewSet  - the two above on ModelViewSet (use for global tables).
FacilityScopedViewSet- additionally always filters by request.bems.facility and sets facility
                       on create. Phase 2+ business tables subclass THIS.
"""
from django.db import transaction
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.core import audit
from apps.core.errors import StaleVersion

from .permissions import BemsPermission

UUID_RE = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"


class ScopedQuerysetMixin:
    permission_classes = [BemsPermission]
    lookup_field = "public_id"
    lookup_value_regex = UUID_RE
    include_inactive_permission = None   # permission code that unlocks include_inactive=true
    hide_inactive = True                 # False for tables without is_active

    @property
    def ctx(self):
        return self.request.bems

    def scope_queryset(self, queryset):
        return queryset

    def wants_inactive(self):
        ctx = getattr(self.request, "bems", None)
        if ctx is None or not self.include_inactive_permission:
            return False
        flag = str(self.request.query_params.get("include_inactive", "")).lower() in ("1", "true")
        return flag and ctx.has(self.include_inactive_permission)   # without permission: silently ignored

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset.none()
        qs = self.scope_queryset(self.queryset.all())
        if self.hide_inactive and not self.wants_inactive():
            qs = qs.filter(is_active=True)
        return qs


class ReadOnlyScopedViewSet(ScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    http_method_names = ["get", "head"]


class AuditedWriteMixin:
    audit_entity_type = None

    def entity_type(self):
        return self.audit_entity_type or self.queryset.model.__name__

    def audit_facility_id(self, instance):
        return audit.UNSET   # default: the request's current facility

    def server_fields(self, action):
        uid = self.request.user.id
        return {"created_by": uid, "updated_by": uid} if action == "create" else {"updated_by": uid}

    def check_can_modify(self, instance, action):
        """Hook: raise to forbid UPDATE / SOFT_DELETE of this instance."""

    def get_object_for_update(self):
        qs = self.get_queryset().select_for_update(of=("self",))
        obj = get_object_or_404(qs, **{self.lookup_field: self.kwargs[self.lookup_url_kwarg or self.lookup_field]})
        self.check_object_permissions(self.request, obj)
        return obj

    def reject_unknown_fields(self, data, allowed=None):
        if not isinstance(data, dict):
            raise ValidationError({"non_field_errors": ["Expected a JSON object."]})
        if allowed is None:
            allowed = set(self.get_serializer().fields.keys()) | {"row_version"}
        unknown = sorted(set(data) - set(allowed))
        if unknown:
            raise ValidationError({name: ["Unknown field."] for name in unknown})

    @staticmethod
    def parse_row_version(raw):
        if raw is None:
            raise ValidationError({"row_version": ["This field is required."]})
        try:
            if isinstance(raw, bool):
                raise ValueError
            value = int(raw)
        except (TypeError, ValueError):
            raise ValidationError({"row_version": ["A valid integer is required."]})
        if value < 1:
            raise ValidationError({"row_version": ["A valid integer is required."]})
        return value

    def _audit(self, action, instance, previous, new):
        audit.record(
            request=self.request, action=action, facility_id=self.audit_facility_id(instance),
            entity_type=self.entity_type(), entity_public_id=instance.public_id,
            previous=previous, new=new, changed_fields=audit.diff(previous, new),
        )

    def create(self, request, *args, **kwargs):
        self.reject_unknown_fields(request.data)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            instance = serializer.save(**self.server_fields("create"))
            self._audit("CREATE", instance, None, audit.snapshot(instance))
        return Response(self.get_serializer(instance).data, status=201)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        self.reject_unknown_fields(request.data)
        expected = self.parse_row_version(request.data.get("row_version"))
        with transaction.atomic():
            instance = self.get_object_for_update()
            if instance.row_version != expected:
                raise StaleVersion(current_row_version=instance.row_version)
            self.check_can_modify(instance, "UPDATE")
            before = audit.snapshot(instance)
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            serializer.is_valid(raise_exception=True)
            instance = serializer.save(**self.server_fields("update"))
            instance.refresh_from_db(fields=["updated_at", "row_version"])  # trigger-maintained
            self._audit("UPDATE", instance, before, audit.snapshot(instance))
        return Response(self.get_serializer(instance).data)

    def destroy(self, request, *args, **kwargs):
        raw = request.query_params.get("row_version")   # optional for DELETE
        expected = self.parse_row_version(raw) if raw is not None else None
        with transaction.atomic():
            instance = self.get_object_for_update()
            if expected is not None and instance.row_version != expected:
                raise StaleVersion(current_row_version=instance.row_version)
            self.check_can_modify(instance, "SOFT_DELETE")
            before = audit.snapshot(instance)
            instance.is_active = False
            instance.updated_by = request.user.id
            instance.save(update_fields=["is_active", "updated_by"])
            instance.refresh_from_db(fields=["updated_at", "row_version"])
            self._audit("SOFT_DELETE", instance, before, audit.snapshot(instance))
        return Response(status=204)


class AuditedModelViewSet(ScopedQuerysetMixin, AuditedWriteMixin, viewsets.ModelViewSet):
    http_method_names = ["get", "post", "put", "patch", "delete", "head"]


class FacilityScopedViewSet(AuditedModelViewSet):
    facility_required = True

    def scope_queryset(self, queryset):
        return queryset.filter(facility_id=self.request.bems.facility.id)

    def server_fields(self, action):
        data = super().server_fields(action)
        if action == "create":
            data["facility"] = self.request.bems.facility
        return data