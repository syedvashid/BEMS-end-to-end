"""The 16 reports of Phase 10. Every query is facility-scoped and parameterised through the ORM."""
from collections import defaultdict
from datetime import timedelta

from django.db.models import Case, Count, DecimalField, Exists, Max, Min, OuterRef, Q, Sum, Value, When
from django.db.models.functions import Abs

from apps.allocation.models import EquipmentAllocation
from apps.compliance.models import AmcContract, AmcCoverage, CalibrationRecord, CalibrationSchedule, Warranty
from apps.compliance.services import status_code
from apps.equipment.models import EquipmentCommissioning
from apps.finance.models import DepreciationEntry, Disposal, TcoSnapshot
from apps.foundation.models import AuditLog, User
from apps.maintenance.models import SparePartStockEntry, WorkOrder
from apps.safety.models import EquipmentIncident, PhysicalVerificationItem, RecallAffectedUnit, RecallNotice

from .common import (D, ZERO, add_months_first, book_values, day_start, equipment_filter, parts_cost_expr, r2)
from .downtime import equipment_kpi_rows
from .pm import evaluate, pm_rows, summarise
from .registry import Column as C
from .registry import Param, ReportDef, register


def _d(days):
    return lambda t: t - timedelta(days=days)


FROM30 = Param("from", "From", "date", default=_d(30))
FROM90 = Param("from", "From", "date", default=_d(90))
TO = Param("to", "To", "date", default=lambda t: t)
TO_YESTERDAY = Param("to", "To", "date", default=_d(1))
CAT = Param("category", "Category", "ref", entity="category")
DEPT = Param("department", "Department", "ref", entity="department")
LOC = Param("location", "Location", "ref", entity="location")
EQ = Param("equipment", "Equipment", "ref", entity="equipment")
VEND = Param("vendor", "Vendor", "ref", entity="vendor")


def _label(tag, name):
    return f"{tag} - {name}"


def _eq(rc):
    p = rc.p
    return equipment_filter(rc.facility, category=p.get("category"), department=p.get("department"),
                            location=p.get("location"), equipment=p.get("equipment"))


def _range(rc, a="from", b="to"):
    """Aware [start, end) of the facility-timezone date range."""
    return day_start(rc.p[a], rc.tz), day_start(rc.p[b] + timedelta(days=1), rc.tz)


# ------------------------------------------------------------------ 1 ASSET_REGISTER
def asset_register(rc):
    p = rc.p
    base = _eq(rc)
    for f in ("lifecycle_stage", "operational_state", "ownership_type", "criticality"):
        if p.get(f):
            base = base.filter(**{f: p[f]})
    if p.get("funding_source") is not None:
        base = base.filter(funding_source_id=p["funding_source"].pk)
    comm = dict(EquipmentCommissioning.objects.filter(
        facility_id=rc.facility.id, is_active=True, commissioning_date__isnull=False, equipment__in=base,
    ).values("equipment_id").annotate(d=Min("commissioning_date")).values_list("equipment_id", "d"))
    books = book_values(rc.facility, base) if rc.can("finance.view") else {}
    qs = base.select_related("equipment_model__category", "equipment_model__manufacturer", "owning_department",
                             "current_location", "funding_source", "supplier_vendor").order_by("asset_tag")

    def gen():
        for e in qs.iterator(chunk_size=2000):
            m = e.equipment_model
            yield {
                "asset_tag": e.asset_tag, "name": e.name, "category": m.category.name, "model": m.model_name,
                "manufacturer": m.manufacturer.name, "serial_number": e.serial_number,
                "department": e.owning_department.name if e.owning_department_id else None,
                "location": e.current_location.name if e.current_location_id else None,
                "lifecycle_stage": e.lifecycle_stage, "operational_state": e.operational_state,
                "criticality": e.criticality, "ownership_type": e.ownership_type,
                "funding_source": e.funding_source.name if e.funding_source_id else None,
                "supplier": e.supplier_vendor.name if e.supplier_vendor_id else None,
                "invoice_number": e.invoice_number, "invoice_date": e.invoice_date,
                "purchase_cost": e.purchase_cost, "commissioning_date": comm.get(e.pk),
                "expected_life_years": e.expected_life_years if e.expected_life_years is not None
                else m.expected_life_years, "book_value": books.get(e.pk)}
    return gen(), None


