from django.db import transaction
from django.http import HttpResponse
from django.db.models import Q
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
import barcode
from apps.foundation.models import User
from apps.foundation.viewsets import FacilityScopedViewSet

from . import importer, labels, services
from .errors import Conflict
from .filters import EquipmentFilter
from .models import Equipment, EquipmentMovement, EquipmentStateHistory
from .serializers import (
    CommissionSerializer, EquipmentBulkCreateSerializer, EquipmentCreateSerializer, EquipmentDetailSerializer,
    EquipmentListSerializer, EquipmentSummarySerializer, EquipmentUpdateSerializer, InstallSerializer,
    LabelsSerializer, MoveSerializer, OperationalStateSerializer, RejectSerializer, ref,
)

SELECT_RELATED = (
    "equipment_model__category", "equipment_model__manufacturer", "owning_department", "current_location",
    "supplier_vendor", "owner_vendor", "funding_source",
)


def _usernames(ids):
    ids = {i for i in ids if i is not None}
    return dict(User.objects.filter(id__in=ids).values_list("id", "username")) if ids else {}


def _file_response(content, content_type, filename=None):
    resp = HttpResponse(content, content_type=content_type)
    resp["Cache-Control"] = "private, no-store"
    if filename:
        resp["Content-Disposition"] = f'inline; filename="{filename}"'
    return resp


