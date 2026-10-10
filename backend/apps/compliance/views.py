from datetime import date

from django.db.models import Count, Exists, IntegerField, OuterRef, Subquery
from django.db.models.functions import Coalesce
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from apps.core.errors import Conflict
from apps.equipment.models import Equipment
from apps.foundation.viewsets import FacilityScopedViewSet, ReadOnlyScopedViewSet
from apps.maintenance.services import today_for
from apps.masters.models import Department

from . import services
from .filters import (
    AmcContractFilter, CalibrationRecordFilter, CalibrationScheduleFilter, EquipmentLicenceFilter,
    WarrantyClaimFilter, WarrantyFilter,
)
from .models import (
    AmcContract, AmcCoverage, CalibrationImpactReview, CalibrationRecord, CalibrationSchedule, EquipmentLicence,
    Warranty, WarrantyClaim,
)
from .serializers import (
    AmcContractDetailSerializer, AmcContractSerializer, AmcRenewSerializer, BulkWarrantySerializer,
    CalibrationRecordCreateSerializer, CalibrationRecordSerializer, CalibrationScheduleSerializer,
    CoverageSetSerializer, EquipmentLicenceSerializer, GenerateSchedulesSerializer, ImpactReviewSerializer,
    LicenceRenewSerializer, WarrantyClaimSerializer, WarrantySerializer,
)
import uuid

from rest_framework import mixins, viewsets


from apps.core.errors import Conflict
from apps.equipment.models import Equipment
from apps.foundation.permissions import deny
from apps.foundation.viewsets import FacilityScopedViewSet, ReadOnlyScopedViewSet, ScopedQuerysetMixin

CRUD = ("list", "retrieve", "create", "update", "partial_update", "destroy")


def _perms(prefix, *, view="view", add="add", change="change", delete="delete", **extra):
    m = {"list": f"{prefix}.{view}", "retrieve": f"{prefix}.{view}", "create": f"{prefix}.{add}",
         "update": f"{prefix}.{change}", "partial_update": f"{prefix}.{change}", "destroy": f"{prefix}.{delete}"}
    m.update(extra)
    return m


def _by_public_id(model, raw, facility_id, field):
    try:
        pid = uuid.UUID(str(raw))
    except ValueError:
        raise ValidationError({field: ["Invalid identifier."]})
    return model.objects.filter(public_id=pid, facility_id=facility_id).first()