# ------------------------------------------------------------------ 2 PM_COMPLIANCE
def pm_compliance(rc):
    p = rc.p
    grace = p.get("grace_days", 0)
    rows, results = [], []
    for r in pm_rows(rc.facility, p["from"], p["to"], p.get("category"), p.get("department")):
        ev = evaluate(r, grace, rc.today, rc.tz)
        results.append(ev)
        rows.append({"equipment": _label(r["equipment__asset_tag"], r["equipment__name"]),
                     "plan": r["maintenance_plan__name"], "due_date": r["due_date"], "status": r["status"],
                     "completed_at": r["completed_at"], "on_time": {"YES": "Yes", "NO": "No"}.get(ev, "Pending")})
    return rows, summarise(results)


# ------------------------------------------------------------------ 3 CALIBRATION_STATUS
def calibration_status(rc):
    p = rc.p
    base = _eq(rc).filter(lifecycle_stage="COMMISSIONED")
    sch = (CalibrationSchedule.objects.filter(facility_id=rc.facility.id, is_active=True, equipment__in=base)
           .select_related("equipment").order_by("next_due_date", "id"))
    last = dict(CalibrationRecord.objects.filter(facility_id=rc.facility.id, equipment__in=base)
                .order_by("equipment_id", "-performed_date", "-id").distinct("equipment_id")
                .values_list("equipment_id", "result"))
    rows = []
    for s in sch:
        st = status_code(s.next_due_date, s.lead_days, rc.today)
        days = (s.next_due_date - rc.today).days
        if p.get("status") and st != p["status"]:
            continue
        if p.get("within_days") is not None and days > p["within_days"]:
            continue
        rows.append({"equipment": _label(s.equipment.asset_tag, s.equipment.name),
                     "last_calibrated": s.last_calibrated_date, "next_due": s.next_due_date,
                     "days_overdue_or_left": days, "status": st, "last_result": last.get(s.equipment_id),
                     "unresolved_failure": last.get(s.equipment_id) == "FAIL"})
    return rows, None


# ------------------------------------------------------------------ 4 CONTRACT_EXPIRY
def contract_expiry(rc):
    p, fid, today = rc.p, rc.facility.id, rc.today
    within = p.get("within_days", 90)
    hi, lo = today + timedelta(days=within), today - timedelta(days=90)
    want = [t for t in ("AMC", "WARRANTY") if p.get("type") in (None, t)
            and rc.can({"AMC": "amc.view", "WARRANTY": "warranty.view"}[t])]
    filtered = p.get("category") is not None
    rows = []
    if "AMC" in want:
        renewed = AmcContract.objects.filter(facility_id=fid, is_active=True,
                                             renewed_from_contract_id__isnull=False).values("renewed_from_contract_id")
        qs = (AmcContract.objects.filter(facility_id=fid, is_active=True, end_date__lte=hi, end_date__gte=lo)
              .exclude(pk__in=renewed).select_related("vendor"))
        if p.get("vendor") is not None:
            qs = qs.filter(vendor_id=p["vendor"].pk)
        if filtered:
            qs = qs.filter(Exists(AmcCoverage.objects.filter(amc_contract_id=OuterRef("pk"), equipment__in=_eq(rc))))
        contracts = list(qs.order_by("end_date", "id"))
        counts = dict(AmcCoverage.objects.filter(facility_id=fid, amc_contract_id__in=[c.pk for c in contracts])
                      .values("amc_contract_id").annotate(n=Count("id")).values_list("amc_contract_id", "n"))
        for c in contracts:
            rows.append({"type": "AMC", "reference": c.contract_number, "vendor": c.vendor.name,
                         "equipment": f"{counts.get(c.pk, 0)} equipment", "start_date": c.start_date,
                         "end_date": c.end_date, "days_left": (c.end_date - today).days,
                         "contract_type": c.contract_type, "contract_cost": c.contract_cost})
    if "WARRANTY" in want:
        qs = (Warranty.objects.filter(facility_id=fid, is_active=True, end_date__lte=hi, end_date__gte=lo,
                                      equipment__in=_eq(rc)).select_related("vendor", "equipment"))
        if p.get("vendor") is not None:
            qs = qs.filter(vendor_id=p["vendor"].pk)
        for w in qs.order_by("end_date", "id"):
            rows.append({"type": "WARRANTY", "reference": w.reference_number,
                         "vendor": w.vendor.name if w.vendor_id else None,
                         "equipment": _label(w.equipment.asset_tag, w.equipment.name), "start_date": w.start_date,
                         "end_date": w.end_date, "days_left": (w.end_date - today).days,
                         "contract_type": w.warranty_type, "contract_cost": None})
    rows.sort(key=lambda r: (r["end_date"], r["type"]))
    return rows, None


