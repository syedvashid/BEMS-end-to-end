"""Finance services: settings, policy resolution, depreciation run, opening balances, book values, summary.

Money is Decimal everywhere. Every data-changing service runs in transaction.atomic(), locks its main row,
validates, and writes the audit event. System jobs pass request=None (audit actor "system").
"""
import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from django.db import connection, transaction
from rest_framework.exceptions import NotFound, ValidationError

from apps.core import audit
from apps.core.errors import Conflict, StaleVersion
from apps.equipment import services as eq_services
from apps.equipment.models import Equipment, EquipmentCommissioning
from apps.foundation.models import Facility, User
from apps.maintenance.services import today_for
from apps.masters.models import EquipmentCategory

from . import depreciation as dep
from .models import DepreciationEntry, DepreciationPolicy, DepreciationRun, FinanceSettings

log = logging.getLogger("bems.finance")

DEPRECIABLE_STAGES = ("COMMISSIONED", "CONDEMNED")
DEFAULT_THRESHOLD = Decimal("60.00")
_LOCK_NS = 9001 << 40
BATCH = 200


def uid_of(request):
    return getattr(getattr(request, "user", None), "id", None) if request is not None else None


def usernames(ids):
    ids = {i for i in ids if i}
    return dict(User.objects.filter(id__in=ids).values_list("id", "username")) if ids else {}


def audit_refused(request, action, entity_type, obj, exc):
    """A request refused by a business gate: written in autocommit, outside the failed atomic block."""
    extra = getattr(exc, "extra", None) or {}
    audit.record(request=request, action=action, facility_id=obj.facility_id, entity_type=entity_type,
                 entity_public_id=obj.public_id,
                 new={"refused": str(getattr(exc, "detail", exc))[:300], **extra})


# ------------------------------------------------------------------ settings and policy resolution
def get_settings(facility):
    row = FinanceSettings.objects.filter(facility_id=facility.id, is_active=True).first()
    if row is not None:
        return row
    return SimpleNamespace(public_id=None, row_version=None, maintenance_cost_threshold_percent=DEFAULT_THRESHOLD,
                           committee_required_above_book_value=None)


def upsert_settings(*, request, facility, data, expected_version):
    uid = uid_of(request)
    with transaction.atomic():
        row = FinanceSettings.objects.select_for_update().filter(facility_id=facility.id, is_active=True).first()
        if row is None:
            row = FinanceSettings.objects.create(
                facility_id=facility.id, created_by=uid, updated_by=uid,
                maintenance_cost_threshold_percent=data.get("maintenance_cost_threshold_percent", DEFAULT_THRESHOLD),
                committee_required_above_book_value=data.get("committee_required_above_book_value"))
            snap = audit.snapshot(row)
            audit.record(request=request, action="CREATE", facility_id=facility.id, entity_type="FinanceSettings",
                         entity_public_id=row.public_id, new=snap, changed_fields=audit.diff(None, snap))
        else:
            if expected_version is None:
                raise ValidationError({"row_version": ["This field is required."]})
            if row.row_version != expected_version:
                raise StaleVersion(current_row_version=row.row_version)
            before = audit.snapshot(row)
            if "maintenance_cost_threshold_percent" in data:
                row.maintenance_cost_threshold_percent = data["maintenance_cost_threshold_percent"]
            row.committee_required_above_book_value = data.get("committee_required_above_book_value")
            row.updated_by = uid
            row.save()
            row.refresh_from_db(fields=["updated_at", "row_version"])
            after = audit.snapshot(row)
            audit.record(request=request, action="UPDATE", facility_id=facility.id, entity_type="FinanceSettings",
                         entity_public_id=row.public_id, previous=before, new=after,
                         changed_fields=audit.diff(before, after))
    return row


