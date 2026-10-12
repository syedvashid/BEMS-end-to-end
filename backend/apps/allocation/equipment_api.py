import uuid
from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.equipment.serializers import ref
from apps.masters.models import Department, EquipmentCategory, Location

from . import services
from .models import EquipmentUsageLog


def _dt(request, name):
    raw = request.query_params.get(name)
    if not raw:
        return None
    try:
        return serializers.DateTimeField().to_internal_value(raw)
    except serializers.ValidationError:
        raise ValidationError({name: ["A valid datetime is required."]})


def _window(request):
    start, end = _dt(request, "from"), _dt(request, "to")
    if end is not None and start is None:
        start = timezone.now()
    if start is not None and end is not None and end <= start:
        raise ValidationError({"to": ["Must be after the start."]})
    return start, end


def _scoped(model, request, name, required=False):
    raw = request.query_params.get(name)
    if not raw:
        if required:
            raise ValidationError({name: ["This field is required."]})
        return None
    try:
        pid = uuid.UUID(raw)
    except ValueError:
        raise ValidationError({name: ["Invalid value."]})
    obj = model.objects.filter(public_id=pid, facility_id=request.bems.facility.id, is_active=True).first()
    if obj is None:
        raise ValidationError({name: ["Unknown reference."]})
    return obj


def _row(e, cal):
    return {"public_id": str(e.public_id), "asset_tag": e.asset_tag, "name": e.name,
            "operational_state": e.operational_state,
            "category": ref(e.equipment_model.category, "code", "name"),
            "current_location": ref(e.current_location, "code", "name") if e.current_location_id else None,
            "calibration_status": cal["status"], "next_calibration_due": cal["next_due_date"],
            "has_unresolved_failure": cal["has_unresolved_failure"]}


class EquipmentAllocationActions:
    @action(detail=True, methods=["get"])
    def availability(self, request, public_id=None):
        start, end = _window(request)
        return Response(services.availability(self.get_object(), start, end))

    @action(detail=False, methods=["get"])
    def available(self, request):
        start, end = _window(request)
        rows = services.available_equipment(
            self.ctx.facility, category=_scoped(EquipmentCategory, request, "category"),
            location=_scoped(Location, request, "location"), department=_scoped(Department, request, "department"),
            start=start, end=end)
        page = self.paginate_queryset(rows)
        return self.get_paginated_response(
            [{**_row(r["equipment"], r["calibration"]), "warnings": r["warnings"]} for r in page])

    @action(detail=False, methods=["get"])
    def bedside(self, request):
        loc = _scoped(Location, request, "location", required=True)
        rows = services.bedside_equipment(self.ctx.facility, loc, _scoped(EquipmentCategory, request, "category"))
        page = self.paginate_queryset(rows)
        out = []
        for r in page:
            a = r["allocation"]
            out.append({**_row(r["equipment"], r["calibration"]),
                        "allocation": None if a is None else {
                            "public_id": str(a.public_id),
                            "department": ref(a.department, "code", "name") if a.department_id else None,
                            "patient_reference": a.patient_reference, "since": a.assigned_at}})
        return self.get_paginated_response(out)

    @action(detail=True, methods=["get"], url_path="usage-summary")
    def usage_summary(self, request, public_id=None):
        eq = self.get_object()
        logs = EquipmentUsageLog.objects.filter(facility_id=eq.facility_id, equipment_id=eq.pk, is_active=True)
        mins30 = logs.filter(ended_at__gte=timezone.now() - timedelta(days=30)).aggregate(
            s=Sum("duration_minutes"))["s"] or 0
        last = logs.order_by("-started_at", "-id").first()
        return Response({
            "total_hours": services.usage_hours_total(eq),
            "hours_last_30_days": round(float(mins30) / 60, 2),
            "session_count": logs.count(),
            "last_session": None if last is None else {
                "public_id": str(last.public_id), "started_at": last.started_at, "ended_at": last.ended_at,
                "operator_name": last.operator_name, "procedure_text": last.procedure_text},
        })