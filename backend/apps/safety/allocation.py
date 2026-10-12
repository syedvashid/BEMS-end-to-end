"""The ONLY place where apps.safety touches Phase 7 (apps/allocation).

If your allocation model or its "active" condition is named differently, change this file and nothing else.
"""
import logging

from django.core.exceptions import FieldError

log = logging.getLogger("bems.safety")

# ADJUST if needed: the filter that means "this allocation is currently active".
ACTIVE_FILTER = {"released_at__isnull": True}


def allocated_equipment_ids(facility_id, equipment_ids):
    """Set of equipment ids (from equipment_ids) that currently have an active allocation."""
    ids = list(equipment_ids)
    if not ids:
        return set()
    try:
        from apps.allocation.models import EquipmentAllocation
        qs = EquipmentAllocation.objects.filter(facility_id=facility_id, equipment_id__in=ids, **ACTIVE_FILTER)
        return set(qs.values_list("equipment_id", flat=True))
    except (ImportError, FieldError) as exc:
        log.error("safety.allocation: lookup failed (%s). Adjust apps/safety/allocation.py", exc)
        raise RuntimeError("apps/safety/allocation.py does not match the Phase 7 allocation model.") from exc
