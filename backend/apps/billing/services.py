"""Charge services (B2-B4). Views stay thin; every writer runs in transaction.atomic(), locks the row it changes,
validates and writes the audit row. Charging never blocks clinical work: the release and usage-log services call
safe_charges_for_allocation / safe_charges_for_usage_log, which never raise."""
import logging
import re
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.allocation.models import EquipmentAllocation, EquipmentUsageLog
from apps.core import audit
from apps.core.errors import Conflict
from apps.maintenance.services import next_number
from apps.reports.common import day_start, facility_tz, local_date

from . import engine
from .models import ChargeMapping, ChargeRecord, ChargeSettings

log = logging.getLogger(__name__)
ENTITY = "ChargeRecord"
LEVELS = ("EQUIPMENT", "CATEGORY", "GROUP")
MAX_BULK = 200
MAX_EXPORT = 5000
MAX_SWEEP_DAYS = 366
GENERIC_WARNING = "Charges could not be calculated. They will be created by the next charge sweep."
REASON_TEXT = {
    "NO_PATIENT_REFERENCE": "No patient reference, nothing will be charged.",
    "NO_MAPPING": "No charge mapping applies to this equipment, nothing will be charged.",
    "BUNDLED": "Covered by package {ref}, no separate charge.",
    "DISABLED": "Billing is disabled for this equipment, nothing will be charged.",
    "NO_ENCOUNTER": "No encounter reference, a per-admission charge cannot be created.",
    "WITHIN_GRACE": "The duration is within the grace period, nothing will be charged.",
    "USAGE_BASIS": "This equipment is charged from its usage logs, not from the allocation.",
    "ALLOCATION_BASIS": "This equipment is charged from its allocation, not from usage logs.",
}


def _reason(code, **kw):
    return {"reason": code, "message": REASON_TEXT[code].format(**kw) if kw else REASON_TEXT[code]}


def _has_ref(v):
    return bool((v or "").strip())


def _constraint(exc):
    return getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None)


# ================================================================== B2 mapping resolution
def resolve_mapping(equipment, on_date):
    """(mapping, level) for the facility date `on_date`: equipment, then its category, then the category's group."""
    from apps.masters.models import EquipmentCategory
    cat_id = equipment.equipment_model.category_id
    parent_id = (EquipmentCategory.objects.filter(pk=cat_id, facility_id=equipment.facility_id)
                 .values_list("parent_category_id", flat=True).first())
    cats = [c for c in (cat_id, parent_id) if c]
    qs = (ChargeMapping.objects.filter(facility_id=equipment.facility_id, is_active=True, effective_from__lte=on_date)
          .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on_date))
          .filter(Q(equipment_id=equipment.pk) | Q(category_id__in=cats)).select_related("charge_item"))
    found = {}
    for m in qs:
        if m.equipment_id is not None:
            found.setdefault("EQUIPMENT", m)
        elif m.category_id == cat_id:
            found.setdefault("CATEGORY", m)
        else:
            found.setdefault("GROUP", m)
    for level in LEVELS:
        if level in found:
            return found[level], level
    return None, None


def config_from_mapping(m):
    """The applied unit rate is the override or the charge item's default rate at calculation time."""
    rate = m.rate_override if m.rate_override is not None else m.charge_item.default_rate
    return engine.RuleConfig(
        billing_rule=m.billing_rule, unit_rate=Decimal(rate), unit_label=m.charge_item.unit_label,
        grace_minutes=m.grace_minutes, minimum_billable_minutes=m.minimum_billable_minutes, rounding=m.rounding,
        daily_cap_amount=Decimal(m.daily_cap_amount) if m.daily_cap_amount is not None else None,
        day_block_mode=m.day_block_mode, bundle_reference=m.bundle_reference)


def mapping_out(m, level=None):
    return {"public_id": str(m.public_id), "charge_item_code": m.charge_item.item_code,
            "charge_item_name": m.charge_item.name, "billing_rule": m.billing_rule, "basis": m.basis,
            "unit_rate": str(config_from_mapping(m).unit_rate), "unit_label": m.charge_item.unit_label,
            "effective_from": m.effective_from.isoformat(),
            "effective_to": m.effective_to.isoformat() if m.effective_to else None,
            "bundle_reference": m.bundle_reference, "level": level}