# ------------------------------------------------------------------ 5 BREAKDOWN_HISTORY
def _parts_by_wo(fid, wo_qs):
    return dict(SparePartStockEntry.objects.filter(facility_id=fid, work_order__in=wo_qs)
                .values("work_order_id").annotate(c=parts_cost_expr()).values_list("work_order_id", "c"))


def breakdown_history(rc):
    p = rc.p
    start, end = _range(rc)
    qs = WorkOrder.objects.filter(facility_id=rc.facility.id, is_active=True, work_order_type="BREAKDOWN",
                                  reported_at__gte=start, reported_at__lt=end).exclude(status="CANCELLED")
    if any(p.get(k) is not None for k in ("equipment", "category", "department")):
        qs = qs.filter(equipment__in=_eq(rc))
    if p.get("vendor") is not None:
        qs = qs.filter(service_provider_vendor_id=p["vendor"].pk)
    if p.get("coverage_source"):
        qs = qs.filter(coverage_source=p["coverage_source"])
    parts = _parts_by_wo(rc.facility.id, qs) if rc.can("finance.view") else {}
    qs = qs.select_related("equipment").order_by("-reported_at", "-id")

    def gen():
        for w in qs.iterator(chunk_size=2000):
            dt = None
            if w.downtime_start is not None:
                dt = r2(((w.downtime_end or rc.now) - w.downtime_start).total_seconds() / 3600)
            yield {"wo_number": w.wo_number, "equipment": _label(w.equipment.asset_tag, w.equipment.name),
                   "reported_at": w.reported_at, "problem": w.problem_description, "priority": w.priority,
                   "status": w.status, "downtime_hours": dt, "root_cause": w.root_cause,
                   "action_taken": w.action_taken, "labour_cost": w.labour_cost, "vendor_cost": w.vendor_cost,
                   "parts_cost": parts.get(w.pk), "coverage_source": w.coverage_source}
    return gen(), None


# ------------------------------------------------------------------ 6 DOWNTIME / 7 UTILIZATION
def _kpi_report(rc):
    rows = equipment_kpi_rows(rc.facility, _eq(rc), rc.p["from"], rc.p["to"])
    rows.sort(key=lambda r: r["asset_tag"])
    for r in rows:
        r["equipment"] = _label(r["asset_tag"], r["name"])
    return rows, None


# ------------------------------------------------------------------ 8 SPARE_PARTS_CONSUMPTION
def spare_parts(rc):
    p = rc.p
    start, end = _range(rc)
    qs = SparePartStockEntry.objects.filter(
        facility_id=rc.facility.id, entry_type__in=("CONSUMPTION", "RETURN"),
        created_at__gte=start, created_at__lt=end)
    if p.get("part") is not None:
        qs = qs.filter(spare_part_id=p["part"].pk)
    if p.get("equipment") is not None or p.get("category") is not None:
        qs = qs.filter(work_order__equipment__in=_eq(rc))
    fields = ["spare_part__part_code", "spare_part__name"]
    if p.get("detail"):
        fields += ["work_order__wo_number", "work_order__equipment__asset_tag", "work_order__equipment__name"]
    dec = DecimalField(max_digits=20, decimal_places=3)
    qty = lambda t: Sum(Case(When(entry_type=t, then=Abs("quantity")), default=Value(ZERO), output_field=dec),
                        output_field=dec)
    rows = []
    for r in qs.values(*fields).annotate(cons=qty("CONSUMPTION"), ret=qty("RETURN"), cost=parts_cost_expr()) \
            .order_by(*fields):
        eq = None
        if p.get("detail") and r["work_order__equipment__asset_tag"]:
            eq = _label(r["work_order__equipment__asset_tag"], r["work_order__equipment__name"])
        rows.append({"part_code": r["spare_part__part_code"], "name": r["spare_part__name"],
                     "wo_number": r.get("work_order__wo_number"), "equipment": eq,
                     "quantity_consumed": r["cons"], "quantity_returned": r["ret"],
                     "net_quantity": D(r["cons"]) - D(r["ret"]), "cost": r["cost"]})
    return rows, None


