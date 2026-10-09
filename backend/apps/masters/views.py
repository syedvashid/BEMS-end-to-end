from django.db import transaction
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core import audit
from apps.foundation.viewsets import FacilityScopedViewSet

from . import gates
from .defaults import DEFAULT_CATEGORIES, DEFAULT_GROUPS
from .filters import (
    DepartmentFilter, EquipmentCategoryFilter, EquipmentModelFilter, FundingSourceFilter,
    LocationFilter, VendorContactFilter, VendorFilter,
)
from .models import Department, EquipmentCategory, EquipmentModel, FundingSource, Location, Vendor, VendorContact
from .serializers import (
    DepartmentSerializer, EquipmentCategorySerializer, EquipmentModelSerializer, FundingSourceSerializer,
    LocationSerializer, VendorContactSerializer, VendorSerializer,
)


def crud_perms(prefix, **extra):
    perms = {
        "list": f"{prefix}.view", "retrieve": f"{prefix}.view", "create": f"{prefix}.add",
        "update": f"{prefix}.change", "partial_update": f"{prefix}.change", "destroy": f"{prefix}.delete",
    }
    perms.update(extra)
    return perms


class DepartmentViewSet(FacilityScopedViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    required_permissions = crud_perms("department")
    include_inactive_permission = "department.delete"
    filterset_class = DepartmentFilter
    ordering_fields = ["code", "name", "department_type", "created_at"]
    ordering = ["name"]

    def check_can_modify(self, instance, action):
        if action == "SOFT_DELETE":
            gates.ensure_department_deletable(instance)


class LocationViewSet(FacilityScopedViewSet):
    queryset = Location.objects.select_related("parent_location", "department")
    serializer_class = LocationSerializer
    required_permissions = crud_perms("location", tree="location.view")
    include_inactive_permission = "location.delete"
    filterset_class = LocationFilter
    ordering_fields = ["code", "name", "location_type", "created_at"]
    ordering = ["name"]

    def check_can_modify(self, instance, action):
        if action == "SOFT_DELETE":
            gates.ensure_location_deletable(instance)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"], url_path="tree")
    def tree(self, request):
        rows = list(
            Location.objects.filter(facility_id=self.ctx.facility.id, is_active=True)
            .order_by("name", "code")
            .values("public_id", "code", "name", "location_type", "parent_location__public_id",
                    "department__public_id", "department__name")
        )
        nodes = {
            r["public_id"]: {
                "public_id": str(r["public_id"]), "code": r["code"], "name": r["name"],
                "location_type": r["location_type"],
                "department": str(r["department__public_id"]) if r["department__public_id"] else None,
                "department_name": r["department__name"],
                "children": [],
            }
            for r in rows
        }
        roots = []
        for r in rows:
            parent = nodes.get(r["parent_location__public_id"])
            (parent["children"] if parent else roots).append(nodes[r["public_id"]])
        return Response(roots)


class EquipmentCategoryViewSet(FacilityScopedViewSet):
    queryset = EquipmentCategory.objects.select_related("parent_category")
    serializer_class = EquipmentCategorySerializer
    required_permissions = crud_perms("equipment_category", load_defaults="equipment_category.add")
    include_inactive_permission = "equipment_category.delete"
    filterset_class = EquipmentCategoryFilter
    ordering_fields = ["code", "name", "risk_class", "created_at"]
    ordering = ["name"]

    def check_can_modify(self, instance, action):
        if action == "SOFT_DELETE":
            gates.ensure_category_deletable(instance)

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"], url_path="load-defaults")
    def load_defaults(self, request):
        self.reject_unknown_fields(request.data, allowed=set())
        fid, uid = self.ctx.facility.id, request.user.id
        created = []
        with transaction.atomic():
            by_code = {
                c.code.upper(): c
                for c in EquipmentCategory.objects.filter(facility_id=fid, is_active=True)
            }

            def make(code, name, parent, pm=None, cal=None, risk="MEDIUM"):
                obj = EquipmentCategory.objects.create(
                    facility_id=fid, parent_category=parent, code=code, name=name,
                    default_pm_interval_days=pm, default_calibration_interval_days=cal,
                    risk_class=risk, created_by=uid, updated_by=uid,
                )
                by_code[code] = obj
                created.append(code)

            for code, name in DEFAULT_GROUPS:
                if code not in by_code:
                    make(code, name, None)
            for code, name, group, pm, cal, risk in DEFAULT_CATEGORIES:
                if code in by_code:
                    continue
                parent = by_code.get(group)
                if parent is not None and parent.parent_category_id is not None:
                    parent = None   # the facility re-arranged this group; keep the two-level rule
                make(code, name, parent, pm, cal, risk)

            audit.record(
                request=request, action="LOAD_DEFAULTS", facility_id=fid, entity_type="EquipmentCategory",
                new={"created_codes": created},
            )
        total = len(DEFAULT_GROUPS) + len(DEFAULT_CATEGORIES)
        return Response({"created": len(created), "created_codes": created, "skipped": total - len(created)})


class VendorViewSet(FacilityScopedViewSet):
    queryset = Vendor.objects.all()
    serializer_class = VendorSerializer
    required_permissions = crud_perms("vendor")
    include_inactive_permission = "vendor.delete"
    filterset_class = VendorFilter
    ordering_fields = ["name", "city", "rating", "created_at"]
    ordering = ["name"]

    def check_can_modify(self, instance, action):
        if action == "SOFT_DELETE":
            gates.ensure_vendor_deletable(instance)


class VendorContactViewSet(FacilityScopedViewSet):
    queryset = VendorContact.objects.select_related("vendor")
    serializer_class = VendorContactSerializer
    required_permissions = crud_perms("vendor")
    include_inactive_permission = "vendor.delete"
    filterset_class = VendorContactFilter
    ordering_fields = ["name", "contact_type", "created_at"]
    ordering = ["-is_primary", "name"]


class FundingSourceViewSet(FacilityScopedViewSet):
    queryset = FundingSource.objects.all()
    serializer_class = FundingSourceSerializer
    required_permissions = crud_perms("funding_source")
    include_inactive_permission = "funding_source.delete"
    filterset_class = FundingSourceFilter
    ordering_fields = ["code", "name", "source_type", "created_at"]
    ordering = ["name"]

    def check_can_modify(self, instance, action):
        if action == "SOFT_DELETE":
            gates.ensure_funding_source_deletable(instance)


class EquipmentModelViewSet(FacilityScopedViewSet):
    queryset = EquipmentModel.objects.select_related("category", "manufacturer")
    serializer_class = EquipmentModelSerializer
    required_permissions = crud_perms("equipment_model")
    include_inactive_permission = "equipment_model.delete"
    filterset_class = EquipmentModelFilter
    ordering_fields = ["model_name", "model_number", "created_at"]
    ordering = ["model_name"]

    def check_can_modify(self, instance, action):
        if action == "SOFT_DELETE":
            gates.ensure_equipment_model_deletable(instance)