def auto_approve_enabled(facility):
    row = ChargeSettings.objects.filter(facility_id=facility.id, is_active=True).first()
    return bool(row and row.auto_approve)


# ================================================================== planning (no writes)
def _calc(cfg, mapping, result, start, end, extra=None):
    return {"rule": cfg.billing_rule, "basis": mapping.basis, "mapping": str(mapping.public_id),
            "unit_rate": str(cfg.unit_rate), "grace_minutes": cfg.grace_minutes,
            "minimum_billable_minutes": cfg.minimum_billable_minutes, "rounding": cfg.rounding,
            "daily_cap_amount": str(cfg.daily_cap_amount) if cfg.daily_cap_amount is not None else None,
            "day_block_mode": cfg.day_block_mode,
            "start": start.isoformat() if start else None, "end": end.isoformat() if end else None,
            "steps": result["steps"], **(extra or {})}


def _line(mapping, cfg, result, *, key, period_key, start, end, charge_date):
    return {"mapping": mapping, "rule": cfg.billing_rule, "basis": mapping.basis, "key": key,
            "period_key": period_key, "period_start": start, "period_end": end, "charge_date": charge_date,
            "unit_label": result["unit_label"], "unit_rate": result["unit_rate"], "quantity": result["quantity"],
            "amount": result["amount"], "steps": result["steps"], "calculation": _calc(cfg, mapping, result, start, end)}


def _plan():
    return {"lines": [], "reasons": [], "mapping": None, "level": None}


def plan_for_allocation(allocation, *, end=None, completed_only=False):
    """What an allocation is (or would be) charged. `end` stands in for the release time of an active allocation;
    completed_only keeps only DAILY blocks that are already complete (the nightly accrual)."""
    plan = _plan()
    if not _has_ref(allocation.patient_reference):
        plan["reasons"].append(_reason("NO_PATIENT_REFERENCE"))
        return plan
    tz = facility_tz(allocation.facility)
    start = allocation.assigned_at
    end = allocation.released_at or end or timezone.now()
    end = max(end, start)
    equipment = allocation.equipment
    event_date = local_date(end, tz)
    mapping, level = resolve_mapping(equipment, event_date)
    plan["mapping"], plan["level"] = mapping, level
    if mapping is None:
        if not completed_only:
            plan["reasons"].append(_reason("NO_MAPPING"))
        return plan
    rule = mapping.billing_rule
    if completed_only and rule != "DAILY":
        return plan
    if rule == "BUNDLED":
        plan["reasons"].append(_reason("BUNDLED", ref=mapping.bundle_reference))
        return plan
    if rule == "DISABLED":
        plan["reasons"].append(_reason("DISABLED"))
        return plan
    if mapping.basis != "ALLOCATION":
        plan["reasons"].append(_reason("USAGE_BASIS"))
        return plan
    cfg = config_from_mapping(mapping)
    apid = allocation.public_id
    if rule == "DAILY":
        _plan_daily(plan, allocation, mapping, cfg, start, end, tz, event_date, completed_only)
        return plan
    if rule == "PER_ADMISSION":
        if not _has_ref(allocation.encounter_reference):
            plan["reasons"].append(_reason("NO_ENCOUNTER"))
            return plan
        res = engine.evaluate(cfg, start, end, tz)
        plan["lines"].append(_line(mapping, cfg, res, key=f"ENC:{allocation.encounter_reference}:{mapping.public_id}",
                                   period_key="ENCOUNTER", start=start, end=end, charge_date=event_date))
        return plan
    res = engine.evaluate(cfg, start, end, tz)
    if res["reason"]:
        plan["reasons"].append(_reason(res["reason"]))
        return plan
    suffix, period = ("FINAL", "FINAL") if rule == "HOURLY" else ("USE", "USE")
    plan["lines"].append(_line(mapping, cfg, res, key=f"ALLOC:{apid}:{mapping.public_id}:{suffix}",
                               period_key=period, start=start, end=end, charge_date=event_date))
    return plan


