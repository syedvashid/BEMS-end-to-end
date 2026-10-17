"""Phase 11 reports, registered in the Phase 10 registry from BillingConfig.ready (one register() call each)."""
from datetime import timedelta
from decimal import Decimal
from itertools import islice

from django.db.models import Count, Q, Sum

from apps.allocation.models import EquipmentAllocation, EquipmentUsageLog
from apps.foundation.models import User
from apps.reports.common import day_start
from apps.reports.registry import Column as C
from apps.reports.registry import Param, ReportDef, register

from . import engine, services
from .models import ChargeRecord

ZERO = Decimal("0")
FROM30 = Param("from", "From", "date", default=lambda t: t - timedelta(days=30))
TO = Param("to", "To", "date", default=lambda t: t)
STATUSES = ("PENDING_REVIEW", "APPROVED", "CANCELLED", "REVERSED")


# ------------------------------------------------------------------ BILLING_EVENTS
def billing_events(rc):
    p = rc.p
    qs = ChargeRecord.objects.filter(facility_id=rc.facility.id, is_active=True,
                                     charge_date__gte=p["from"], charge_date__lte=p["to"])
    for field in ("status", "record_type", "billing_rule"):
        if p.get(field):
            qs = qs.filter(**{field: p[field]})
    if p.get("equipment") is not None:
        qs = qs.filter(equipment_id=p["equipment"].pk)
    if p.get("department") is not None:
        qs = qs.filter(department_id=p["department"].pk)
    if p.get("patient_reference"):
        qs = qs.filter(patient_reference__iexact=p["patient_reference"])
    if "exported" in p:
        qs = qs.filter(exported_at__isnull=not p["exported"])
    qs = qs.select_related("equipment", "charge_item", "department").order_by("charge_date", "record_number")
    uids = {u for u in qs.order_by().values_list("approved_by", flat=True).distinct() if u}
    names = dict(User.objects.filter(id__in=uids).values_list("id", "username")) if uids else {}

    def rows():
        for r in qs.iterator(chunk_size=2000):
            yield {
                "record_number": r.record_number, "charge_date": r.charge_date,
                "equipment": f"{r.equipment.asset_tag} - {r.equipment.name}",
                "charge_item": f"{r.charge_item.item_code} - {r.charge_item.name}", "billing_rule": r.billing_rule,
                "quantity": r.quantity, "unit_label": r.unit_label, "unit_rate": r.unit_rate, "amount": r.amount,
                "status": r.status, "record_type": r.record_type, "patient_reference": r.patient_reference,
                "encounter_reference": r.encounter_reference,
                "department": r.department.name if r.department_id else None,
                "period_start": r.period_start, "period_end": r.period_end,
                "approved_by": names.get(r.approved_by) or ("system" if r.approved_at else None),
                "approved_at": r.approved_at, "exported_at": r.exported_at, "export_reference": r.export_reference}

    def summary():
        counts = dict(qs.order_by().values_list("status").annotate(n=Count("id")))
        net = qs.order_by().aggregate(s=Sum("amount", filter=Q(status__in=("APPROVED", "REVERSED"))))["s"] or ZERO
        return {"Net billed amount (approved and reversed)": net, "Records": sum(counts.values()),
                "Pending review": counts.get("PENDING_REVIEW", 0), "Approved": counts.get("APPROVED", 0),
                "Reversed": counts.get("REVERSED", 0), "Cancelled": counts.get("CANCELLED", 0)}

    return rows(), summary


# ------------------------------------------------------------------ CHARGE_RECONCILIATION
def _chunks(iterable, n):
    it = iter(iterable)
    while True:
        chunk = list(islice(it, n))
        if not chunk:
            return
        yield chunk


def _period(obj_start, obj_end, tz):
    f = lambda d: d.astimezone(tz).strftime("%Y-%m-%d %H:%M")
    return f"{f(obj_start)} to {f(obj_end)}"


def _row(source, obj, start, end, plan, by_key, by_src, tz):
    base = {"source": source, "equipment": f"{obj.equipment.asset_tag} - {obj.equipment.name}",
            "patient_reference": obj.patient_reference, "period": _period(start, end, tz),
            "expected_amount": ZERO, "record_number": None}
    if not plan["lines"]:
        code = plan["reasons"][0]["reason"] if plan["reasons"] else "NO_MAPPING"
        if code in ("USAGE_BASIS", "ALLOCATION_BASIS"):
            return None                                  # charged from the other source: not expected here
        return {**base, "reason": code}
    found, missing = [], 0
    for ln in plan["lines"]:
        rec = by_key.get(ln["key"])
        if rec is None and ln["rule"] == "DAILY":
            rec = by_src.get((obj.pk, ln["period_key"]))
        if rec is None:
            missing += 1
        else:
            found.append(rec)
    if missing:
        reason = "MISSING_RECORD"
    elif all(r.status == "CANCELLED" for r in found):
        reason = "CANCELLED"
    else:
        reason = "CHARGED"
    numbers = [r.record_number for r in found]
    shown = ", ".join(numbers[:3]) + (f" (+{len(numbers) - 3} more)" if len(numbers) > 3 else "")
    return {**base, "expected_amount": sum((ln["amount"] for ln in plan["lines"]), ZERO),
            "record_number": shown or None, "reason": reason}


