from decimal import Decimal

from django.db.models import Sum

from apps.core.errors import Conflict

from .models import (
    EquipmentAllocation, EquipmentReservation, EquipmentTransferRequest, EquipmentUsageLog, UserDepartment,
)


def ensure_not_allocated(equipment):
    if EquipmentAllocation.objects.filter(
            facility_id=equipment.facility_id, equipment_id=equipment.pk,
            released_at__isnull=True, is_active=True).exists():
        raise Conflict("Equipment is allocated. Release it first.")


def usage_hours_totals(facility_id, equipment_ids):
    """{equipment_id: hours} in one query; equipment without logs is simply absent (treat as 0)."""
    ids = list(dict.fromkeys(equipment_ids))
    if not ids:
        return {}
    rows = EquipmentUsageLog.objects.filter(
        facility_id=facility_id, equipment_id__in=ids, is_active=True
    ).values("equipment_id").annotate(s=Sum("duration_minutes"))
    return {r["equipment_id"]: (Decimal(r["s"] or 0) / Decimal(60)).quantize(Decimal("0.01")) for r in rows}


def department_blockers(instance):
    f = instance.facility_id
    return [
        (EquipmentAllocation.objects.filter(facility_id=f, department_id=instance.pk, released_at__isnull=True,
                                            is_active=True).count(), "allocations"),
        (EquipmentReservation.objects.filter(facility_id=f, department_id=instance.pk, status="CONFIRMED",
                                             is_active=True).count(), "reservations"),
        (EquipmentTransferRequest.objects.filter(
            facility_id=f, status="PENDING", is_active=True).filter(
            to_department_id=instance.pk).count()
         + EquipmentTransferRequest.objects.filter(
            facility_id=f, status="PENDING", is_active=True, to_department_id__isnull=True,
            from_department_id=instance.pk).count(), "pending transfer requests"),
        (UserDepartment.objects.filter(facility_id=f, department_id=instance.pk).count(), "user-department mappings"),
    ]


def location_blockers(instance):
    f = instance.facility_id
    return [
        (EquipmentAllocation.objects.filter(facility_id=f, location_id=instance.pk, released_at__isnull=True,
                                            is_active=True).count(), "allocations"),
        (EquipmentTransferRequest.objects.filter(facility_id=f, status="PENDING", is_active=True).filter(
            to_location_id=instance.pk).count()
         + EquipmentTransferRequest.objects.filter(facility_id=f, status="PENDING", is_active=True).filter(
            from_location_id=instance.pk).exclude(to_location_id=instance.pk).count(), "pending transfer requests"),
    ]