def _plan_daily(plan, allocation, mapping, cfg, start, end, tz, event_date, completed_only):
    blocks = engine.daily_blocks(cfg, start, end, tz)
    if not blocks:
        if not completed_only:
            plan["reasons"].append(_reason("WITHIN_GRACE"))
        return
    cache = {event_date: mapping}
    noted = False
    for b in blocks:
        if completed_only and b.full_end > end:
            continue
        if b.charge_date not in cache:
            cache[b.charge_date] = resolve_mapping(allocation.equipment, b.charge_date)[0]
        m = cache[b.charge_date]
        if m is None or m.billing_rule != "DAILY" or m.basis != "ALLOCATION":
            if not noted and not completed_only:
                plan["reasons"].append(_reason("NO_MAPPING"))
                noted = True
            continue
        bcfg = config_from_mapping(m)
        res = engine.block_result(bcfg, b)
        plan["lines"].append(_line(m, bcfg, res, key=f"ALLOC:{allocation.public_id}:{m.public_id}:DAY:{b.index}",
                                   period_key=f"DAY:{b.index}", start=b.start, end=b.end, charge_date=b.charge_date))


def plan_for_usage_log(usage_log):
    plan = _plan()
    if not _has_ref(usage_log.patient_reference):
        plan["reasons"].append(_reason("NO_PATIENT_REFERENCE"))
        return plan
    tz = facility_tz(usage_log.facility)
    start, end = usage_log.started_at, usage_log.ended_at
    event_date = local_date(start, tz)
    mapping, level = resolve_mapping(usage_log.equipment, event_date)
    plan["mapping"], plan["level"] = mapping, level
    if mapping is None:
        plan["reasons"].append(_reason("NO_MAPPING"))
        return plan
    rule = mapping.billing_rule
    if rule == "BUNDLED":
        plan["reasons"].append(_reason("BUNDLED", ref=mapping.bundle_reference))
        return plan
    if rule == "DISABLED":
        plan["reasons"].append(_reason("DISABLED"))
        return plan
    if mapping.basis != "USAGE_LOG":
        plan["reasons"].append(_reason("ALLOCATION_BASIS"))
        return plan
    cfg = config_from_mapping(mapping)
    lpid = usage_log.public_id
    if rule == "PER_ADMISSION":
        if not _has_ref(usage_log.encounter_reference):
            plan["reasons"].append(_reason("NO_ENCOUNTER"))
            return plan
        res = engine.evaluate(cfg, start, end, tz)
        plan["lines"].append(_line(mapping, cfg, res, key=f"ENC:{usage_log.encounter_reference}:{mapping.public_id}",
                                   period_key="ENCOUNTER", start=start, end=end, charge_date=event_date))
        return plan
    res = engine.evaluate(cfg, start, end, tz)
    if res["reason"]:
        plan["reasons"].append(_reason(res["reason"]))
        return plan
    suffix = "HOURLY" if rule == "HOURLY" else "SESSION"
    plan["lines"].append(_line(mapping, cfg, res, key=f"USAGE:{lpid}:{mapping.public_id}:{suffix}",
                               period_key="SESSION", start=start, end=end, charge_date=event_date))
    return plan


# ================================================================== record creation
def _record_view(r):
    return {"record_number": r.record_number, "record_type": r.record_type, "status": r.status,
            "billing_rule": r.billing_rule, "quantity": r.quantity, "amount": r.amount, "charge_date": r.charge_date,
            "period_key": r.period_key, "patient_reference": r.patient_reference,
            "equipment_id": r.equipment_id, "exported_at": r.exported_at, "export_reference": r.export_reference}


