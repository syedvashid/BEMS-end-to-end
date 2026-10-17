from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.allocation.models import EquipmentAllocation
from apps.equipment.models import Equipment
from apps.foundation.models import User
from apps.foundation.viewsets import FacilityScopedViewSet
from apps.reports.common import facility_today, facility_tz, paginate, parse_date, parse_uuid

from . import gates, services
from .filters import ChargeItemFilter, ChargeMappingFilter, ChargeRecordFilter
from .models import ChargeItem, ChargeMapping, ChargeRecord
from .serializers import (
    BulkIdsSerializer, CalculatorSerializer, ChargeItemSerializer, ChargeMappingSerializer, MarkExportedSerializer,
    ReasonSerializer, SettingsSerializer, record_repr,
)

RECORD_RELATED = ("equipment", "charge_item", "charge_mapping", "department", "allocation", "usage_log",
                  "reverses_record", "corrects_record")


def usernames(ids):
    ids = {i for i in ids if i is not None}
    return dict(User.objects.filter(id__in=ids).values_list("id", "username")) if ids else {}


def _equipment_or_404(request, public_id):
    eq = (Equipment.objects.select_related("equipment_model")
          .filter(facility_id=request.bems.facility.id, public_id=public_id, is_active=True).first())
    if eq is None:
        raise NotFound()
    return eq


def _equipment_out(eq):
    return {"public_id": str(eq.public_id), "asset_tag": eq.asset_tag, "name": eq.name}


# ================================================================== items and mappings
class ChargeItemViewSet(FacilityScopedViewSet):
    queryset = ChargeItem.objects.all()
    serializer_class = ChargeItemSerializer
    audit_entity_type = "ChargeItem"
    required_permissions = {"list": "charge.view", "retrieve": "charge.view", "create": "charge.configure",
                            "update": "charge.configure", "partial_update": "charge.configure",
                            "destroy": "charge.configure"}
    include_inactive_permission = "charge.configure"
    filterset_class = ChargeItemFilter
    ordering_fields = ["item_code", "name", "default_rate", "created_at"]
    ordering = ["item_code"]

    def check_can_modify(self, instance, action):
        if action == "SOFT_DELETE":
            gates.ensure_item_deletable(instance)


class ChargeMappingViewSet(FacilityScopedViewSet):
    queryset = ChargeMapping.objects.select_related("equipment", "category", "charge_item")
    serializer_class = ChargeMappingSerializer
    audit_entity_type = "ChargeMapping"
    required_permissions = {"list": "charge.view", "retrieve": "charge.view", "resolve": "charge.view",
                            "create": "charge.configure", "update": "charge.configure",
                            "partial_update": "charge.configure", "destroy": "charge.configure"}
    include_inactive_permission = "charge.configure"
    filterset_class = ChargeMappingFilter
    ordering_fields = ["effective_from", "billing_rule", "created_at"]
    ordering = ["-effective_from", "-id"]

    @action(detail=False, methods=["get"], url_path="resolve")
    def resolve(self, request):
        eq = _equipment_or_404(request, parse_uuid(request.query_params.get("equipment"), "equipment"))
        raw_on = request.query_params.get("on")
        on = parse_date(raw_on, "on") if raw_on else facility_today(request.bems.facility)
        mapping, level = services.resolve_mapping(eq, on)
        return Response({"equipment": _equipment_out(eq), "on": on, "level": level,
                         "mapping": services.mapping_out(mapping, level) if mapping else None})


class ChargeSettingsView(APIView):
    required_permissions = {"get": "charge.view", "put": "charge.configure"}

    def get(self, request):
        return Response(services.get_settings(request.bems.facility))

    def put(self, request):
        ser = SettingsSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        return Response(services.set_auto_approve(request=request, value=ser.validated_data["auto_approve"]))


class ChargeCalculatorView(APIView):
    required_permissions = {"post": "charge.view"}

    def post(self, request):
        ser = CalculatorSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        return Response(services.calculate(request.bems.facility, ser.validated_data))


