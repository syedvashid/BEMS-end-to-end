from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from apps.core.errors import Conflict
from apps.equipment.models import Equipment
from apps.foundation.viewsets import UUID_RE, FacilityScopedViewSet

from . import services
from .filters import (
    IncidentFilter, RecallNoticeFilter, RecallUnitFilter, VerificationFilter, VerificationItemFilter,
)
from .models import (
    EquipmentIncident, PhysicalVerification, PhysicalVerificationItem, RecallAffectedUnit, RecallNotice,
)
from .serializers import (
    AddUnitSerializer, EmptyActionSerializer, IdentifyUnitsSerializer, IncidentActionsTakenSerializer, IncidentCloseSerializer,
    IncidentCreateSerializer, IncidentDetailSerializer, IncidentListSerializer, IncidentMarkReportedSerializer,
    IncidentReleaseSerializer, IncidentUpdateSerializer, ItemResolveSerializer, ItemUpdateSerializer,
    NoteSerializer, NoticeCloseSerializer, ReasonSerializer, RecallCreateSerializer, RecallDetailSerializer,
    RecallListSerializer, RecallUpdateSerializer, ResolveUnitSerializer, ScanSerializer,
    VerificationCreateSerializer, VerificationDetailSerializer, VerificationListSerializer,
    VerificationUpdateSerializer, equipment_brief, item_repr, unit_repr,
)