def _insert(*, facility, request, source_type, source, equipment, line, auto_approve, key=None, corrects=None):
    """Insert one charge record. A repeated key means 'already charged' and returns None (not an error)."""
    key = key or line["key"]
    if ChargeRecord.objects.filter(facility_id=facility.id, idempotency_key=key).exists():
        return None
    year, n = next_number(facility, "CHARGE")
    now = timezone.now()
    uid = request.user.id if request is not None else None
    m = line["mapping"]
    try:
        with transaction.atomic():
            rec = ChargeRecord.objects.create(
                facility_id=facility.id, record_number=f"CHG-{year}-{n:06d}", idempotency_key=key,
                record_type="CHARGE", source_type=source_type,
                allocation_id=source.pk if source_type == "ALLOCATION" else None,
                usage_log_id=source.pk if source_type == "USAGE_LOG" else None,
                equipment_id=equipment.pk, charge_mapping_id=m.pk, charge_item_id=m.charge_item_id,
                billing_rule=line["rule"], basis=line["basis"], unit_label=line["unit_label"],
                unit_rate=line["unit_rate"], quantity=line["quantity"], amount=line["amount"],
                period_key=line["period_key"], period_start=line["period_start"], period_end=line["period_end"],
                charge_date=line["charge_date"], patient_reference=source.patient_reference,
                encounter_reference=(source.encounter_reference or None), department_id=source.department_id,
                calculation=line["calculation"],
                status="APPROVED" if auto_approve else "PENDING_REVIEW",
                approved_by=uid if auto_approve else None, approved_at=now if auto_approve else None,
                corrects_record_id=corrects.pk if corrects is not None else None, created_by=uid, updated_by=uid)
    except IntegrityError as exc:
        if _constraint(exc) == "uq_charge_records_idem":
            return None
        raise
    audit.record(request=request, action="CHARGE_CREATED", facility_id=facility.id, entity_type=ENTITY,
                 entity_public_id=rec.public_id, new=_record_view(rec))
    return rec


def _write_plan(plan, *, facility, request, source_type, source, equipment):
    auto = auto_approve_enabled(facility)
    periods = set()
    if source_type == "ALLOCATION":
        periods = set(ChargeRecord.objects.filter(
            facility_id=facility.id, allocation_id=source.pk, billing_rule="DAILY", record_type="CHARGE"
        ).values_list("period_key", flat=True))
    created, already = [], 0
    for line in plan["lines"]:
        if line["rule"] == "DAILY" and line["period_key"] in periods:
            already += 1
            continue
        rec = _insert(facility=facility, request=request, source_type=source_type, source=source,
                      equipment=equipment, line=line, auto_approve=auto)
        if rec is None:
            already += 1
        else:
            created.append(rec)
    return {"created": created, "already": already, "reasons": plan["reasons"]}


def create_charges_for_allocation(allocation, request=None, as_of=None):
    """Released allocation: all remaining charges. Active allocation: only the DAILY blocks completed as of `as_of`."""
    active = allocation.released_at is None
    if active and as_of is None:
        return {"created": [], "already": 0, "reasons": []}
    plan = plan_for_allocation(allocation, end=as_of, completed_only=active)
    return _write_plan(plan, facility=allocation.facility, request=request, source_type="ALLOCATION",
                       source=allocation, equipment=allocation.equipment)


def create_charges_for_usage_log(usage_log, request=None):
    plan = plan_for_usage_log(usage_log)
    return _write_plan(plan, facility=usage_log.facility, request=request, source_type="USAGE_LOG",
                       source=usage_log, equipment=usage_log.equipment)


def result_payload(result, warning=None):
    return {"created": [{"public_id": str(r.public_id), "record_number": r.record_number, "amount": str(r.amount),
                         "status": r.status, "billing_rule": r.billing_rule} for r in result["created"]],
            "not_billable": result["reasons"], "warning": warning}


def _audit_failure(request, facility, entity_type, entity, exc):
    log.exception("charge calculation failed (%s %s)", entity_type, entity.public_id)
    try:
        audit.record(request=request, action="CHARGE_CALCULATION_FAILED", facility_id=facility.id,
                     entity_type=entity_type, entity_public_id=entity.public_id, new={"error": type(exc).__name__})
    except Exception:
        log.exception("could not audit the charge calculation failure")


def safe_charges_for_allocation(allocation, request=None):
    """Called by the release service after a successful release. Never raises; failures are audited and reported."""
    try:
        with transaction.atomic():                                   # savepoint: a failure leaves the release intact
            return result_payload(create_charges_for_allocation(allocation, request=request))
    except Exception as exc:
        _audit_failure(request, allocation.facility, "EquipmentAllocation", allocation, exc)
        return {"created": [], "not_billable": [], "warning": GENERIC_WARNING}


def safe_charges_for_usage_log(usage_log, request=None):
    try:
        with transaction.atomic():
            return result_payload(create_charges_for_usage_log(usage_log, request=request))
    except Exception as exc:
        _audit_failure(request, usage_log.facility, "EquipmentUsageLog", usage_log, exc)
        return {"created": [], "not_billable": [], "warning": GENERIC_WARNING}