class PolicyResolver:
    """Equipment override, then the equipment's category (through its model), then the category's parent group."""

    def __init__(self, facility_id):
        pols = list(DepreciationPolicy.objects.filter(facility_id=facility_id, is_active=True))
        self.by_equipment = {p.equipment_id: p for p in pols if p.equipment_id}
        self.by_category = {p.category_id: p for p in pols if p.category_id}
        self.parent = dict(EquipmentCategory.objects.filter(facility_id=facility_id)
                           .values_list("id", "parent_category_id"))

    def resolve(self, equipment_pk, category_id):
        p = self.by_equipment.get(equipment_pk)
        if p is not None:
            return p
        p = self.by_category.get(category_id)
        if p is not None:
            return p
        parent = self.parent.get(category_id)
        return self.by_category.get(parent) if parent else None

    def source(self, policy, category_id):
        if policy is None:
            return None
        if policy.equipment_id:
            return "EQUIPMENT"
        return "CATEGORY" if policy.category_id == category_id else "PARENT_CATEGORY"


def resolve_policy(equipment):
    return PolicyResolver(equipment.facility_id).resolve(equipment.pk, equipment.equipment_model.category_id)


# ------------------------------------------------------------------ depreciation basis and book values
@dataclass(frozen=True)
class Basis:
    cost: Decimal
    salvage: Decimal
    start: date
    method: str
    life: Decimal | None
    rate: Decimal | None


def commissioning_dates(equipment_ids):
    return dict(EquipmentCommissioning.objects.filter(
        equipment_id__in=list(equipment_ids), is_active=True, commissioning_date__isnull=False,
    ).values_list("equipment_id", "commissioning_date"))


def depreciation_basis(*, ownership_type, lifecycle_stage, purchase_cost, installation_cost, invoice_date, policy,
                       commissioning_date):
    """(reason, Basis|None). reason is OK or NOT_OWNED, NOT_ELIGIBLE_STAGE, NO_COST, NO_POLICY, NO_START_DATE."""
    if ownership_type != "OWNED":
        return "NOT_OWNED", None
    if lifecycle_stage not in DEPRECIABLE_STAGES:
        return "NOT_ELIGIBLE_STAGE", None
    if purchase_cost is None or purchase_cost <= 0:
        return "NO_COST", None
    if policy is None:
        return "NO_POLICY", None
    start = dep.start_date_for(policy.start_rule, commissioning_date, invoice_date)
    if start is None:
        return "NO_START_DATE", None
    cost = dep.capitalised_cost(purchase_cost, installation_cost)
    return "OK", Basis(cost=cost, salvage=dep.salvage_amount(cost, policy.salvage_percent), start=start,
                       method=policy.method, life=policy.useful_life_years, rate=policy.rate_percent)


def basis_for_equipment(eq, policy, commissioning_date):
    return depreciation_basis(
        ownership_type=eq.ownership_type, lifecycle_stage=eq.lifecycle_stage, purchase_cost=eq.purchase_cost,
        installation_cost=eq.installation_cost, invoice_date=eq.invoice_date, policy=policy,
        commissioning_date=commissioning_date)


def latest_entries(equipment_ids):
    """{equipment_id: latest DepreciationEntry}: one query for any number of equipment."""
    ids = list(equipment_ids)
    if not ids:
        return {}
    rows = DepreciationEntry.objects.filter(equipment_id__in=ids).order_by("equipment_id", "-period_month") \
        .distinct("equipment_id")
    return {e.equipment_id: e for e in rows}


def current_book_value(eq):
    """Latest book value of an owned equipment, else None."""
    if eq.ownership_type != "OWNED":
        return None
    e = latest_entries([eq.pk]).get(eq.pk)
    return e.closing_value if e is not None else None


def _calc_dict(c):
    return {"period_month": c.period_month, "opening_value": c.opening_value, "charge": c.charge,
            "closing_value": c.closing_value, "days_charged": c.days_charged}


def equipment_finance_brief(eq):
    """Small block for the equipment detail: book value, accumulated depreciation, last depreciation month."""
    out = {"book_value": None, "accumulated_depreciation": None, "last_depreciation_month": None}
    if eq.ownership_type != "OWNED":
        return out
    e = latest_entries([eq.pk]).get(eq.pk)
    if e is None:
        return out
    cost = dep.capitalised_cost(eq.purchase_cost, eq.installation_cost)
    out.update(book_value=e.closing_value, accumulated_depreciation=dep.q2(cost - e.closing_value),
               last_depreciation_month=e.period_month)
    return out