class EquipmentViewSet(FacilityScopedViewSet):
    queryset = Equipment.objects.all()
    audit_entity_type = "Equipment"
    filterset_class = EquipmentFilter
    ordering_fields = ["asset_tag", "name", "lifecycle_stage", "operational_state", "criticality",
                       "invoice_date", "created_at"]
    ordering = ["-created_at", "-id"]
    include_inactive_permission = "equipment.delete"
    required_permissions = {
        "list": "equipment.view", "retrieve": "equipment.view",
        "create": "equipment.add", "bulk_create": "equipment.add",
        "update": "equipment.change", "partial_update": "equipment.change",
        "destroy": "equipment.delete",
        "install": "equipment.transition", "commission": "equipment.transition",
        "reject": "equipment.transition", "set_operational_state": "equipment.transition",
        "move": "equipment.transition",
      "state_history": "equipment.view", "movements": "equipment.view", "holds": "equipment.view",
        "qr": "equipment.view", "barcode": "equipment.view", "labels": "equipment.view", "scan": "equipment.view",
        "import_template": "equipment.import", "import_dry_run": "equipment.import",
        "import_confirm": "equipment.import",
    }

    # ------------------------------------------------------------ plumbing
    def scope_queryset(self, queryset):
        return super().scope_queryset(queryset).select_related(*SELECT_RELATED)

    def get_serializer_class(self):
        a = self.action
        if a == "list":
            summary = str(self.request.query_params.get("summary", "")).lower() in ("1", "true")
            return EquipmentSummarySerializer if summary else EquipmentListSerializer
        if a == "create":
            return EquipmentCreateSerializer
        if a in ("update", "partial_update"):
            return EquipmentUpdateSerializer
        if a == "bulk_create":
            return EquipmentBulkCreateSerializer
        return EquipmentDetailSerializer

    def check_can_modify(self, instance, action):
        if action == "SOFT_DELETE" and instance.lifecycle_stage not in ("RECEIVED", "REJECTED"):
            raise Conflict("Only equipment that is Received or Rejected can be deleted.")

    def _detail(self, pk):
        return EquipmentDetailSerializer(self.get_queryset().get(pk=pk), context=self.get_serializer_context()).data

    # ------------------------------------------------------------ create
    def create(self, request, *args, **kwargs):
        self.reject_unknown_fields(request.data)
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            eq = services.register(request=request, facility=self.ctx.facility, fields=dict(ser.validated_data))
        return Response(self._detail(eq.pk), status=201)

    @action(detail=False, methods=["post"], url_path="bulk-create")
    def bulk_create(self, request):
        self.reject_unknown_fields(request.data)
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = dict(ser.validated_data)
        qty = data.pop("quantity")
        serials = data.pop("serial_numbers", None)
        names = data.pop("names", None)
        with transaction.atomic():
            created = services.bulk_register(request=request, facility=self.ctx.facility, fields=data,
                                             quantity=qty, serial_numbers=serials, names=names)
        return Response({
            "count": len(created),
            "results": [{"public_id": str(e.public_id), "asset_tag": e.asset_tag, "name": e.name} for e in created],
        }, status=201)

    # ------------------------------------------------------------ transitions
    def _run(self, request, ser_cls, call):
        ser = ser_cls(data=request.data, context=self.get_serializer_context())
        self.reject_unknown_fields(request.data, allowed=set(ser.fields) | {"row_version"})
        ser.is_valid(raise_exception=True)
        version = self.parse_row_version(request.data.get("row_version"))
        with transaction.atomic():
            eq = self.get_object_for_update()
            call(eq, dict(ser.validated_data), version)
        return Response(self._detail(eq.pk))

    @action(detail=True, methods=["post"])
    def install(self, request, public_id=None):
        return self._run(request, InstallSerializer, lambda eq, d, v: services.install(
            request=request, equipment=eq, expected_version=v, **d))

    @action(detail=True, methods=["post"])
    def commission(self, request, public_id=None):
        return self._run(request, CommissionSerializer, lambda eq, d, v: services.commission(
            request=request, equipment=eq, expected_version=v, **d))

    @action(detail=True, methods=["post"])
    def reject(self, request, public_id=None):
        return self._run(request, RejectSerializer, lambda eq, d, v: services.reject(
            request=request, equipment=eq, expected_version=v, reason=d["reason"]))

    @action(detail=True, methods=["post"], url_path="set-operational-state")
    def set_operational_state(self, request, public_id=None):
        return self._run(request, OperationalStateSerializer, lambda eq, d, v: services.set_operational_state(
            request=request, equipment=eq, expected_version=v,
            operational_state=d["operational_state"], reason=d["reason"]))

    @action(detail=True, methods=["post"])
    def move(self, request, public_id=None):
        return self._run(request, MoveSerializer, lambda eq, d, v: services.move_equipment(
            request=request, equipment=eq, expected_version=v, to_location=d["location"],
            to_department=d.get("department"), reason=d["reason"]))

    # ------------------------------------------------------------ histories
    @action(detail=True, methods=["get"], url_path="state-history")
    def state_history(self, request, public_id=None):
        eq = self.get_object()
        qs = EquipmentStateHistory.objects.filter(facility_id=eq.facility_id, equipment_id=eq.pk) \
            .order_by("-created_at", "-id")
        page = self.paginate_queryset(qs)
        names = _usernames(r.created_by for r in page)
        return self.get_paginated_response([{
            "public_id": str(r.public_id), "change_type": r.change_type, "from_value": r.from_value,
            "to_value": r.to_value, "reason": r.reason, "created_at": r.created_at,
            "created_by": names.get(r.created_by),
        } for r in page])

    @action(detail=True, methods=["get"])
    def movements(self, request, public_id=None):
        eq = self.get_object()
        qs = EquipmentMovement.objects.filter(facility_id=eq.facility_id, equipment_id=eq.pk) \
            .select_related("from_location", "to_location", "from_department", "to_department") \
            .order_by("-moved_at", "-id")
        page = self.paginate_queryset(qs)
        names = _usernames(r.created_by for r in page)
        return self.get_paginated_response([{
            "public_id": str(r.public_id),
            "from_location": ref(r.from_location, "code", "name"), "to_location": ref(r.to_location, "code", "name"),
            "from_department": ref(r.from_department, "code", "name"),
            "to_department": ref(r.to_department, "code", "name"),
            "reason": r.reason, "moved_at": r.moved_at, "created_by": names.get(r.created_by),
        } for r in page])

    # ------------------------------------------------------------ QR / barcode / labels / scan
    @action(detail=True, methods=["get"])
    def holds(self, request, public_id=None):
        from apps.maintenance.models import EquipmentHold          # lazy import: no circular dependency
        from apps.maintenance.serializers import hold_repr
        eq = self.get_object()
        qs = EquipmentHold.objects.filter(facility_id=eq.facility_id, equipment_id=eq.pk) \
            .select_related("work_order").order_by("-started_at", "-id")
        page = self.paginate_queryset(qs)
        return self.get_paginated_response([hold_repr(h) for h in page])


    @action(detail=True, methods=["get"])
    def qr(self, request, public_id=None):
        eq = self.get_object()
        return _file_response(labels.qr_png(eq.qr_code_value), "image/png")

    @action(detail=True, methods=["get"])
    def barcode(self, request, public_id=None):
        eq = self.get_object()
        return _file_response(labels.barcode_png(eq.asset_tag), "image/png")

    @action(detail=False, methods=["post"])
    def labels(self, request):
        self.reject_unknown_fields(request.data, allowed={"equipment"})
        ser = LabelsSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ids = list(dict.fromkeys(ser.validated_data["equipment"]))
        rows = {e.public_id: e for e in self.get_queryset().filter(public_id__in=ids)}
        if len(rows) != len(ids):
            raise NotFound()   # unknown or other-facility ids: no hint which
        pdf = labels.labels_pdf((rows[i].asset_tag, rows[i].name, rows[i].qr_code_value) for i in ids)
        return _file_response(pdf, "application/pdf", "labels.pdf")

    @action(detail=False, methods=["get"], url_path=r"scan/(?P<code>[A-Za-z0-9_-]{1,100})")
    def scan(self, request, code=None):
        code = (code or "").strip()
        eq = self.get_queryset().filter(
            Q(qr_code_value=code.upper()) | Q(asset_tag=code.upper()) | Q(legacy_asset_id__iexact=code)
        ).order_by("id").first()
        if eq is None:
            raise NotFound()
        return Response(self._detail(eq.pk))

    # ------------------------------------------------------------ import
    def _import_inputs(self, request):
        extra = set(request.data.keys()) - {"file", "mapping"}
        if extra:
            raise ValidationError({name: ["Unknown field."] for name in sorted(extra)})
        return request.FILES.get("file"), request.data.get("mapping")

    @action(detail=False, methods=["get"], url_path="import/template")
    def import_template(self, request):
        resp = HttpResponse(importer.template_csv(), content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="equipment_import_template.csv"'
        return resp

    @action(detail=False, methods=["post"], url_path="import/dry-run", parser_classes=[MultiPartParser])
    def import_dry_run(self, request):
        upload, mapping = self._import_inputs(request)
        result, _ = importer.analyse(self.ctx.facility, upload, mapping)
        return Response(result)

    @action(detail=False, methods=["post"], url_path="import", parser_classes=[MultiPartParser])
    def import_confirm(self, request):
        upload, mapping = self._import_inputs(request)
        result, parsed = importer.analyse(self.ctx.facility, upload, mapping)
        if result["errors"] or result["missing_models"] or result["missing_columns"]:
            raise ValidationError({"file": ["The file has errors. Nothing was imported. Run the dry-run and fix them."]})
        tags = importer.commit(request, self.ctx.facility, parsed)
        return Response({"imported": len(tags), "first_asset_tag": tags[0], "last_asset_tag": tags[-1]}, status=201)