# ================================================================== preview
def _iso(v):
    return v.isoformat() if v is not None else None


def preview_for_allocation(allocation, at=None):
    plan = plan_for_allocation(allocation, end=at)
    existing = list(ChargeRecord.objects.filter(facility_id=allocation.facility_id, allocation_id=allocation.pk))
    keys = {r.idempotency_key for r in existing}
    periods = {r.period_key for r in existing if r.billing_rule == "DAILY" and r.record_type == "CHARGE"}
    accrued = sum((r.amount for r in existing if r.status != "CANCELLED"), Decimal("0"))
    lines, total = [], Decimal("0")
    for ln in plan["lines"]:
        done = ln["key"] in keys or (ln["rule"] == "DAILY" and ln["period_key"] in periods)
        if not done:
            total += ln["amount"]
        lines.append({"mapping": str(ln["mapping"].public_id), "charge_item": ln["mapping"].charge_item.name,
                      "rule": ln["rule"], "basis": ln["basis"], "period_key": ln["period_key"],
                      "period_start": _iso(ln["period_start"]), "period_end": _iso(ln["period_end"]),
                      "charge_date": ln["charge_date"].isoformat(), "quantity": str(ln["quantity"]),
                      "unit_label": ln["unit_label"], "unit_rate": str(ln["unit_rate"]), "amount": str(ln["amount"]),
                      "steps": ln["steps"], "already_charged": done})
    return {"as_of": _iso(allocation.released_at or at or timezone.now()), "released": allocation.released_at is not None,
            "mapping": mapping_out(plan["mapping"], plan["level"]) if plan["mapping"] else None,
            "lines": lines, "accrued_amount": str(accrued), "total": str(total), "reasons": plan["reasons"]}


# ================================================================== accrual and sweep
def accrue_daily_charges(facility, as_of=None, request=None):
    """Create the records of every completed day block of ACTIVE allocations with a DAILY mapping (idempotent)."""
    as_of = as_of or timezone.now()
    allocs = (EquipmentAllocation.objects.filter(facility_id=facility.id, is_active=True, released_at__isnull=True)
              .exclude(patient_reference__isnull=True).exclude(patient_reference="")
              .select_related("facility", "equipment__equipment_model").order_by("id"))
    out = {"scanned": 0, "created": 0, "already": 0, "failed": 0}
    for alloc in allocs.iterator(chunk_size=500):
        out["scanned"] += 1
        try:
            with transaction.atomic():
                res = create_charges_for_allocation(alloc, request=request, as_of=as_of)
            out["created"] += len(res["created"])
            out["already"] += res["already"]
        except Exception as exc:
            out["failed"] += 1
            _audit_failure(request, facility, "EquipmentAllocation", alloc, exc)
    with transaction.atomic():
        audit.record(request=request, action="CHARGES_ACCRUED", facility_id=facility.id, entity_type=ENTITY,
                     new={**out, "as_of": as_of})
    return out


def generate_missing_charges(facility, date_from, date_to, request=None):
    """Sweep released allocations and usage logs of the range and create the charges that are missing (idempotent)."""
    if date_to < date_from:
        raise ValidationError({"to": ["Must not be before the start date."]})
    if (date_to - date_from).days + 1 > MAX_SWEEP_DAYS:
        raise ValidationError({"to": [f"At most {MAX_SWEEP_DAYS} days per sweep."]})
    tz = facility_tz(facility)
    lo, hi = day_start(date_from, tz), day_start(date_to + timedelta(days=1), tz)
    out = {"allocations": 0, "usage_logs": 0, "created": 0, "already": 0, "failed": 0}
    allocs = (EquipmentAllocation.objects.filter(facility_id=facility.id, is_active=True,
                                                 released_at__gte=lo, released_at__lt=hi)
              .exclude(patient_reference__isnull=True).exclude(patient_reference="")
              .select_related("facility", "equipment__equipment_model").order_by("id"))
    logs = (EquipmentUsageLog.objects.filter(facility_id=facility.id, is_active=True, started_at__gte=lo,
                                             started_at__lt=hi)
            .exclude(patient_reference__isnull=True).exclude(patient_reference="")
            .select_related("facility", "equipment__equipment_model").order_by("id"))
    for kind, qs, fn, entity in (("allocations", allocs, create_charges_for_allocation, "EquipmentAllocation"),
                                 ("usage_logs", logs, create_charges_for_usage_log, "EquipmentUsageLog")):
        for src in qs.iterator(chunk_size=500):
            out[kind] += 1
            try:
                with transaction.atomic():
                    res = fn(src, request=request)
                out["created"] += len(res["created"])
                out["already"] += res["already"]
            except Exception as exc:
                out["failed"] += 1
                _audit_failure(request, facility, entity, src, exc)
    with transaction.atomic():
        audit.record(request=request, action="CHARGES_SWEPT", facility_id=facility.id, entity_type=ENTITY,
                     new={**out, "from": date_from, "to": date_to})
    return out