def equipment_finance_info(eq):
    resolver = PolicyResolver(eq.facility_id)
    category_id = eq.equipment_model.category_id
    policy = resolver.resolve(eq.pk, category_id)
    comm = commissioning_dates([eq.pk]).get(eq.pk)
    reason, basis = basis_for_equipment(eq, policy, comm)
    entry = latest_entries([eq.pk]).get(eq.pk)
    cost = dep.capitalised_cost(eq.purchase_cost, eq.installation_cost) if eq.ownership_type == "OWNED" else None
    info = {
        "ownership_type": eq.ownership_type, "depreciable": reason == "OK", "reason": reason,
        "capitalised_cost": cost, "book_value": None, "accumulated_depreciation": None,
        "last_depreciation_month": None, "last_entry_type": None, "effective_start_date": None,
        "salvage_value": basis.salvage if basis else None, "policy": None,
    }
    if basis is not None:
        info["effective_start_date"] = basis.start
    if entry is not None and cost is not None:
        info.update(book_value=entry.closing_value, accumulated_depreciation=dep.q2(cost - entry.closing_value),
                    last_depreciation_month=entry.period_month, last_entry_type=entry.entry_type)
    if policy is not None:
        info["policy"] = {
            "public_id": str(policy.public_id), "source": resolver.source(policy, category_id),
            "method": policy.method, "useful_life_years": policy.useful_life_years,
            "rate_percent": policy.rate_percent, "salvage_percent": policy.salvage_percent,
            "start_rule": policy.start_rule}
    return info


def equipment_projection(eq):
    """Future monthly schedule from the last entry to salvage (cap 600 months)."""
    policy = resolve_policy(eq)
    comm = commissioning_dates([eq.pk]).get(eq.pk)
    reason, basis = basis_for_equipment(eq, policy, comm)
    if basis is None:
        return []
    entry = latest_entries([eq.pk]).get(eq.pk)
    calcs = dep.projection(
        method=basis.method, cost=basis.cost, salvage=basis.salvage, start_date=basis.start,
        last_closing=entry.closing_value if entry else None, last_month=entry.period_month if entry else None,
        useful_life_years=basis.life, rate_percent=basis.rate)
    return [_calc_dict(c) for c in calcs]


# ------------------------------------------------------------------ monthly run
def last_completed_month(facility):
    return dep.add_months(dep.month_start(today_for(facility)), -1)


def _entry_row(eq, c, entry_type, basis, policy, run, uid):
    return DepreciationEntry(
        facility_id=eq.facility_id, equipment_id=eq.pk, period_month=c.period_month, entry_type=entry_type,
        opening_value=c.opening_value, charge=c.charge, closing_value=c.closing_value, method=basis.method,
        policy_id=policy.pk if policy is not None else None, run_id=run.pk if run is not None else None,
        days_charged=c.days_charged, created_by=uid)


def _catch_up(eq, basis, policy, last, target, run, uid):
    if last is None:
        opening, from_month = basis.cost, dep.month_start(basis.start)
    else:
        opening, from_month = last.closing_value, dep.add_months(last.period_month, 1)
    if from_month > target:
        return []
    calcs = dep.generate_entries(
        method=basis.method, cost=basis.cost, salvage=basis.salvage, start_date=basis.start, opening_value=opening,
        from_month=from_month, to_month=target, useful_life_years=basis.life, rate_percent=basis.rate)
    if calcs:
        DepreciationEntry.objects.bulk_create([_entry_row(eq, c, "REGULAR", basis, policy, run, uid) for c in calcs])
    return calcs


