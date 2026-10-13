"""Total cost of ownership: one set-based computation used by the live endpoint, the snapshot job and candidates."""
from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Sum
from rest_framework.exceptions import ValidationError

from apps.core import audit
from apps.equipment.models import Equipment, EquipmentCommissioning
from apps.maintenance.services import facility_tz, today_for

from . import depreciation as dep
from .models import Disposal, TcoSnapshot
from .services import DEPRECIABLE_STAGES, PolicyResolver, get_settings, uid_of

SNAPSHOT_STAGES = ("COMMISSIONED", "CONDEMNED", "DISPOSED")
BATCH = 500
ZERO = Decimal("0.00")


def compute_tco(facility, equipment_ids, as_of_date):
    """{equipment_pk: dict of snapshot columns + reasons}. A fixed number of queries for any number of equipment."""
    from apps.allocation.models import EquipmentUsageLog
    from apps.compliance.models import AmcCoverage
    from apps.maintenance.models import SparePartStockEntry, WorkOrder

    ids = list(equipment_ids)
    if not ids:
        return {}
    fid = facility.id
    threshold = get_settings(facility).maintenance_cost_threshold_percent
    resolver = PolicyResolver(fid)
    eqs = {e.pk: e for e in Equipment.objects.filter(facility_id=fid, pk__in=ids).select_related("equipment_model")}
    comm = dict(EquipmentCommissioning.objects.filter(
        equipment_id__in=ids, is_active=True, commissioning_date__isnull=False,
    ).values_list("equipment_id", "commissioning_date"))

    labour, vendor = defaultdict(lambda: ZERO), defaultdict(lambda: ZERO)
    for r in WorkOrder.objects.filter(facility_id=fid, equipment_id__in=ids, is_active=True,
                                      status__in=("COMPLETED", "CLOSED")).values("equipment_id").annotate(
            l=Sum("labour_cost"), v=Sum("vendor_cost")):
        labour[r["equipment_id"]] = dep.D(r["l"])
        vendor[r["equipment_id"]] = dep.D(r["v"])

    # Parts: CONSUMPTION adds, RETURN subtracts; the sign convention of the stored quantity does not matter (abs).
    parts = defaultdict(lambda: Decimal(0))
    for eq_id, etype, qty, unit_cost in SparePartStockEntry.objects.filter(
            facility_id=fid, work_order__equipment_id__in=ids, entry_type__in=("CONSUMPTION", "RETURN"),
    ).values_list("work_order__equipment_id", "entry_type", "quantity", "unit_cost"):
        value = abs(dep.D(qty)) * dep.D(unit_cost)
        parts[eq_id] += value if etype == "CONSUMPTION" else -value

    amc = defaultdict(lambda: Decimal(0))
    for cov in AmcCoverage.objects.filter(facility_id=fid, equipment_id__in=ids, amc_contract__is_active=True) \
            .select_related("amc_contract"):
        c = cov.amc_contract
        amc[cov.equipment_id] += dep.D(cov.allocated_cost) * dep.amc_fraction(c.start_date, c.end_date, as_of_date)

    cutoff = datetime.combine(as_of_date + timedelta(days=1), time.min, tzinfo=facility_tz(facility))
    usage = {r["equipment_id"]: r for r in EquipmentUsageLog.objects.filter(
        facility_id=fid, equipment_id__in=ids, is_active=True, started_at__lt=cutoff,
    ).values("equipment_id").annotate(minutes=Sum("duration_minutes"), n=Count("id"))}

    proceeds = dict(Disposal.objects.filter(facility_id=fid, equipment_id__in=ids, status="COMPLETED", is_active=True)
                    .values_list("equipment_id", "proceeds_amount"))

    out = {}
    for pk in ids:
        eq = eqs.get(pk)
        if eq is None:
            continue
        acquisition, install = dep.q2(dep.D(eq.purchase_cost)), dep.q2(dep.D(eq.installation_cost))
        lab, ven, prt, amc_c = dep.q2(labour[pk]), dep.q2(vendor[pk]), dep.q2(parts[pk]), dep.q2(amc[pk])
        if eq.lifecycle_stage == "DISPOSED" and pk in proceeds:
            salvage = dep.q2(dep.D(proceeds[pk]))
        else:
            policy = resolver.resolve(pk, eq.equipment_model.category_id)
            salvage = dep.salvage_amount(dep.D(eq.purchase_cost), policy.salvage_percent) if policy else ZERO
        maintenance = lab + ven + prt + amc_c
        total = acquisition + install + maintenance - salvage
        ratio = None
        if eq.purchase_cost is not None and eq.purchase_cost > 0:
            ratio = dep.q2(maintenance / eq.purchase_cost * 100)
        age = dep.age_years(comm.get(pk), as_of_date)
        life = eq.expected_life_years if eq.expected_life_years is not None else eq.equipment_model.expected_life_years
        life = dep.D(life) if life is not None else None
        u = usage.get(pk)
        hours = dep.q2(dep.D(u["minutes"]) / 60) if u else ZERO
        sessions = u["n"] if u else 0
        indicator, reasons = dep.replacement_indicator(ratio, age, life, threshold)
        out[pk] = {
            "as_of_date": as_of_date, "acquisition_cost": acquisition, "installation_cost": install,
            "labour_cost": lab, "vendor_cost": ven, "parts_cost": prt, "amc_cost": amc_c, "salvage_value": salvage,
            "total_cost_of_ownership": dep.q2(total), "maintenance_cost": dep.q2(maintenance),
            "maintenance_cost_ratio_percent": ratio, "age_years": age, "expected_life_years": life,
            "usage_hours": hours, "session_count": sessions,
            "cost_per_hour": dep.q2(total / hours) if hours > 0 else None,
            "cost_per_use": dep.q2(total / sessions) if sessions > 0 else None,
            "threshold_percent": dep.q2(dep.D(threshold)), "replacement_indicator": indicator,
            "reasons": reasons,
        }
    return out


