"""Equipment holds and the DERIVED operational state.

State of a COMMISSIONED equipment = UNDER_MAINTENANCE if any open MAINTENANCE hold, else OUT_OF_SERVICE if any
open OUT_OF_SERVICE hold, else IN_SERVICE. recompute_operational_state is the only caller of the private writer
apps.equipment.services._write_operational_state.
"""
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core import audit
from apps.core.errors import Conflict
from apps.equipment import services as eq_services
from apps.equipment.models import Equipment

from .models import EquipmentHold

ENTITY = "EquipmentHold"


def open_holds(facility_id, equipment_pk):
    return EquipmentHold.objects.filter(
        facility_id=facility_id, equipment_id=equipment_pk, is_active=True, released_at__isnull=True)


def derive_state(facility_id, equipment_pk):
    types = set(open_holds(facility_id, equipment_pk).values_list("hold_type", flat=True))
    if "MAINTENANCE" in types:
        return "UNDER_MAINTENANCE"
    if "OUT_OF_SERVICE" in types:
        return "OUT_OF_SERVICE"
    return "IN_SERVICE"


def recompute_operational_state(*, request, equipment, reason):
    """Lock the equipment row, derive the state, write it only when it changed."""
    with transaction.atomic():
        eq = eq_services._lock(equipment)
        if eq.lifecycle_stage != "COMMISSIONED":
            return eq
        new = derive_state(eq.facility_id, eq.pk)
        if new != eq.operational_state:
            eq_services._write_operational_state(request=request, eq=eq, new_state=new, reason=reason[:1000])
        return eq


def _hold_audit(request, action, hold, eq, extra=None):
    new = {"equipment": str(eq.public_id), "asset_tag": eq.asset_tag, "hold_type": hold.hold_type,
           "source_type": hold.source_type, "reason": hold.reason,
           "work_order": str(hold.work_order.public_id) if hold.work_order_id else None}
    new.update(extra or {})
    audit.record(request=request, action=action, facility_id=eq.facility_id, entity_type=ENTITY,
                 entity_public_id=hold.public_id, new=new)


def place_hold(*, request, equipment, hold_type, source_type, work_order=None, reason):
    uid = request.user.id
    with transaction.atomic():
        eq = eq_services._lock(equipment)
        if eq.lifecycle_stage != "COMMISSIONED":
            raise Conflict("Holds can only be placed on commissioned equipment.")
        if work_order is not None:
            existing = open_holds(eq.facility_id, eq.pk).filter(work_order_id=work_order.pk, hold_type=hold_type).first()
            if existing is not None:
                return existing
        hold = EquipmentHold.objects.create(
            facility_id=eq.facility_id, equipment=eq, hold_type=hold_type, source_type=source_type,
            work_order=work_order, reason=reason, created_by=uid, updated_by=uid)
        _hold_audit(request, "HOLD_PLACED", hold, eq)
        label = "Maintenance" if hold_type == "MAINTENANCE" else "Out-of-service"
        recompute_operational_state(request=request, equipment=eq, reason=f"{label} hold placed: {reason}")
    return hold


def _release(request, hold, eq, reason):
    hold.released_at = timezone.now()
    hold.released_by = request.user.id
    hold.release_reason = reason
    hold.updated_by = request.user.id
    hold.save(update_fields=["released_at", "released_by", "release_reason", "updated_by"])
    _hold_audit(request, "HOLD_RELEASED", hold, eq, {"release_reason": reason})


def release_hold(*, request, hold, reason):
    with transaction.atomic():
        row = EquipmentHold.objects.select_for_update().filter(pk=hold.pk, facility_id=hold.facility_id).first()
        if row is None or row.released_at is not None:
            return row
        eq = Equipment.objects.select_for_update().get(pk=row.equipment_id)
        _release(request, row, eq, reason)
        recompute_operational_state(request=request, equipment=eq, reason=f"Hold released: {reason}")
    return row


def release_work_order_holds(*, request, wo, reason):
    """Release ALL open holds of a work order (complete / cancel), then recompute once."""
    with transaction.atomic():
        eq = Equipment.objects.select_for_update().filter(pk=wo.equipment_id, facility_id=wo.facility_id).first()
        if eq is None:
            return
        rows = list(open_holds(eq.facility_id, eq.pk).select_for_update().filter(work_order_id=wo.pk))
        for h in rows:
            _release(request, h, eq, reason)
        if rows:
            recompute_operational_state(request=request, equipment=eq, reason=reason)


def release_manual_holds(*, request, equipment, reason):
    """Manual In service: releases MANUAL holds only; any other open hold blocks it (409 with the list)."""
    with transaction.atomic():
        eq = eq_services._lock(equipment)
        rows = list(open_holds(eq.facility_id, eq.pk).select_for_update().select_related("work_order"))
        blocking = [h for h in rows if h.source_type != "MANUAL"]
        if blocking:
            exc = Conflict("Equipment cannot be set to In service while other holds are open. "
                           "They are released automatically when their work orders are completed or cancelled.")
            exc.extra = {"blocking_holds": [{
                "public_id": str(h.public_id), "hold_type": h.hold_type, "source_type": h.source_type,
                "reason": h.reason, "started_at": h.started_at.isoformat(),
                "work_order": h.work_order.wo_number if h.work_order_id else None} for h in blocking]}
            raise exc
        if not rows:
            raise ValidationError({"operational_state": ["Equipment is already in this state."]})
        for h in rows:
            _release(request, h, eq, reason)
        recompute_operational_state(request=request, equipment=eq, reason=reason)
    return eq