# ================================================================== charge records
class ChargeRecordViewSet(FacilityScopedViewSet):
    """Read-only list and detail plus the status actions. A record is never created, edited or deleted here."""
    queryset = ChargeRecord.objects.select_related(*RECORD_RELATED)
    serializer_class = ReasonSerializer            # only used by reject_unknown_fields; list/detail use record_repr
    audit_entity_type = "ChargeRecord"
    http_method_names = ["get", "post", "head"]
    filterset_class = ChargeRecordFilter
    ordering_fields = ["charge_date", "record_number", "amount", "status", "created_at"]
    ordering = ["-charge_date", "-id"]
    required_permissions = {
        "list": "charge.view", "retrieve": "charge.view", "approve": "charge.approve", "cancel": "charge.approve",
        "reverse": "charge.approve", "recalculate": "charge.approve", "approve_bulk": "charge.approve",
        "mark_exported": "charge.approve"}

    @staticmethod
    def _user_ids(r):
        return [r.approved_by, r.cancelled_by, r.exported_by, r.created_by]

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        names = usernames(i for r in page for i in self._user_ids(r))
        return self.get_paginated_response([record_repr(r, names) for r in page])

    def retrieve(self, request, *args, **kwargs):
        return Response(self._one(self.get_object()))

    def _one(self, rec):
        rec = ChargeRecord.objects.select_related(*RECORD_RELATED).get(pk=rec.pk)
        return record_repr(rec, usernames(self._user_ids(rec)), detail=True)

    @action(detail=True, methods=["post"])
    def approve(self, request, public_id=None):
        self.reject_unknown_fields(request.data, allowed=set())
        return Response(self._one(services.approve(request=request, record=self.get_object())))

    @action(detail=True, methods=["post"])
    def cancel(self, request, public_id=None):
        ser = ReasonSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        return Response(self._one(services.cancel(request=request, record=self.get_object(),
                                                  reason=ser.validated_data["reason"])))

    @action(detail=True, methods=["post"])
    def reverse(self, request, public_id=None):
        ser = ReasonSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        original, reversal = services.reverse(request=request, record=self.get_object(),
                                              reason=ser.validated_data["reason"])
        return Response({"original": self._one(original), "reversal": self._one(reversal)})

    @action(detail=True, methods=["post"])
    def recalculate(self, request, public_id=None):
        self.reject_unknown_fields(request.data, allowed=set())
        return Response(self._one(services.recalculate(request=request, record=self.get_object())), status=201)

    @action(detail=False, methods=["post"], url_path="approve")
    def approve_bulk(self, request):
        ser = BulkIdsSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        res = services.approve_many(request=request, public_ids=ser.validated_data["ids"])
        return Response({"approved": [{"public_id": str(r.public_id), "record_number": r.record_number}
                                      for r in res["approved"]], "skipped": res["skipped"]})

    @action(detail=False, methods=["post"], url_path="mark-exported")
    def mark_exported(self, request):
        ser = MarkExportedSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if "ids" in d:
            res = services.mark_exported(request=request, export_reference=d["export_reference"],
                                         public_ids=d["ids"])
        else:
            fs = ChargeRecordFilter(data=d["filters"], queryset=self.get_queryset(), request=request)
            unknown = sorted(set(d["filters"]) - set(fs.filters))
            if unknown:
                raise ValidationError({"filters": [f"Unknown filter: {', '.join(unknown)}."]})
            if not fs.is_valid():
                raise ValidationError({"filters": fs.errors})
            res = services.mark_exported(request=request, export_reference=d["export_reference"], queryset=fs.qs)
        return Response(res)


# ================================================================== preview and equipment tab
class AllocationChargePreviewView(APIView):
    required_permissions = {"get": "charge.view"}

    def get(self, request, public_id):
        alloc = (EquipmentAllocation.objects.select_related("facility", "equipment__equipment_model")
                 .filter(facility_id=request.bems.facility.id, public_id=public_id, is_active=True).first())
        if alloc is None:
            raise NotFound()
        at = None
        raw = request.query_params.get("at")
        if raw:
            at = parse_datetime(raw)
            if at is None:
                raise ValidationError({"at": ["Enter a valid date and time (ISO 8601)."]})
            if timezone.is_naive(at):
                at = timezone.make_aware(at, facility_tz(request.bems.facility))
        return Response(services.preview_for_allocation(alloc, at=at))


class EquipmentChargesView(APIView):
    required_permissions = {"get": "charge.view"}

    def get(self, request, public_id):
        eq = _equipment_or_404(request, public_id)
        today = facility_today(request.bems.facility)
        mapping, level = services.resolve_mapping(eq, today)
        qs = (ChargeRecord.objects.select_related(*RECORD_RELATED)
              .filter(facility_id=eq.facility_id, equipment_id=eq.pk, is_active=True).order_by("-charge_date", "-id"))
        page = paginate(request, qs)
        names = usernames(i for r in page["results"] for i in
                          [r.approved_by, r.cancelled_by, r.exported_by, r.created_by])
        page["results"] = [record_repr(r, names) for r in page["results"]]
        return Response({"equipment": _equipment_out(eq), "today": today, "level": level,
                         "mapping": services.mapping_out(mapping, level) if mapping else None, "records": page})