# ================================================================== lifecycle of a record
def _lock(request, record):
    rec = ChargeRecord.objects.select_for_update().filter(
        pk=record.pk, facility_id=request.bems.facility.id, is_active=True).first()
    if rec is None:
        raise NotFound()
    return rec


def _clean_reason(reason):
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError({"reason": ["This field is required."]})
    return reason[:500]


def _save_status(rec, request, fields):
    rec.updated_by = request.user.id
    rec.save(update_fields=list(fields) + ["updated_by"])
    rec.refresh_from_db(fields=["updated_at", "row_version"])


def approve(*, request, record):
    with transaction.atomic():
        rec = _lock(request, record)
        if rec.status != "PENDING_REVIEW":
            raise Conflict("Only records that are pending review can be approved.")
        before = _record_view(rec)
        rec.status, rec.approved_by, rec.approved_at = "APPROVED", request.user.id, timezone.now()
        _save_status(rec, request, ("status", "approved_by", "approved_at"))
        audit.record(request=request, action="CHARGE_APPROVED", facility_id=rec.facility_id, entity_type=ENTITY,
                     entity_public_id=rec.public_id, previous=before, new=_record_view(rec),
                     changed_fields=audit.diff(before, _record_view(rec)))
    return rec


def approve_many(*, request, public_ids):
    """Approve what can be approved; the rest is reported with a reason. At most 200 per call."""
    ids = list(dict.fromkeys(public_ids))
    if len(ids) > MAX_BULK:
        raise ValidationError({"ids": [f"At most {MAX_BULK} records per call."]})
    found = {r.public_id: r for r in ChargeRecord.objects.filter(
        facility_id=request.bems.facility.id, is_active=True, public_id__in=ids)}
    approved, skipped = [], []
    for pid in ids:
        rec = found.get(pid)
        if rec is None:
            skipped.append({"public_id": str(pid), "reason": "NOT_FOUND"})
            continue
        try:
            approved.append(approve(request=request, record=rec))
        except Conflict:
            skipped.append({"public_id": str(pid), "record_number": rec.record_number, "reason": "NOT_PENDING_REVIEW"})
    return {"approved": approved, "skipped": skipped}


def cancel(*, request, record, reason):
    reason = _clean_reason(reason)
    with transaction.atomic():
        rec = _lock(request, record)
        if rec.status != "PENDING_REVIEW":
            raise Conflict("Only records that are pending review can be cancelled.")
        before = _record_view(rec)
        rec.status, rec.cancelled_by, rec.cancelled_at, rec.cancel_reason = (
            "CANCELLED", request.user.id, timezone.now(), reason)
        _save_status(rec, request, ("status", "cancelled_by", "cancelled_at", "cancel_reason"))
        audit.record(request=request, action="CHARGE_CANCELLED", facility_id=rec.facility_id, entity_type=ENTITY,
                     entity_public_id=rec.public_id, previous=before, new={**_record_view(rec), "reason": reason},
                     changed_fields=audit.diff(before, _record_view(rec)))
    return rec