class _SafetyViewSet(FacilityScopedViewSet):
    """No PUT, no DELETE: incidents, notices and verifications are closed or cancelled, never deleted."""
    http_method_names = ["get", "post", "patch", "head"]

    def _run(self, ser_cls, call):
        """Validate the body, pop the optional row_version, call the service, return the detail."""
        ser = ser_cls(data=self.request.data, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        data = dict(ser.validated_data)
        version = data.pop("row_version", None)
        return call(data, version)

    def _filtered(self, filterset_cls, qs):
        fs = filterset_cls(self.request.query_params, queryset=qs, request=self.request)
        if not fs.is_valid():
            raise ValidationError(fs.errors)
        return fs.qs

    def _detail(self, pk):
        return self.get_serializer_class()(self.get_queryset().get(pk=pk), context=self.get_serializer_context()).data


# ================================================================== incidents
class IncidentViewSet(_SafetyViewSet):
    queryset = EquipmentIncident.objects.all()
    audit_entity_type = "EquipmentIncident"
    filterset_class = IncidentFilter
    ordering_fields = ["incident_number", "occurred_at", "severity", "status", "created_at"]
    ordering = ["-occurred_at", "-id"]
    required_permissions = {
        "list": "incident.view", "retrieve": "incident.view", "create": "incident.add",
        "partial_update": "incident.manage", "start_investigation": "incident.manage",
        "actions_taken": "incident.manage", "close": "incident.manage", "mark_reported": "incident.manage",
        "release_quarantine": "incident.manage", "create_work_order": "incident.manage", "notes": "incident.manage",
    }

    def scope_queryset(self, queryset):
        return super().scope_queryset(queryset).select_related("equipment", "department", "location", "work_order")

    def get_serializer_class(self):
        return IncidentListSerializer if self.action == "list" else IncidentDetailSerializer

    def create(self, request, *args, **kwargs):
        ser = IncidentCreateSerializer(data=request.data, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        inc, quarantine = services.report_incident(request=request, facility=self.ctx.facility,
                                                   data=dict(ser.validated_data))
        return Response({**self._detail(inc.pk), "quarantine": quarantine}, status=201)

    def partial_update(self, request, *args, **kwargs):
        ser = IncidentUpdateSerializer(data=request.data, partial=True, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        version = self.parse_row_version(request.data.get("row_version"))
        fields = dict(ser.validated_data)
        fields.pop("row_version", None)
        inc = self.get_object()
        services.update_incident(request=request, incident=inc, expected_version=version, fields=fields)
        return Response(self._detail(inc.pk))

    @action(detail=True, methods=["post"], url_path="start-investigation")
    def start_investigation(self, request, public_id=None):
        inc = self.get_object()
        self._run(EmptyActionSerializer, lambda d, v: services.start_investigation(
            request=request, incident=inc, expected_version=v))
        return Response(self._detail(inc.pk))

    @action(detail=True, methods=["post"], url_path="actions-taken")
    def actions_taken(self, request, public_id=None):
        inc = self.get_object()
        self._run(IncidentActionsTakenSerializer, lambda d, v: services.record_actions(
            request=request, incident=inc, corrective_action=d.get("corrective_action"), expected_version=v))
        return Response(self._detail(inc.pk))

    @action(detail=True, methods=["post"])
    def close(self, request, public_id=None):
        inc = self.get_object()
        try:
            self._run(IncidentCloseSerializer, lambda d, v: services.close_incident(
                request=request, incident=inc, closure_notes=d["closure_notes"], expected_version=v))
        except Conflict as exc:   # the atomic block has already rolled back: audit the refusal in autocommit
            services.audit_refused(request, "INCIDENT_CLOSE_REFUSED", services.INCIDENT, inc, exc)
            raise
        return Response(self._detail(inc.pk))

    @action(detail=True, methods=["post"], url_path="mark-reported")
    def mark_reported(self, request, public_id=None):
        inc = self.get_object()
        self._run(IncidentMarkReportedSerializer, lambda d, v: services.mark_regulator_reported(
            request=request, incident=inc, reference=d["reference"], reported_on=d["reported_on"],
            expected_version=v))
        return Response(self._detail(inc.pk))

    @action(detail=True, methods=["post"], url_path="release-quarantine")
    def release_quarantine(self, request, public_id=None):
        inc = self.get_object()
        self._run(IncidentReleaseSerializer, lambda d, v: services.release_quarantine(
            request=request, incident=inc, reason=d["reason"], expected_version=v))
        return Response(self._detail(inc.pk))

    @action(detail=True, methods=["post"], url_path="create-work-order")
    def create_work_order(self, request, public_id=None):
        inc = self.get_object()
        self._run(EmptyActionSerializer, lambda d, v: services.create_incident_work_order(
            request=request, incident=inc, expected_version=v))
        return Response(self._detail(inc.pk))

    @action(detail=True, methods=["post"])
    def notes(self, request, public_id=None):
        inc = self.get_object()
        self._run(NoteSerializer, lambda d, v: services.add_incident_note(request=request, incident=inc, text=d["text"]))
        return Response(self._detail(inc.pk), status=201)


# ================================================================== recall notices
class RecallNoticeViewSet(_SafetyViewSet):
    queryset = RecallNotice.objects.all()
    audit_entity_type = "RecallNotice"
    filterset_class = RecallNoticeFilter
    ordering_fields = ["notice_number", "title", "urgency", "status", "issued_date", "created_at"]
    ordering = ["-created_at", "-id"]
    required_permissions = {
        "list": "recall.view", "retrieve": "recall.view", "create": "recall.add", "partial_update": "recall.manage",
        "identify_units": "recall.manage", "close": "recall.manage", "cancel": "recall.manage",
        "units": "recall.view", "add_unit": "recall.manage", "resolve_unit": "recall.manage",
        "create_unit_work_order": "recall.manage",
    }

    def scope_queryset(self, queryset):
        return super().scope_queryset(queryset).select_related("issued_by_vendor")

    def get_serializer_class(self):
        return RecallListSerializer if self.action == "list" else RecallDetailSerializer

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        counts = services.notice_counts([n.pk for n in page])
        ser = RecallListSerializer(page, many=True, context={**self.get_serializer_context(), "counts": counts})
        return self.get_paginated_response(ser.data)

    def create(self, request, *args, **kwargs):
        ser = RecallCreateSerializer(data=request.data, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        data = dict(ser.validated_data)
        models = data.pop("models")
        notice = services.create_notice(request=request, facility=self.ctx.facility, data=data, models=models)
        return Response(self._detail(notice.pk), status=201)

    def partial_update(self, request, *args, **kwargs):
        ser = RecallUpdateSerializer(data=request.data, partial=True, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        version = self.parse_row_version(request.data.get("row_version"))
        data = dict(ser.validated_data)
        data.pop("row_version", None)
        models = data.pop("models", None)
        notice = self.get_object()
        services.update_notice(request=request, notice=notice, expected_version=version, fields=data, models=models)
        return Response(self._detail(notice.pk))

    @action(detail=True, methods=["post"], url_path="identify-units")
    def identify_units(self, request, public_id=None):
        notice = self.get_object()
        result = self._run(IdentifyUnitsSerializer, lambda d, v: services.identify_units(
            request=request, notice=notice, mode=d["mode"], serial_numbers=d.get("serial_numbers")))
        return Response(result)

    @action(detail=True, methods=["post"])
    def close(self, request, public_id=None):
        notice = self.get_object()
        try:
            self._run(NoticeCloseSerializer, lambda d, v: services.close_notice(
                request=request, notice=notice, close_notes=d["close_notes"], expected_version=v))
        except Conflict as exc:
            services.audit_refused(request, "RECALL_CLOSE_REFUSED", services.NOTICE, notice, exc)
            raise
        return Response(self._detail(notice.pk))

    @action(detail=True, methods=["post"])
    def cancel(self, request, public_id=None):
        notice = self.get_object()
        self._run(ReasonSerializer, lambda d, v: services.cancel_notice(
            request=request, notice=notice, reason=d["reason"], expected_version=v))
        return Response(self._detail(notice.pk))

    # -------------------------------------------------------------- units
    def _unit(self, notice, public_id):
        unit = RecallAffectedUnit.objects.filter(
            facility_id=notice.facility_id, recall_notice_id=notice.pk, public_id=public_id, is_active=True).first()
        if unit is None:
            raise NotFound()
        return unit

    def _unit_data(self, unit_pk):
        u = RecallAffectedUnit.objects.select_related("equipment__current_location", "work_order").get(pk=unit_pk)
        return unit_repr(u, services.usernames([u.resolved_by]))

    @action(detail=True, methods=["get"], url_path="units")
    def units(self, request, public_id=None):
        notice = self.get_object()
        qs = RecallAffectedUnit.objects.filter(facility_id=notice.facility_id, recall_notice_id=notice.pk, is_active=True) \
            .select_related("equipment__current_location", "work_order")
        qs = self._filtered(RecallUnitFilter, qs).order_by("equipment__asset_tag", "id")
        page = self.paginate_queryset(qs)
        names = services.usernames(u.resolved_by for u in page)
        return self.get_paginated_response([unit_repr(u, names) for u in page])

    @units.mapping.post
    def add_unit(self, request, public_id=None):
        notice = self.get_object()
        ser = AddUnitSerializer(data=request.data, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        unit, info = services.add_unit(request=request, notice=notice, equipment=ser.validated_data["equipment"])
        return Response({**self._unit_data(unit.pk), **info}, status=201)

    @action(detail=True, methods=["post"], url_path=rf"units/(?P<unit>{UUID_RE})/resolve")
    def resolve_unit(self, request, public_id=None, unit=None):
        notice = self.get_object()
        row = self._unit(notice, unit)
        self._run(ResolveUnitSerializer, lambda d, v: services.resolve_unit(
            request=request, unit=row, status=d["status"], notes=d.get("notes"),
            vendor_reference=d.get("vendor_reference")))
        return Response(self._unit_data(row.pk))

    @action(detail=True, methods=["post"], url_path=rf"units/(?P<unit>{UUID_RE})/create-work-order")
    def create_unit_work_order(self, request, public_id=None, unit=None):
        notice = self.get_object()
        row = self._unit(notice, unit)
        if len(request.data):
            raise ValidationError({"non_field_errors": ["No fields are accepted."]})
        services.create_unit_work_order(request=request, unit=row)
        return Response(self._unit_data(row.pk))


# ================================================================== physical verification
class VerificationViewSet(_SafetyViewSet):
    queryset = PhysicalVerification.objects.all()
    audit_entity_type = "PhysicalVerification"
    filterset_class = VerificationFilter
    ordering_fields = ["verification_number", "title", "planned_date", "status", "created_at"]
    ordering = ["-created_at", "-id"]
    required_permissions = {
        "list": "verification.view", "retrieve": "verification.view", "create": "verification.add",
        "partial_update": "verification.add", "start": "verification.add", "scan": "verification.add",
        "complete": "verification.manage", "cancel": "verification.manage", "items": "verification.view",
        "update_item": "verification.add", "resolve_item": "verification.manage",
    }

    def scope_queryset(self, queryset):
        return super().scope_queryset(queryset).select_related("department", "location")

    def get_serializer_class(self):
        return VerificationListSerializer if self.action == "list" else VerificationDetailSerializer

    def create(self, request, *args, **kwargs):
        ser = VerificationCreateSerializer(data=request.data, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        v = services.create_verification(request=request, facility=self.ctx.facility, data=dict(ser.validated_data))
        return Response(self._detail(v.pk), status=201)

    def partial_update(self, request, *args, **kwargs):
        ser = VerificationUpdateSerializer(data=request.data, partial=True, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        version = self.parse_row_version(request.data.get("row_version"))
        fields = dict(ser.validated_data)
        fields.pop("row_version", None)
        v = self.get_object()
        services.update_verification(request=request, verification=v, expected_version=version, fields=fields)
        return Response(self._detail(v.pk))

    @action(detail=True, methods=["post"])
    def start(self, request, public_id=None):
        v = self.get_object()
        if len(request.data):
            raise ValidationError({"non_field_errors": ["No fields are accepted."]})
        services.start_verification(request=request, verification=v)
        return Response(self._detail(v.pk))

    @action(detail=True, methods=["post"])
    def scan(self, request, public_id=None):
        v = self.get_object()
        ser = ScanSerializer(data=request.data, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        item, eq, counters = services.scan(request=request, verification=v, code=ser.validated_data["code"],
                                           found_location=ser.validated_data.get("found_location"))
        row = PhysicalVerificationItem.objects.select_related(
            "equipment", "expected_location", "expected_department", "found_location").get(pk=item.pk)
        eq = Equipment.objects.select_related("current_location").get(pk=eq.pk)
        return Response({"item": item_repr(row, {request.user.id: request.user.username}),
                         "equipment": equipment_brief(eq), "counters": counters})

    @action(detail=True, methods=["post"])
    def complete(self, request, public_id=None):
        v = self.get_object()
        if len(request.data):
            raise ValidationError({"non_field_errors": ["No fields are accepted."]})
        services.complete_verification(request=request, verification=v)
        return Response(self._detail(v.pk))

    @action(detail=True, methods=["post"])
    def cancel(self, request, public_id=None):
        v = self.get_object()
        self._run(ReasonSerializer, lambda d, val: services.cancel_verification(
            request=request, verification=v, reason=d["reason"]))
        return Response(self._detail(v.pk))

    # -------------------------------------------------------------- items
    def _item(self, v, public_id):
        item = PhysicalVerificationItem.objects.filter(
            facility_id=v.facility_id, verification_id=v.pk, public_id=public_id, is_active=True).first()
        if item is None:
            raise NotFound()
        return item

    def _item_data(self, pk):
        i = PhysicalVerificationItem.objects.select_related(
            "equipment", "expected_location", "expected_department", "found_location").get(pk=pk)
        return item_repr(i, services.usernames([i.scanned_by, i.resolved_by]))

    @action(detail=True, methods=["get"], url_path="items")
    def items(self, request, public_id=None):
        v = self.get_object()
        qs = PhysicalVerificationItem.objects.filter(facility_id=v.facility_id, verification_id=v.pk, is_active=True) \
            .select_related("equipment", "expected_location", "expected_department", "found_location")
        qs = self._filtered(VerificationItemFilter, qs)
        if request.query_params.get("ordering") == "-scanned_at":
            qs = qs.order_by("-scanned_at", "-id")
        else:
            qs = qs.order_by("equipment__asset_tag", "id")
        page = self.paginate_queryset(qs)
        names = services.usernames([i.scanned_by for i in page] + [i.resolved_by for i in page])
        return self.get_paginated_response([item_repr(i, names) for i in page])

    @action(detail=True, methods=["patch"], url_path=rf"items/(?P<item>{UUID_RE})")
    def update_item(self, request, public_id=None, item=None):
        v = self.get_object()
        row = self._item(v, item)
        ser = ItemUpdateSerializer(data=request.data, partial=True, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        version = self.parse_row_version(request.data.get("row_version"))
        d = ser.validated_data
        services.update_item(request=request, verification=v, item=row, expected_version=version,
                             tag_status=d.get("tag_status"), notes=d.get("notes"), notes_given="notes" in d)
        return Response(self._item_data(row.pk))

    @action(detail=True, methods=["post"], url_path=rf"items/(?P<item>{UUID_RE})/resolve")
    def resolve_item(self, request, public_id=None, item=None):
        v = self.get_object()
        row = self._item(v, item)
        ser = ItemResolveSerializer(data=request.data, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        try:
            services.resolve_item(request=request, verification=v, item=row,
                                  resolution=ser.validated_data["resolution"], notes=ser.validated_data.get("notes"))
        except Conflict as exc:
            services.audit_refused(request, "VERIFICATION_ITEM_RESOLVE_REFUSED", services.ITEM, row, exc)
            raise
        return Response(self._item_data(row.pk))


# ================================================================== equipment safety tab
class EquipmentSafetyViewSet(FacilityScopedViewSet):
    """GET /equipment/{id}/safety/ : each part only for users who hold the matching view permission."""
    queryset = Equipment.objects.all()
    http_method_names = ["get", "head"]
    required_permissions = {"safety": "equipment.view"}

    def safety(self, request, public_id=None):
        eq = self.get_object()
        can_inc, can_rec = self.ctx.has("incident.view"), self.ctx.has("recall.view")
        incidents = recall_units = None
        if can_inc:
            rows = EquipmentIncident.objects.filter(facility_id=eq.facility_id, equipment_id=eq.pk, is_active=True) \
                .order_by("-occurred_at", "-id")[:20]
            incidents = [{"public_id": str(i.public_id), "incident_number": i.incident_number,
                          "incident_type": i.incident_type, "severity": i.severity, "status": i.status,
                          "occurred_at": i.occurred_at} for i in rows]
        if can_rec:
            rows = RecallAffectedUnit.objects.filter(facility_id=eq.facility_id, equipment_id=eq.pk, is_active=True) \
                .select_related("recall_notice").order_by("-created_at", "-id")[:50]
            recall_units = [{"public_id": str(u.public_id), "status": u.status,
                             "notice": {"public_id": str(u.recall_notice.public_id),
                                        "notice_number": u.recall_notice.notice_number,
                                        "title": u.recall_notice.title, "urgency": u.recall_notice.urgency,
                                        "status": u.recall_notice.status, "stop_use": u.recall_notice.stop_use}}
                            for u in rows]
        return Response({"incidents": incidents, "recall_units": recall_units})