# ------------------------------------------------------------------ 9 DEPRECIATION
def depreciation(rc):
    p = rc.p
    qs = DepreciationEntry.objects.filter(facility_id=rc.facility.id, period_month__gte=p["from_month"],
                                          period_month__lte=p["to_month"])
    if p.get("category") is not None or p.get("department") is not None:
        qs = qs.filter(equipment__in=equipment_filter(rc.facility, category=p.get("category"),
                                                      department=p.get("department")))
    qs = qs.order_by("equipment__asset_tag", "equipment_id", "period_month", "id").values(
        "equipment_id", "equipment__asset_tag", "equipment__name", "period_month", "opening_value", "charge",
        "closing_value")
    if p.get("detail"):
        return ([{"equipment": _label(r["equipment__asset_tag"], r["equipment__name"]),
                  "period_month": r["period_month"], "opening_value": r["opening_value"], "charges": r["charge"],
                  "closing_value": r["closing_value"]} for r in qs], None)
    agg, order = {}, []
    for r in qs:
        a = agg.get(r["equipment_id"])
        if a is None:
            a = agg[r["equipment_id"]] = {
                "equipment": _label(r["equipment__asset_tag"], r["equipment__name"]),
                "opening_value": r["opening_value"], "charges": ZERO, "closing_value": None}
            order.append(r["equipment_id"])
        a["charges"] += D(r["charge"])
        a["closing_value"] = r["closing_value"]
    rows = [agg[i] for i in order]
    return rows, {"equipment": len(rows), "total_charges": sum((r["charges"] for r in rows), ZERO)}


# ------------------------------------------------------------------ 10 TCO
def tco(rc):
    p = rc.p
    as_of = p.get("as_of_date", rc.today)
    qs = TcoSnapshot.objects.filter(facility_id=rc.facility.id, as_of_date__lte=as_of)
    if p.get("category") is not None or p.get("department") is not None:
        qs = qs.filter(equipment__in=equipment_filter(rc.facility, category=p.get("category"),
                                                      department=p.get("department")))
    snaps = (qs.order_by("equipment_id", "-as_of_date", "-id").distinct("equipment_id")
             .select_related("equipment"))
    rows = []
    for s in snaps:
        if p.get("indicator") and s.replacement_indicator != p["indicator"]:
            continue
        rows.append({"equipment": _label(s.equipment.asset_tag, s.equipment.name),
                     "acquisition": s.acquisition_cost, "installation": s.installation_cost,
                     "labour": s.labour_cost, "vendor": s.vendor_cost, "parts": s.parts_cost, "amc": s.amc_cost,
                     "salvage": s.salvage_value, "tco": s.total_cost_of_ownership,
                     "ratio_percent": s.maintenance_cost_ratio_percent, "age_years": s.age_years,
                     "cost_per_hour": s.cost_per_hour, "cost_per_use": s.cost_per_use,
                     "indicator": s.replacement_indicator})
    rows.sort(key=lambda r: r["equipment"])
    return rows, None


# ------------------------------------------------------------------ 11 ASSIGNMENT_HISTORY
def assignment_history(rc):
    p = rc.p
    start, end = _range(rc)
    qs = EquipmentAllocation.objects.filter(facility_id=rc.facility.id, is_active=True,
                                            assigned_at__gte=start, assigned_at__lt=end)
    if p.get("equipment") is not None:
        qs = qs.filter(equipment_id=p["equipment"].pk)
    if p.get("department") is not None:
        qs = qs.filter(department_id=p["department"].pk)
    if p.get("source_module"):
        qs = qs.filter(source_module=p["source_module"])
    qs = qs.select_related("equipment", "department", "location").order_by("-assigned_at", "-id")

    def gen():
        for a in qs.iterator(chunk_size=2000):
            yield {"equipment": _label(a.equipment.asset_tag, a.equipment.name),
                   "department": a.department.name if a.department_id else None,
                   "location": a.location.name if a.location_id else None, "source_module": a.source_module,
                   "patient_reference": a.patient_reference, "assigned_at": a.assigned_at,
                   "released_at": a.released_at, "condition_on_release": a.condition_on_release,
                   "gate_override": a.gate_override}
    return gen(), None