def reverse(*, request, record, reason):
    """Add a negative REVERSAL record and mark the original REVERSED, in one transaction. Nothing is edited."""
    reason = _clean_reason(reason)
    with transaction.atomic():
        rec = _lock(request, record)
        if rec.record_type != "CHARGE" or rec.status != "APPROVED":
            raise Conflict("Only approved charge records that are not yet reversed can be reversed.")
        facility, uid, now = request.bems.facility, request.user.id, timezone.now()
        year, n = next_number(facility, "CHARGE")
        rev = ChargeRecord.objects.create(
            facility_id=facility.id, record_number=f"CHG-{year}-{n:06d}", idempotency_key=f"{rec.idempotency_key}:REV",
            record_type="REVERSAL", source_type=rec.source_type, allocation_id=rec.allocation_id,
            usage_log_id=rec.usage_log_id, equipment_id=rec.equipment_id, charge_mapping_id=rec.charge_mapping_id,
            charge_item_id=rec.charge_item_id, billing_rule=rec.billing_rule, basis=rec.basis,
            unit_label=rec.unit_label, unit_rate=rec.unit_rate, quantity=-rec.quantity, amount=-rec.amount,
            period_key=rec.period_key, period_start=rec.period_start, period_end=rec.period_end,
            charge_date=rec.charge_date, patient_reference=rec.patient_reference,
            encounter_reference=rec.encounter_reference, department_id=rec.department_id,
            calculation={"reversal_of": rec.record_number, "reason": reason,
                         "steps": [f"Reverses {rec.record_number} ({rec.amount}). Reason: {reason}"]},
            status="APPROVED", approved_by=uid, approved_at=now, reverses_record_id=rec.pk, reversal_reason=reason,
            created_by=uid, updated_by=uid)
        before = _record_view(rec)
        rec.status, rec.reversal_reason = "REVERSED", reason
        _save_status(rec, request, ("status", "reversal_reason"))
        audit.record(request=request, action="CHARGE_REVERSED", facility_id=facility.id, entity_type=ENTITY,
                     entity_public_id=rec.public_id, previous=before,
                     new={**_record_view(rec), "reversal_record": rev.record_number, "reason": reason},
                     changed_fields=audit.diff(before, _record_view(rec)))
    return rec, rev


def recalculate(*, request, record):
    """Run the engine again for the source of a REVERSED record with today's mapping and rate; creates a new
    PENDING_REVIEW record that points at the reversed one. Records are never edited."""
    with transaction.atomic():
        rec = _lock(request, record)
        if rec.record_type != "CHARGE" or rec.status != "REVERSED":
            raise Conflict("Only reversed charge records can be recalculated.")
        if ChargeRecord.objects.filter(facility_id=rec.facility_id, corrects_record_id=rec.pk).exclude(
                status="CANCELLED").exists():
            raise Conflict("This record has already been recalculated.")
        if rec.source_type == "ALLOCATION":
            src = EquipmentAllocation.objects.select_related("facility", "equipment__equipment_model").get(
                pk=rec.allocation_id, facility_id=rec.facility_id)
            plan = plan_for_allocation(src, completed_only=src.released_at is None, end=timezone.now())
            equipment = src.equipment
        else:
            src = EquipmentUsageLog.objects.select_related("facility", "equipment__equipment_model").get(
                pk=rec.usage_log_id, facility_id=rec.facility_id)
            plan = plan_for_usage_log(src)
            equipment = src.equipment
        lines = [ln for ln in plan["lines"] if ln["period_key"] == rec.period_key]
        if not lines and len(plan["lines"]) == 1 and not rec.period_key.startswith("DAY:"):
            lines = plan["lines"]
        if not lines:
            msg = plan["reasons"][0]["message"] if plan["reasons"] else "The current mapping gives no matching charge."
            raise Conflict(f"Cannot recalculate: {msg}")
        base = re.sub(r":R[0-9]+$", "", rec.idempotency_key)
        n = ChargeRecord.objects.filter(
            facility_id=rec.facility_id, idempotency_key__regex=r"^" + re.escape(base) + r":R[0-9]+$").count() + 1
        new = _insert(facility=request.bems.facility, request=request, source_type=rec.source_type, source=src,
                      equipment=equipment, line=lines[0], auto_approve=False, key=f"{base}:R{n}", corrects=rec)
        if new is None:
            raise Conflict("This record has already been recalculated.")
        audit.record(request=request, action="CHARGE_RECALCULATED", facility_id=rec.facility_id, entity_type=ENTITY,
                     entity_public_id=new.public_id, previous=_record_view(rec), new=_record_view(new))
    return new