def charge_reconciliation(rc):
    p, fac, tz = rc.p, rc.facility, rc.tz
    lo, hi = day_start(p["from"], tz), day_start(p["to"] + timedelta(days=1), tz)
    source = p.get("source")

    def rows():
        if source in (None, "ALLOCATION"):
            qs = (EquipmentAllocation.objects.filter(facility_id=fac.id, is_active=True, released_at__gte=lo,
                                                     released_at__lt=hi)
                  .select_related("facility", "equipment__equipment_model").order_by("released_at", "id"))
            for chunk in _chunks(qs.iterator(chunk_size=500), 500):
                plans = [services.plan_for_allocation(a) for a in chunk]
                keys = [ln["key"] for pl in plans for ln in pl["lines"]]
                recs = ChargeRecord.objects.filter(facility_id=fac.id).filter(
                    Q(idempotency_key__in=keys) | Q(allocation_id__in=[a.pk for a in chunk], billing_rule="DAILY",
                                                    record_type="CHARGE"))
                by_key = {r.idempotency_key: r for r in recs}
                by_src = {(r.allocation_id, r.period_key): r for r in recs if r.allocation_id}
                for a, pl in zip(chunk, plans):
                    row = _row("ALLOCATION", a, a.assigned_at, a.released_at, pl, by_key, by_src, tz)
                    if row:
                        yield row
        if source in (None, "USAGE_LOG"):
            qs = (EquipmentUsageLog.objects.filter(facility_id=fac.id, is_active=True, started_at__gte=lo,
                                                   started_at__lt=hi)
                  .select_related("facility", "equipment__equipment_model").order_by("started_at", "id"))
            for chunk in _chunks(qs.iterator(chunk_size=500), 500):
                plans = [services.plan_for_usage_log(u) for u in chunk]
                keys = [ln["key"] for pl in plans for ln in pl["lines"]]
                by_key = {r.idempotency_key: r for r in
                          ChargeRecord.objects.filter(facility_id=fac.id, idempotency_key__in=keys)}
                for u, pl in zip(chunk, plans):
                    row = _row("USAGE_LOG", u, u.started_at, u.ended_at, pl, by_key, {}, tz)
                    if row:
                        yield row

    return rows(), None


register(ReportDef(
    "BILLING_EVENTS", "Billing Events", "Finance",
    "Charge records for the billing team: approved, reversed and pending charges with export status.",
    billing_events, permissions=("charge.view",),
    params=(FROM30, TO, Param("status", "Status", "choice", choices=STATUSES),
            Param("record_type", "Record type", "choice", choices=("CHARGE", "REVERSAL")),
            Param("equipment", "Equipment", "ref", entity="equipment"),
            Param("department", "Department", "ref", entity="department"),
            Param("patient_reference", "Patient reference", "string"),
            Param("billing_rule", "Billing rule", "choice", choices=engine.CHARGING_RULES),
            Param("exported", "Exported", "boolean")),
    columns=(C("record_number", "Record no."), C("charge_date", "Charge date", "date"), C("equipment", "Equipment"),
             C("charge_item", "Charge item"), C("billing_rule", "Billing rule"), C("quantity", "Quantity", "number"),
             C("unit_label", "Unit"), C("unit_rate", "Unit rate", "money"), C("amount", "Amount", "money"),
             C("status", "Status"), C("record_type", "Type"), C("patient_reference", "Patient reference"),
             C("encounter_reference", "Encounter reference"), C("department", "Department"),
             C("period_start", "Period start", "datetime"), C("period_end", "Period end", "datetime"),
             C("approved_by", "Approved by"), C("approved_at", "Approved at", "datetime"),
             C("exported_at", "Exported at", "datetime"), C("export_reference", "Export reference"))))

register(ReportDef(
    "CHARGE_RECONCILIATION", "Charge Reconciliation", "Finance",
    "Released allocations and usage logs with the charge they should have and whether the record exists.",
    charge_reconciliation, permissions=("charge.view",),
    params=(FROM30, TO, Param("source", "Source", "choice", choices=engine.BASES)),
    columns=(C("source", "Source"), C("equipment", "Equipment"), C("patient_reference", "Patient reference"),
             C("period", "Period"), C("expected_amount", "Expected amount", "money"),
             C("record_number", "Record no."), C("reason", "Result"))))