# ------------------------------------------------------------------ 12 INCIDENT_REGISTER
def incident_register(rc):
    p = rc.p
    start, end = _range(rc)
    qs = EquipmentIncident.objects.filter(facility_id=rc.facility.id, is_active=True,
                                          occurred_at__gte=start, occurred_at__lt=end)
    if p.get("severity"):
        qs = qs.filter(severity=p["severity"])
    if p.get("status"):
        qs = qs.filter(status=p["status"])
    if p.get("equipment") is not None:
        qs = qs.filter(equipment_id=p["equipment"].pk)
    qs = qs.select_related("equipment").order_by("-occurred_at", "-id")

    def gen():
        for i in qs.iterator(chunk_size=2000):
            until = i.closed_at or rc.now
            yield {"incident_number": i.incident_number, "equipment": _label(i.equipment.asset_tag, i.equipment.name),
                   "type": i.incident_type, "severity": i.severity, "occurred_at": i.occurred_at,
                   "status": i.status, "reportable": i.reportable_to_regulator,
                   "regulator_report_reference": i.regulator_report_reference,
                   "days_open": max(0, (until.astimezone(rc.tz).date() - i.occurred_at.astimezone(rc.tz).date()).days)}
    return gen(), None


# ------------------------------------------------------------------ 13 RECALL_STATUS
def recall_status(rc):
    p = rc.p
    fid = rc.facility.id
    notices = RecallNotice.objects.filter(facility_id=fid, is_active=True)
    if p.get("status"):
        notices = notices.filter(status=p["status"])
    if p.get("urgency"):
        notices = notices.filter(urgency=p["urgency"])
    notices = list(notices.order_by("-received_date", "-id"))
    ids = [n.pk for n in notices]
    if p.get("level") == "UNIT":
        n_by = {n.pk: n for n in notices}
        units = (RecallAffectedUnit.objects.filter(facility_id=fid, is_active=True, recall_notice_id__in=ids)
                 .select_related("equipment").order_by("recall_notice_id", "equipment__asset_tag"))
        rows = []
        for u in units:
            n = n_by[u.recall_notice_id]
            rows.append({"notice_number": n.notice_number, "reference": n.reference_number, "title": n.title,
                         "urgency": n.urgency, "action_type": n.action_type,
                         "equipment": _label(u.equipment.asset_tag, u.equipment.name), "unit_status": u.status})
        return rows, None
    agg = defaultdict(lambda: [0, 0, 0])
    for r in (RecallAffectedUnit.objects.filter(facility_id=fid, is_active=True, recall_notice_id__in=ids)
              .values("recall_notice_id").annotate(
                  total=Count("id"), pending=Count("id", filter=Q(status="PENDING")),
                  done=Count("id", filter=Q(resolved_at__isnull=False)))):
        agg[r["recall_notice_id"]] = [r["total"], r["pending"], r["done"]]
    rows = [{"notice_number": n.notice_number, "reference": n.reference_number, "title": n.title,
             "urgency": n.urgency, "action_type": n.action_type, "units_total": agg[n.pk][0],
             "units_pending": agg[n.pk][1], "units_completed": agg[n.pk][2]} for n in notices]
    return rows, None


# ------------------------------------------------------------------ 14 VERIFICATION_RESULTS
def verification_results(rc):
    v = rc.p["verification"]
    items = list(PhysicalVerificationItem.objects.filter(facility_id=rc.facility.id, verification_id=v.pk,
                                                         is_active=True)
                 .select_related("equipment", "expected_location", "found_location").order_by("equipment__asset_tag"))
    users = dict(User.objects.filter(pk__in={i.scanned_by for i in items if i.scanned_by})
                 .values_list("pk", "username"))
    rows = [{"equipment": _label(i.equipment.asset_tag, i.equipment.name),
             "expected_location": i.expected_location.name if i.expected_location_id else None,
             "found_location": i.found_location.name if i.found_location_id else None, "result": i.result,
             "tag_status": i.tag_status, "resolution": i.resolution, "scanned_at": i.scanned_at,
             "scanned_by": users.get(i.scanned_by)} for i in items]
    return rows, None


# ------------------------------------------------------------------ 15 DISPOSAL_REGISTER
def disposal_register(rc):
    p = rc.p
    qs = Disposal.objects.filter(facility_id=rc.facility.id, is_active=True,
                                 disposal_date__gte=p["from"], disposal_date__lte=p["to"])
    if p.get("method"):
        qs = qs.filter(disposal_method=p["method"])
    qs = qs.select_related("equipment", "recipient_vendor").order_by("-disposal_date", "-id")
    rows = [{"disposal_number": d.disposal_number, "equipment": _label(d.equipment.asset_tag, d.equipment.name),
             "method": d.disposal_method, "disposal_date": d.disposal_date,
             "recipient": d.recipient_name or (d.recipient_vendor.name if d.recipient_vendor_id else None),
             "book_value": d.book_value_at_disposal, "proceeds": d.proceeds_amount, "gain_loss": d.gain_loss,
             "decontamination_done": d.decontamination_done} for d in qs]
    return rows, None


