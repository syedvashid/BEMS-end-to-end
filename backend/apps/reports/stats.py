"""Daily statistics rebuild (B2). Idempotent: delete-and-insert per batch inside one transaction."""
import logging
import time
from decimal import Decimal
from django.db import connection, transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core import audit
from apps.core.errors import Conflict
from apps.equipment.models import EquipmentCommissioning

from .downtime import compute_rows
from .models import EquipmentDailyStat
from django.db.models import Max, Sum



log = logging.getLogger(__name__)
LOCK_NS = 7101
MAX_DAYS = 366


def latest_stat_date(facility):
    return EquipmentDailyStat.objects.filter(facility_id=facility.id).aggregate(m=Max("stat_date"))["m"]


def stats_status(facility):
    agg = EquipmentDailyStat.objects.filter(facility_id=facility.id).aggregate(d=Max("stat_date"), c=Max("computed_at"))
    return {"latest_date": agg["d"], "computed_at": agg["c"]}


def _candidate_ids(facility, date_to, equipment):
    q = EquipmentCommissioning.objects.filter(
        facility_id=facility.id, is_active=True, commissioning_date__isnull=False,
        commissioning_date__lte=date_to, equipment__is_active=True)
    if equipment is not None:
        q = q.filter(equipment_id=equipment.pk)
    return sorted(set(q.values_list("equipment_id", flat=True)))



def _billed_by_day(facility, equipment_ids, date_from, date_to):
    """Net billed amount per (equipment, charge date) from APPROVED and REVERSED records. A reversal record is
    APPROVED with a negative amount, so a reversed charge nets to zero. Pending and cancelled are excluded."""
    from apps.billing.models import ChargeRecord   # Phase 11 (lazy)
    rows = (ChargeRecord.objects.filter(
        facility_id=facility.id, equipment_id__in=equipment_ids, charge_date__gte=date_from,
        charge_date__lte=date_to, status__in=("APPROVED", "REVERSED"))
        .values_list("equipment_id", "charge_date").annotate(s=Sum("amount")).order_by())
    return {(e, d): s for e, d, s in rows}


def rebuild_daily_stats(facility, date_from, date_to, equipment=None, request=None, batch_size=500):
    if date_to < date_from:
        raise ValidationError({"to": ["Must not be before the start date."]})
    if (date_to - date_from).days + 1 > MAX_DAYS:
        raise ValidationError({"to": [f"At most {MAX_DAYS} days per rebuild."]})
    key = (LOCK_NS << 32) | int(facility.id)
    with connection.cursor() as cur:
        cur.execute("select pg_try_advisory_lock(%s)", [key])
        got = cur.fetchone()[0]
    if not got:
        raise Conflict("A statistics rebuild is already running for this facility.")
    started = time.monotonic()
    try:
        ids = _candidate_ids(facility, date_to, equipment)
        processed = written = 0
        for i in range(0, len(ids), batch_size):
            batch = ids[i:i + batch_size]
            rows = compute_rows(facility, batch, date_from, date_to)
            billed = _billed_by_day(facility, batch, date_from, date_to)
            for r in rows:
                r["billed_amount"] = billed.get((r["equipment_id"], r["stat_date"]), Decimal("0"))
            now = timezone.now()
            with transaction.atomic():
                EquipmentDailyStat.objects.filter(
                    facility_id=facility.id, equipment_id__in=batch,
                    stat_date__gte=date_from, stat_date__lte=date_to).delete()
                EquipmentDailyStat.objects.bulk_create(
                    [EquipmentDailyStat(facility_id=facility.id, computed_at=now, **r) for r in rows], batch_size=2000)
            processed += len(batch)
            written += len(rows)
        result = {"from": date_from, "to": date_to, "equipment_processed": processed, "rows_written": written,
                  "seconds": round(time.monotonic() - started, 2)}
        with transaction.atomic():
            audit.record(request=request, action="STATS_REBUILT", facility_id=facility.id,
                         entity_type="EquipmentDailyStat",
                         new={**result, "scope": equipment.asset_tag if equipment is not None else "ALL"})
        return result
    finally:
        with connection.cursor() as cur:
            cur.execute("select pg_advisory_unlock(%s)", [key])