class CalibrationScheduleViewSet(FacilityScopedViewSet):
    queryset = CalibrationSchedule.objects.all()
    serializer_class = CalibrationScheduleSerializer
    required_permissions = {**_perms("calibration", add="manage", change="manage", delete="manage"),
                            "generate": "calibration.manage"}
    include_inactive_permission = "calibration.manage"
    filterset_class = CalibrationScheduleFilter
    ordering_fields = ["next_due_date", "created_at", "frequency_value"]
    ordering = ["next_due_date", "id"]

    def scope_queryset(self, qs):
        return qs.select_related("equipment")

    @action(detail=False, methods=["post"])
    def generate(self, request):
        ser = GenerateSchedulesSerializer(data=request.data, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        return Response(services.generate_schedules(request=request, facility=self.ctx.facility, **ser.validated_data))


class CalibrationRecordViewSet(ReadOnlyScopedViewSet):
    """Immutable: list/retrieve/create plus review-impact. No update, no delete."""
    queryset = CalibrationRecord.objects.all()
    http_method_names = ["get", "post", "head"]
    hide_inactive = False   # this table has no is_active
    serializer_class = CalibrationRecordSerializer
    required_permissions = {"list": "calibration.view", "retrieve": "calibration.view",
                            "create": "calibration.record", "review_impact": "calibration.review"}
    filterset_class = CalibrationRecordFilter
    ordering_fields = ["performed_date", "created_at"]
    ordering = ["-performed_date", "-id"]
    

    def scope_queryset(self, qs):
        return qs.filter(facility_id=self.ctx.facility.id).select_related("equipment", "performer_vendor").annotate(
            has_impact_review=Exists(CalibrationImpactReview.objects.filter(calibration_record_id=OuterRef("pk"))))

    def create(self, request, *args, **kwargs):
        ser = CalibrationRecordCreateSerializer(data=request.data, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        data = dict(ser.validated_data)
        equipment = data.pop("equipment")
        rec = services.record_calibration(request=request, facility=self.ctx.facility, equipment=equipment, data=data)
        return Response(CalibrationRecordSerializer(rec, context=self.get_serializer_context()).data, status=201)

    @action(detail=True, methods=["post"], url_path="review-impact")
    def review_impact(self, request, *args, **kwargs):
        rec = self.get_object()
        ser = ImpactReviewSerializer(data=request.data, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        services.review_impact(request=request, record=rec, notes=ser.validated_data["review_notes"],
                               patient_impact_found=ser.validated_data["patient_impact_found"])
        rec = self.get_object()
        return Response(CalibrationRecordSerializer(rec, context=self.get_serializer_context()).data, status=201)


class WarrantyViewSet(FacilityScopedViewSet):
    queryset = Warranty.objects.all()
    serializer_class = WarrantySerializer
    required_permissions = {**_perms("warranty"), "bulk": "warranty.add"}
    include_inactive_permission = "warranty.delete"
    filterset_class = WarrantyFilter
    ordering_fields = ["end_date", "start_date", "created_at"]
    ordering = ["end_date", "id"]

    def scope_queryset(self, qs):
        return qs.select_related("equipment", "vendor")

    def check_can_modify(self, instance, action):
        if action == "SOFT_DELETE" and WarrantyClaim.objects.filter(
                facility_id=instance.facility_id, warranty_id=instance.pk, is_active=True).exists():
            raise Conflict("This warranty has active claims. Remove them first.")

    @action(detail=False, methods=["post"])
    def bulk(self, request):
        ser = BulkWarrantySerializer(data=request.data, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        d = dict(ser.validated_data)
        eqs = d.pop("equipment_list")
        d.pop("equipment")
        n = services.bulk_create_warranties(request=request, facility=self.ctx.facility, equipment_list=eqs, common=d)
        return Response({"created": n}, status=201)


class WarrantyClaimViewSet(FacilityScopedViewSet):
    queryset = WarrantyClaim.objects.all()
    serializer_class = WarrantyClaimSerializer
    required_permissions = _perms("warranty")
    include_inactive_permission = "warranty.delete"
    filterset_class = WarrantyClaimFilter
    ordering_fields = ["claim_date", "created_at"]
    ordering = ["-claim_date", "-id"]

    def scope_queryset(self, qs):
        return qs.select_related("warranty", "equipment", "work_order")


class AmcContractViewSet(FacilityScopedViewSet):
    queryset = AmcContract.objects.all()
    serializer_class = AmcContractSerializer
    required_permissions = {**_perms("amc"), "coverage": "amc.change", "renew": "amc.add"}
    include_inactive_permission = "amc.delete"
    filterset_class = AmcContractFilter
    ordering_fields = ["end_date", "start_date", "contract_number", "created_at"]
    ordering = ["end_date", "id"]

    def get_serializer_class(self):
        return AmcContractDetailSerializer if self.action in ("retrieve", "coverage", "renew") else AmcContractSerializer

    def scope_queryset(self, qs):
        n = AmcCoverage.objects.filter(amc_contract_id=OuterRef("pk")).values("amc_contract_id") \
            .annotate(c=Count("id")).values("c")[:1]
        return qs.select_related("vendor", "renewed_from_contract").annotate(
            equipment_count=Coalesce(Subquery(n, output_field=IntegerField()), 0))

    @action(detail=True, methods=["put"])
    def coverage(self, request, *args, **kwargs):
        c = self.get_object()
        ser = CoverageSetSerializer(data=request.data, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        services.set_coverage(request=request, facility=self.ctx.facility, contract=c, items=ser.validated_data["items"])
        return Response(AmcContractDetailSerializer(self.get_object(), context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def renew(self, request, *args, **kwargs):
        c = self.get_object()
        ser = AmcRenewSerializer(data=request.data, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        d = {k: v for k, v in ser.validated_data.items() if v not in (None, "")}
        new = services.renew_contract(request=request, facility=self.ctx.facility, contract=c, **d)
        return Response(AmcContractDetailSerializer(new, context=self.get_serializer_context()).data, status=201)


class EquipmentLicenceViewSet(FacilityScopedViewSet):
    queryset = EquipmentLicence.objects.all()
    serializer_class = EquipmentLicenceSerializer
    required_permissions = {**_perms("licence"), "renew": "licence.add"}
    include_inactive_permission = "licence.delete"
    filterset_class = EquipmentLicenceFilter
    ordering_fields = ["expiry_date", "issue_date", "created_at"]
    ordering = ["expiry_date", "id"]

    def scope_queryset(self, qs):
        return qs.select_related("equipment", "renewed_from_licence")

    @action(detail=True, methods=["post"])
    def renew(self, request, *args, **kwargs):
        lic = self.get_object()
        ser = LicenceRenewSerializer(data=request.data, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        d = {k: v for k, v in ser.validated_data.items() if v not in (None, "")}
        new = services.renew_licence(request=request, facility=self.ctx.facility, licence=lic, **d)
        return Response(EquipmentLicenceSerializer(new, context=self.get_serializer_context()).data, status=201)


class EquipmentCoverageViewSet(ReadOnlyScopedViewSet):
    """GET /equipment/{public_id}/coverage/?on=YYYY-MM-DD"""
    queryset = Equipment.objects.all()
    required_permissions = {"coverage": "equipment.view"}

    def coverage(self, request, public_id):
        fac = self.ctx.facility
        eq = Equipment.objects.filter(public_id=public_id, facility_id=fac.id, is_active=True).first()
        if eq is None:
            raise NotFound()
        raw = request.query_params.get("on")
        try:
            on = date.fromisoformat(raw) if raw else today_for(fac)
        except ValueError:
            raise ValidationError({"on": ["Use the format YYYY-MM-DD."]})
        return Response(services.suggest_coverage(eq, on))


class ComplianceDueViewSet(ReadOnlyScopedViewSet):
    """GET /compliance/due/. Gate is calibration.view (see assumptions); each type is filtered by its own view code."""
    queryset = CalibrationSchedule.objects.none()
    required_permissions = {"list": ()}   # signed in; "any one view code" is checked in list()
    BUCKETS = ("OVERDUE", "D7", "D30", "D60", "D90")

    def list(self, request, *args, **kwargs):
        if not any(self.ctx.has(code) for code in services.TYPE_PERMS.values()):
            deny(request, self, "list", list(services.TYPE_PERMS.values()))
        q = request.query_params
        types = [t.strip().upper() for raw in q.getlist("types") for t in raw.split(",") if t.strip()]
        bad = [t for t in types if t not in services.TYPE_PERMS]
        if bad:
            raise ValidationError({"types": [f"Unknown type {bad[0]}."]})
        try:
            within = int(q.get("within_days", 90))
        except ValueError:
            raise ValidationError({"within_days": ["Must be a whole number."]})
        if not 0 <= within <= 365:
            raise ValidationError({"within_days": ["Must be between 0 and 365."]})
        bucket = (q.get("bucket") or "").upper() or None
        if bucket and bucket not in self.BUCKETS:
            raise ValidationError({"bucket": ["Unknown bucket."]})
        fac = self.ctx.facility
        eq_pk = dept_pk = None
        if q.get("equipment"):
            eq = _by_public_id(Equipment, q["equipment"], fac.id, "equipment")
            if eq is None:
                return self.get_paginated_response(self.paginate_queryset([]))
            eq_pk = eq.pk
        if q.get("department"):
            dept = _by_public_id(Department, q["department"], fac.id, "department")
            if dept is None:
                return self.get_paginated_response(self.paginate_queryset([]))
            dept_pk = dept.pk
        rows = services.compliance_due(facility=fac, can=self.ctx.has, types=types or None, within_days=within,
                                       bucket=bucket, equipment_pk=eq_pk, department_pk=dept_pk)
        return self.get_paginated_response(self.paginate_queryset(rows))