# ------------------------------------------------------------------ 16 AUDIT_TRAIL
def audit_trail(rc):
    p = rc.p
    start, end = _range(rc)
    qs = AuditLog.objects.filter(facility_id=rc.facility.id, occurred_at__gte=start, occurred_at__lt=end)
    if p.get("entity_type"):
        qs = qs.filter(entity_type=p["entity_type"])
    if p.get("entity_public_id"):
        qs = qs.filter(entity_public_id=p["entity_public_id"])
    if p.get("actor"):
        qs = qs.filter(actor_username__icontains=p["actor"])
    if p.get("action"):
        qs = qs.filter(action=p["action"])
    qs = qs.order_by("-occurred_at", "-id")

    def gen():
        for a in qs.iterator(chunk_size=2000):
            yield {"occurred_at": a.occurred_at, "actor": a.actor_username or "system", "action": a.action,
                   "entity_type": a.entity_type, "entity_public_id": str(a.entity_public_id or ""),
                   "changed_fields": ", ".join(a.changed_fields or []), "request_id": a.request_id,
                   "request_path": a.request_path}
    return gen(), None


# ------------------------------------------------------------------ registrations
register(ReportDef(
    "ASSET_REGISTER", "Asset Register", "Assets", "All equipment with classification, ownership and cost.",
    asset_register, permissions=("equipment.view",),
    params=(CAT, DEPT, LOC, Param("lifecycle_stage", "Lifecycle stage", "string"),
            Param("operational_state", "Operational state", "string"), Param("ownership_type", "Ownership", "string"),
            Param("criticality", "Criticality", "string"),
            Param("funding_source", "Funding source", "ref", entity="funding_source")),
    columns=(C("asset_tag", "Asset tag"), C("name", "Name"), C("category", "Category"), C("model", "Model"),
             C("manufacturer", "Manufacturer"), C("serial_number", "Serial number"), C("department", "Department"),
             C("location", "Location"), C("lifecycle_stage", "Lifecycle"), C("operational_state", "State"),
             C("criticality", "Criticality"), C("ownership_type", "Ownership"), C("funding_source", "Funding source"),
             C("supplier", "Supplier"), C("invoice_number", "Invoice no."), C("invoice_date", "Invoice date", "date"),
             C("purchase_cost", "Purchase cost", "money", True), C("commissioning_date", "Commissioned", "date"),
             C("expected_life_years", "Expected life (yrs)", "number"), C("book_value", "Book value", "money", True))))

register(ReportDef(
    "PM_COMPLIANCE", "PM Compliance", "Maintenance", "Preventive work orders completed on time.",
    pm_compliance, permissions=("work_order.view",),
    params=(FROM30, TO, Param("grace_days", "Grace days", "integer", default=0, min=0, max=365), CAT, DEPT),
    columns=(C("equipment", "Equipment"), C("plan", "Plan"), C("due_date", "Due date", "date"), C("status", "Status"),
             C("completed_at", "Completed at", "datetime"), C("on_time", "On time"))))

register(ReportDef(
    "CALIBRATION_STATUS", "Calibration Due and Overdue", "Compliance", "Calibration schedules by status.",
    calibration_status, permissions=("calibration.view",),
    params=(Param("status", "Status", "choice", choices=("OVERDUE", "DUE_SOON", "OK")),
            Param("within_days", "Due within (days)", "integer", min=0, max=3650), CAT, DEPT),
    columns=(C("equipment", "Equipment"), C("last_calibrated", "Last calibrated", "date"),
             C("next_due", "Next due", "date"), C("days_overdue_or_left", "Days left (negative = overdue)", "number"),
             C("status", "Status"), C("last_result", "Last result"), C("unresolved_failure", "Unresolved failure", "bool"))))

register(ReportDef(
    "CONTRACT_EXPIRY", "AMC and Warranty Expiry", "Compliance", "AMC contracts and warranties ending soon.",
    contract_expiry, any_of=("amc.view", "warranty.view"),
    params=(Param("type", "Type", "choice", choices=("AMC", "WARRANTY")),
            Param("within_days", "Ending within (days)", "integer", default=90, min=0, max=3650), VEND, CAT),
    columns=(C("type", "Type"), C("reference", "Reference"), C("vendor", "Vendor"), C("equipment", "Equipment"),
             C("start_date", "Start", "date"), C("end_date", "End", "date"), C("days_left", "Days left", "number"),
             C("contract_type", "Contract type"), C("contract_cost", "Contract cost", "money", True))))