def mark_exported(*, request, export_reference, public_ids=None, queryset=None):
    """Stamp approved (and reversed) records that were not exported yet; reversal records are APPROVED rows."""
    fid, uid, now = request.bems.facility.id, request.user.id, timezone.now()
    ref = (export_reference or "").strip()
    if not ref or len(ref) > 100:
        raise ValidationError({"export_reference": ["Enter a reference of up to 100 characters."]})
    if (public_ids is None) == (queryset is None):
        raise ValidationError({"ids": ["Send either ids or a filter."]})
    base = queryset if queryset is not None else ChargeRecord.objects.filter(public_id__in=public_ids)
    with transaction.atomic():
        pks = list(base.filter(facility_id=fid, is_active=True, exported_at__isnull=True,
                               status__in=("APPROVED", "REVERSED")).order_by("id").values_list("pk", flat=True)
                   [:MAX_EXPORT + 1])
        if len(pks) > MAX_EXPORT:
            raise ValidationError({"non_field_errors": [f"At most {MAX_EXPORT} records per call. Narrow the filters."]})
        locked = list(ChargeRecord.objects.select_for_update().filter(
            pk__in=pks, exported_at__isnull=True, status__in=("APPROVED", "REVERSED")).values_list("pk", flat=True))
        ChargeRecord.objects.filter(pk__in=locked).update(
            exported_at=now, exported_by=uid, export_reference=ref, updated_by=uid)
        requested = len(set(public_ids)) if public_ids is not None else len(locked)
        audit.record(request=request, action="CHARGE_EXPORTED", facility_id=fid, entity_type=ENTITY,
                     new={"count": len(locked), "export_reference": ref})
    return {"exported": len(locked), "skipped": max(0, requested - len(locked)), "export_reference": ref}


# ================================================================== B4 calculator and settings
def calculate(facility, data):
    """Calculator for the mapping settings page. With only a duration, the period starts at local midnight."""
    tz = facility_tz(facility)
    cfg = engine.RuleConfig(
        billing_rule=data["billing_rule"], unit_rate=Decimal(data["unit_rate"]), unit_label=data.get("unit_label") or "unit",
        grace_minutes=data.get("grace_minutes", 0), minimum_billable_minutes=data.get("minimum_billable_minutes", 0),
        rounding=data.get("rounding", "UP"), daily_cap_amount=data.get("daily_cap_amount"),
        day_block_mode=data.get("day_block_mode", "CALENDAR_DAY"), bundle_reference=data.get("bundle_reference"))
    if data.get("start") and data.get("end"):
        start, end = data["start"], data["end"]
    else:
        start = datetime.combine(timezone.now().astimezone(tz).date(), time.min, tzinfo=tz)
        end = start + timedelta(minutes=data["duration_minutes"])
    res = engine.evaluate(cfg, start, end, tz)
    if cfg.billing_rule == "DAILY" and cfg.day_block_mode == "CALENDAR_DAY" and not (data.get("start") and data.get("end")):
        res["steps"].append("No start was given, so the period starts at midnight.")
    return res


def get_settings(facility):
    return {"auto_approve": auto_approve_enabled(facility)}


def set_auto_approve(*, request, value):
    facility, uid = request.bems.facility, request.user.id
    with transaction.atomic():
        row = ChargeSettings.objects.select_for_update().filter(facility_id=facility.id, is_active=True).first()
        if row is None:
            row = ChargeSettings.objects.create(facility_id=facility.id, auto_approve=value, created_by=uid, updated_by=uid)
            audit.record(request=request, action="CREATE", facility_id=facility.id, entity_type="ChargeSettings",
                         entity_public_id=row.public_id, new={"auto_approve": value})
        elif row.auto_approve != value:
            before = {"auto_approve": row.auto_approve}
            row.auto_approve, row.updated_by = value, uid
            row.save(update_fields=["auto_approve", "updated_by"])
            audit.record(request=request, action="UPDATE", facility_id=facility.id, entity_type="ChargeSettings",
                         entity_public_id=row.public_id, previous=before, new={"auto_approve": value},
                         changed_fields=["auto_approve"])
    return get_settings(facility)