_SNAPSHOT_FIELDS = (
    "acquisition_cost", "installation_cost", "labour_cost", "vendor_cost", "parts_cost", "amc_cost", "salvage_value",
    "total_cost_of_ownership", "maintenance_cost", "maintenance_cost_ratio_percent", "age_years",
    "expected_life_years", "usage_hours", "session_count", "cost_per_hour", "cost_per_use", "threshold_percent",
    "replacement_indicator")


def generate_tco_snapshots(*, facility, as_of_date=None, request=None):
    """One snapshot per (equipment, as_of_date); equipment that already has one is left untouched (idempotent)."""
    today = today_for(facility)
    as_of = as_of_date or today
    if as_of > today:
        raise ValidationError({"as_of": ["Cannot be in the future."]})
    uid = uid_of(request)
    with transaction.atomic():
        ids = list(Equipment.objects.filter(
            facility_id=facility.id, is_active=True, lifecycle_stage__in=SNAPSHOT_STAGES).order_by("id")
            .values_list("id", flat=True))
        existing = set(TcoSnapshot.objects.filter(facility_id=facility.id, as_of_date=as_of)
                       .values_list("equipment_id", flat=True))
        todo = [i for i in ids if i not in existing]
        created = 0
        for i in range(0, len(todo), BATCH):
            computed = compute_tco(facility, todo[i:i + BATCH], as_of)
            rows = [TcoSnapshot(facility_id=facility.id, equipment_id=pk, as_of_date=as_of, created_by=uid,
                                **{f: v[f] for f in _SNAPSHOT_FIELDS}) for pk, v in computed.items()]
            TcoSnapshot.objects.bulk_create(rows)
            created += len(rows)
        summary = {"as_of_date": as_of.isoformat(), "equipment_considered": len(ids), "created": created,
                   "skipped_existing": len(ids) - len(todo)}
        audit.record(request=request, action="TCO_SNAPSHOTS_GENERATED", facility_id=facility.id,
                     entity_type="TcoSnapshot", new=summary)
    return summary