register(ReportDef(
    "BREAKDOWN_HISTORY", "Breakdown History", "Maintenance", "Breakdown work orders with downtime and cost.",
    breakdown_history, permissions=("work_order.view",),
    params=(FROM90, TO, EQ, CAT, DEPT, VEND, Param("coverage_source", "Coverage", "string")),
    columns=(C("wo_number", "WO no."), C("equipment", "Equipment"), C("reported_at", "Reported", "datetime"),
             C("problem", "Problem"), C("priority", "Priority"), C("status", "Status"),
             C("downtime_hours", "Downtime (h)", "number"), C("root_cause", "Root cause"),
             C("action_taken", "Action taken"), C("labour_cost", "Labour cost", "money", True),
             C("vendor_cost", "Vendor cost", "money", True), C("parts_cost", "Parts cost", "money", True),
             C("coverage_source", "Coverage"))))

register(ReportDef(
    "DOWNTIME", "Downtime", "Performance", "Availability, uptime, MTBF and MTTR per equipment (daily statistics).",
    _kpi_report, permissions=("work_order.view",), params=(FROM30, TO_YESTERDAY, CAT, DEPT, EQ),
    columns=(C("equipment", "Equipment"), C("in_service_hours", "In service (h)", "number"),
             C("planned_downtime_hours", "Planned downtime (h)", "number"),
             C("unplanned_downtime_hours", "Unplanned downtime (h)", "number"),
             C("availability_percent", "Availability %", "percent"), C("uptime_percent", "Uptime %", "percent"),
             C("failures", "Failures", "number"), C("mtbf_hours", "MTBF (h)", "number"),
             C("mttr_hours", "MTTR (h)", "number"))))

register(ReportDef(
    "UTILIZATION", "Utilization", "Performance", "Used time against available time (daily statistics).",
    _kpi_report, any_of=("usage.view", "allocation.view"), params=(FROM30, TO_YESTERDAY, CAT, DEPT, LOC),
    columns=(C("equipment", "Equipment"), C("available_hours", "Available (h)", "number"),
             C("used_hours", "Used (h)", "number"), C("utilization_percent", "Utilization %", "percent"),
             C("allocated_hours", "Allocated (h)", "number"), C("occupancy_percent", "Occupancy %", "percent"),
             C("sessions", "Sessions", "number"))))

register(ReportDef(
    "SPARE_PARTS_CONSUMPTION", "Spare Parts Consumption", "Maintenance", "Parts consumed and returned.",
    spare_parts, permissions=("spare_part.view",),
    params=(FROM30, TO, Param("part", "Part", "ref", entity="part"), CAT, EQ, Param("detail", "One row per work order", "boolean")),
    columns=(C("part_code", "Part code"), C("name", "Name"), C("wo_number", "WO no."), C("equipment", "Equipment"),
             C("quantity_consumed", "Consumed", "number"), C("quantity_returned", "Returned", "number"),
             C("net_quantity", "Net", "number"), C("cost", "Cost", "money", True)),
    hide_columns=lambda p: set() if p.get("detail") else {"wo_number", "equipment"}))

register(ReportDef(
    "DEPRECIATION", "Depreciation", "Finance", "Opening value, charges and closing value.",
    depreciation, permissions=("finance.view",),
    params=(Param("from_month", "From month", "month", default=lambda t: add_months_first(t, -11)),
            Param("to_month", "To month", "month", default=lambda t: t.replace(day=1)), CAT, DEPT,
            Param("detail", "Month by month", "boolean")),
    columns=(C("equipment", "Equipment"), C("period_month", "Month", "date"), C("opening_value", "Opening value", "money"),
             C("charges", "Charges", "money"), C("closing_value", "Closing value", "money")),
    hide_columns=lambda p: set() if p.get("detail") else {"period_month"}))

register(ReportDef(
    "TCO", "Total Cost of Ownership", "Finance", "Latest TCO snapshot on or before the date.",
    tco, permissions=("finance.view",),
    params=(Param("as_of_date", "As of", "date", default=lambda t: t), CAT, DEPT,
            Param("indicator", "Indicator", "string")),
    columns=(C("equipment", "Equipment"), C("acquisition", "Acquisition", "money"), C("installation", "Installation", "money"),
             C("labour", "Labour", "money"), C("vendor", "Vendor", "money"), C("parts", "Parts", "money"),
             C("amc", "AMC", "money"), C("salvage", "Salvage", "money"), C("tco", "TCO", "money"),
             C("ratio_percent", "Maintenance ratio %", "percent"), C("age_years", "Age (yrs)", "number"),
             C("cost_per_hour", "Cost per hour", "money"), C("cost_per_use", "Cost per use", "money"),
             C("indicator", "Indicator"))))