def _process_facility(facility, target, run, uid):
    resolver = PolicyResolver(facility.id)
    ids = list(Equipment.objects.filter(
        facility_id=facility.id, is_active=True, ownership_type="OWNED", lifecycle_stage__in=DEPRECIABLE_STAGES,
    ).order_by("id").values_list("id", flat=True))
    counters = {"NO_POLICY": 0, "NO_COST": 0, "NO_START_DATE": 0}
    processed = created = 0
    total = Decimal("0.00")
    failures = []
    for i in range(0, len(ids), BATCH):
        chunk = ids[i:i + BATCH]
        eqs = list(Equipment.objects.filter(pk__in=chunk).select_related("equipment_model").order_by("id"))
        comm = commissioning_dates(chunk)
        last = latest_entries(chunk)
        for eq in eqs:
            policy = resolver.resolve(eq.pk, eq.equipment_model.category_id)
            reason, basis = basis_for_equipment(eq, policy, comm.get(eq.pk))
            if reason in counters:
                counters[reason] += 1
                continue
            if reason != "OK":
                continue
            try:
                with transaction.atomic():   # savepoint per equipment: one failure does not stop the run
                    locked = Equipment.objects.select_for_update().filter(
                        pk=eq.pk, is_active=True, lifecycle_stage__in=DEPRECIABLE_STAGES).first()
                    if locked is None:
                        continue
                    calcs = _catch_up(eq, basis, policy, last.get(eq.pk), target, run, uid)
                processed += 1
                created += len(calcs)
                total += sum((c.charge for c in calcs), Decimal("0.00"))
            except Exception as exc:   # noqa: BLE001 - counted and listed, never leaked to the client
                log.exception("Depreciation failed for equipment %s", eq.pk)
                failures.append({"asset_tag": eq.asset_tag, "error": type(exc).__name__})
    return {"assets_processed": processed, "entries_created": created, "total_charge": dep.q2(total),
            "skipped_no_policy": counters["NO_POLICY"], "skipped_no_cost": counters["NO_COST"],
            "skipped_no_start_date": counters["NO_START_DATE"], "failed": failures[:50],
            "failed_count": len(failures)}


def run_depreciation(*, facility, target_month=None, request=None):
    """Catch-up depreciation through target_month (default: the last completed month in the facility timezone)."""
    last_done = last_completed_month(facility)
    target = last_done if target_month is None else dep.month_start(target_month)
    if target > last_done:
        raise ValidationError({"month": ["That month has not finished yet."]})
    uid = uid_of(request)
    try:
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("select pg_try_advisory_xact_lock(%s)", [_LOCK_NS + facility.id])
                if not cur.fetchone()[0]:
                    raise Conflict("A depreciation run is already in progress for this facility.")
            run = DepreciationRun.objects.create(
                facility_id=facility.id, run_period=target, status="RUNNING", triggered_by_system=request is None,
                created_by=uid, updated_by=uid)
            result = _process_facility(facility, target, run, uid)
            from django.utils import timezone
            run.status = "COMPLETED"
            run.finished_at = timezone.now()
            run.assets_processed = result["assets_processed"]
            run.entries_created = result["entries_created"]
            run.skipped_no_policy = result["skipped_no_policy"]
            run.skipped_no_cost = result["skipped_no_cost"]
            run.skipped_no_start_date = result["skipped_no_start_date"]
            run.total_charge = result["total_charge"]
            if result["failed_count"]:
                run.error_message = "%d equipment failed: %s" % (
                    result["failed_count"], ", ".join(f["asset_tag"] for f in result["failed"][:20]))[:1000]
            run.updated_by = uid
            run.save()
            summary = {"run": str(run.public_id), "run_period": target.isoformat(), **result,
                       "total_charge": str(result["total_charge"])}
            audit.record(request=request, action="DEPRECIATION_RUN", facility_id=facility.id,
                         entity_type="DepreciationRun", entity_public_id=run.public_id, new=summary)
    except (Conflict, ValidationError):
        raise
    except Exception as exc:
        log.exception("Depreciation run failed")
        DepreciationRun.objects.create(   # autocommit, outside the rolled-back block
            facility_id=facility.id, run_period=target, status="FAILED", triggered_by_system=request is None,
            error_message=type(exc).__name__, created_by=uid, updated_by=uid)
        raise
    return run, summary