register(ReportDef(
    "ASSIGNMENT_HISTORY", "Assignment History", "Operations", "Who held the equipment and when.",
    assignment_history, permissions=("allocation.view",),
    params=(FROM30, TO, EQ, DEPT, Param("source_module", "Source", "string")),
    columns=(C("equipment", "Equipment"), C("department", "Department"), C("location", "Location"),
             C("source_module", "Source"), C("patient_reference", "Patient ref."),
             C("assigned_at", "Assigned", "datetime"), C("released_at", "Released", "datetime"),
             C("condition_on_release", "Condition on release"), C("gate_override", "Gate override", "bool"))))

register(ReportDef(
    "INCIDENT_REGISTER", "Incident Register", "Safety", "Equipment incidents.",
    incident_register, permissions=("incident.view",),
    params=(FROM90, TO, Param("severity", "Severity", "string"), Param("status", "Status", "string"), EQ),
    columns=(C("incident_number", "Incident no."), C("equipment", "Equipment"), C("type", "Type"),
             C("severity", "Severity"), C("occurred_at", "Occurred", "datetime"), C("status", "Status"),
             C("reportable", "Reportable", "bool"), C("regulator_report_reference", "Regulator ref."),
             C("days_open", "Days open", "number"))))

register(ReportDef(
    "RECALL_STATUS", "Recall Status", "Safety", "Recall notices and their units.",
    recall_status, permissions=("recall.view",),
    params=(Param("status", "Status", "string"), Param("urgency", "Urgency", "string"),
            Param("level", "Level", "choice", choices=("NOTICE", "UNIT"), default="NOTICE")),
    columns=(C("notice_number", "Notice no."), C("reference", "Reference"), C("title", "Title"),
             C("urgency", "Urgency"), C("action_type", "Action"), C("units_total", "Units", "number"),
             C("units_pending", "Pending", "number"), C("units_completed", "Completed", "number"),
             C("equipment", "Equipment"), C("unit_status", "Unit status")),
    hide_columns=lambda p: ({"equipment", "unit_status"} if p.get("level") != "UNIT"
                            else {"units_total", "units_pending", "units_completed"})))

register(ReportDef(
    "VERIFICATION_RESULTS", "Verification Results", "Safety", "Result of one physical verification.",
    verification_results, permissions=("verification.view",),
    params=(Param("verification", "Verification", "ref", required=True, entity="verification"),),
    columns=(C("equipment", "Equipment"), C("expected_location", "Expected location"),
             C("found_location", "Found location"), C("result", "Result"), C("tag_status", "Tag"),
             C("resolution", "Resolution"), C("scanned_at", "Scanned", "datetime"), C("scanned_by", "Scanned by"))))

register(ReportDef(
    "DISPOSAL_REGISTER", "Disposal Register", "Finance", "Disposals with book value and proceeds.",
    disposal_register, permissions=("disposal.view",),
    params=(Param("from", "From", "date", default=lambda t: add_months_first(t, -11)), TO,
            Param("method", "Method", "string")),
    columns=(C("disposal_number", "Disposal no."), C("equipment", "Equipment"), C("method", "Method"),
             C("disposal_date", "Date", "date"), C("recipient", "Recipient"),
             C("book_value", "Book value", "money", True), C("proceeds", "Proceeds", "money", True),
             C("gain_loss", "Gain / loss", "money", True), C("decontamination_done", "Decontaminated", "bool"))))

register(ReportDef(
    "AUDIT_TRAIL", "Audit Trail", "Audit", "Who changed what and when.",
    audit_trail, permissions=("audit.view",),
    params=(Param("entity_type", "Entity type", "string"), Param("entity_public_id", "Entity id", "string"),
            Param("actor", "Actor", "string"), Param("action", "Action", "string"), FROM30, TO),
    columns=(C("occurred_at", "When", "datetime"), C("actor", "Actor"), C("action", "Action"),
             C("entity_type", "Entity type"), C("entity_public_id", "Entity id"),
             C("changed_fields", "Changed fields"), C("request_id", "Request id"), C("request_path", "Path"))))