# ------------------------------------------------------------------ opening book value
def set_opening_book_value(*, request, equipment, as_of_month, book_value):
    uid = uid_of(request)
    with transaction.atomic():
        eq = eq_services._lock(equipment)
        if eq.ownership_type != "OWNED":
            raise Conflict("Only owned equipment has a book value.")
        if eq.lifecycle_stage not in DEPRECIABLE_STAGES:
            raise Conflict("An opening book value can only be set for commissioned or condemned equipment.")
        facility = Facility.objects.get(pk=eq.facility_id)
        month = dep.month_start(as_of_month)
        if month > last_completed_month(facility):
            raise ValidationError({"as_of_month": ["That month has not finished yet."]})
        if DepreciationEntry.objects.filter(equipment_id=eq.pk, period_month__gte=month).exists():
            raise Conflict("Depreciation entries already exist for this month or later.")
        value = dep.q2(book_value)
        cost = dep.capitalised_cost(eq.purchase_cost, eq.installation_cost)
        if cost > 0 and value > cost:
            raise ValidationError({"book_value": ["Cannot exceed the capitalised cost."]})
        policy = PolicyResolver(eq.facility_id).resolve(eq.pk, eq.equipment_model.category_id)
        entry = DepreciationEntry.objects.create(
            facility_id=eq.facility_id, equipment_id=eq.pk, period_month=month, entry_type="OPENING_BALANCE",
            opening_value=value, charge=Decimal("0.00"), closing_value=value,
            method=policy.method if policy else None, policy_id=policy.pk if policy else None, created_by=uid)
        audit.record(request=request, action="OPENING_BOOK_VALUE_SET", facility_id=eq.facility_id,
                     entity_type="Equipment", entity_public_id=eq.public_id,
                     new={"asset_tag": eq.asset_tag, "as_of_month": month.isoformat(), "book_value": str(value),
                          "entry": str(entry.public_id)})
    return entry


# ------------------------------------------------------------------ finance summary (set-based)
_GROUPS = {
    "category": ("equipment_model__category__public_id", "equipment_model__category__name"),
    "department": ("owning_department__public_id", "owning_department__name"),
    "funding_source": ("funding_source__public_id", "funding_source__name"),
    "ownership_type": ("ownership_type", "ownership_type"),
    "location": ("current_location__public_id", "current_location__name"),
}
GROUP_BY_CHOICES = list(_GROUPS)


def finance_summary(facility, group_by):
    key_f, label_f = _GROUPS[group_by]
    fields = {"id", "ownership_type", "lifecycle_stage", "purchase_cost", "installation_cost", "invoice_date",
              "equipment_model__category_id", key_f, label_f}
    rows = list(Equipment.objects.filter(
        facility_id=facility.id, is_active=True, lifecycle_stage__in=DEPRECIABLE_STAGES).values(*sorted(fields)))
    ids = [r["id"] for r in rows]
    comm, last, resolver = commissioning_dates(ids), latest_entries(ids), PolicyResolver(facility.id)
    zero = Decimal("0.00")
    groups, totals = {}, {"count": 0, "owned_count": 0, "capitalised_cost": zero, "accumulated_depreciation": zero,
                          "book_value": zero, "cannot_depreciate_count": 0}
    for r in rows:
        key = r[key_f]
        g = groups.setdefault(key, {"key": str(key) if key is not None else None, "label": r[label_f] or "Unassigned",
                                    "count": 0, "owned_count": 0, "capitalised_cost": zero,
                                    "accumulated_depreciation": zero, "book_value": zero,
                                    "cannot_depreciate_count": 0})
        g["count"] += 1
        totals["count"] += 1
        if r["ownership_type"] != "OWNED":
            continue
        g["owned_count"] += 1
        totals["owned_count"] += 1
        cost = dep.capitalised_cost(r["purchase_cost"], r["installation_cost"])
        g["capitalised_cost"] += cost
        totals["capitalised_cost"] += cost
        policy = resolver.resolve(r["id"], r["equipment_model__category_id"])
        reason, _ = depreciation_basis(
            ownership_type=r["ownership_type"], lifecycle_stage=r["lifecycle_stage"], purchase_cost=r["purchase_cost"],
            installation_cost=r["installation_cost"], invoice_date=r["invoice_date"], policy=policy,
            commissioning_date=comm.get(r["id"]))
        if reason in ("NO_COST", "NO_POLICY", "NO_START_DATE"):
            g["cannot_depreciate_count"] += 1
            totals["cannot_depreciate_count"] += 1
        e = last.get(r["id"])
        if e is not None:
            g["book_value"] += e.closing_value
            totals["book_value"] += e.closing_value
            g["accumulated_depreciation"] += cost - e.closing_value
            totals["accumulated_depreciation"] += cost - e.closing_value
    return {"group_by": group_by, "totals": totals,
            "groups": sorted(groups.values(), key=lambda g: (g["label"] or "").lower())}
