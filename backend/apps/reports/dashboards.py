"""Dashboards (B3). Each builder returns a list of widgets {key,title,type,data}; widgets the user may not see are omitted.
Widget data: kpi {value,format,hint} | bar/donut {items:[{label,value}]} | line {labels,series:[{name,values}]}
| heatmap {rows,columns,values,unit} | table {columns:[{key,label}],rows:[...]}."""
from collections import defaultdict
from datetime import timedelta

from django.db.models import Count, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.fields import DecimalField
from django.db.models.functions import Coalesce, TruncMonth, TruncWeek
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.allocation.models import EquipmentTransferRequest
from apps.compliance.models import AmcContract, AmcCoverage, CalibrationSchedule, EquipmentLicence, Warranty
from apps.compliance.services import compliance_due
from apps.equipment.models import Equipment, EquipmentCommissioning, EquipmentStateHistory
from apps.finance.models import DepreciationEntry, Disposal, TcoSnapshot
from apps.maintenance.models import SparePart, SparePartStockEntry, WorkOrder
from apps.masters.models import Location
from apps.safety.models import EquipmentIncident, RecallAffectedUnit

from .common import (D, ZERO, add_months_first, book_values, category_groups, day_start, facility_today, facility_tz,
                     month_list, parse_date, parse_int, parts_cost_expr, r2, years_ago)
from .downtime import combine, failure_stats, kpis, stat_sums
from .models import EquipmentDailyStat
from .pm import evaluate, pm_rows, summarise
from .stats import latest_stat_date

OPEN_EXCLUDE = ("COMPLETED", "CLOSED", "CANCELLED")
DONE = ("COMPLETED", "CLOSED")


def _w(key, title, type_, data):
    return {"key": key, "title": title, "type": type_, "data": data}


def _kpi(key, title, value, fmt="number", hint=None):
    return _w(key, title, "kpi", {"value": value, "format": fmt, "hint": hint})


def _items(pairs):
    return {"items": [{"label": str(l) if l is not None else "None", "value": v} for l, v in pairs]}


def _f(v):
    return float(v) if v is not None else 0.0


def _live(facility):
    return Equipment.objects.filter(facility_id=facility.id, is_active=True).exclude(lifecycle_stage="DISPOSED")


def _eq_info(facility):
    return {e["id"]: e for e in Equipment.objects.filter(facility_id=facility.id, is_active=True).values(
        "id", "public_id", "asset_tag", "name", "equipment_model__category_id", "owning_department_id",
        "current_location_id")}


# ================================================================== executive
def executive(facility, ctx, q):
    today, widgets = facility_today(facility), []
    base = Equipment.objects.filter(facility_id=facility.id, is_active=True)
    live = _live(facility)
    a = live.aggregate(
        total=Count("id"), commissioned=Count("id", filter=Q(lifecycle_stage="COMMISSIONED")),
        in_service=Count("id", filter=Q(operational_state="IN_SERVICE")),
        under=Count("id", filter=Q(operational_state="UNDER_MAINTENANCE")),
        oos=Count("id", filter=Q(operational_state="OUT_OF_SERVICE")),
        awaiting=Count("id", filter=Q(lifecycle_stage__in=["RECEIVED", "INSTALLED"])),
        condemned=Count("id", filter=Q(lifecycle_stage="CONDEMNED")), purchase=Sum("purchase_cost"))
    widgets += [_kpi("total_assets", "Total assets", a["total"]), _kpi("commissioned", "Commissioned", a["commissioned"]),
                _kpi("in_service", "In service", a["in_service"]), _kpi("under_maintenance", "Under maintenance", a["under"]),
                _kpi("out_of_service", "Out of service", a["oos"]),
                _kpi("awaiting", "Awaiting installation or acceptance", a["awaiting"]),
                _kpi("condemned", "Condemned", a["condemned"])]
    if ctx.has("finance.view"):
        widgets.append(_kpi("purchase_value", "Total purchase value", _f(a["purchase"]), "money"))
        widgets.append(_kpi("book_value", "Total book value", _f(sum(book_values(facility, live).values(), ZERO)), "money"))
    widgets.append(_w("by_stage", "Equipment by lifecycle stage", "donut", _items(
        base.values_list("lifecycle_stage").annotate(n=Count("id")).order_by("lifecycle_stage"))))
    group_of, cat = category_groups(facility.id), defaultdict(int)
    for cid, n in live.values_list("equipment_model__category_id").annotate(n=Count("id")).order_by():
        cat[group_of(cid)[1]] += n
    widgets.append(_w("by_category", "Equipment by category group", "bar",
                      {**_items(sorted(cat.items(), key=lambda x: -x[1])), "horizontal": True}))
    dept = live.values_list("owning_department__name").annotate(n=Count("id")).order_by("-n")[:10]
    widgets.append(_w("by_department", "Top 10 departments", "bar",
                      {**_items((d or "Unassigned", n) for d, n in dept), "horizontal": True}))
    widgets.append(_w("by_ownership", "Ownership type", "donut", _items(
        live.values_list("ownership_type").annotate(n=Count("id")).order_by("ownership_type"))))
    t2, t5, t10 = years_ago(today, 2), years_ago(today, 5), years_ago(today, 10)
    ages = EquipmentCommissioning.objects.filter(
        facility_id=facility.id, is_active=True, commissioning_date__isnull=False, equipment__is_active=True,
        equipment__lifecycle_stage="COMMISSIONED").aggregate(
        a=Count("equipment_id", distinct=True, filter=Q(commissioning_date__gt=t2)),
        b=Count("equipment_id", distinct=True, filter=Q(commissioning_date__lte=t2, commissioning_date__gt=t5)),
        c=Count("equipment_id", distinct=True, filter=Q(commissioning_date__lte=t5, commissioning_date__gt=t10)),
        d=Count("equipment_id", distinct=True, filter=Q(commissioning_date__lte=t10)))
    widgets.append(_w("age_profile", "Age profile (years since commissioning)", "bar",
                      _items([("0-2", ages["a"]), ("2-5", ages["b"]), ("5-10", ages["c"]), ("over 10", ages["d"])])))
    if ctx.has("finance.view"):
        fs = live.values_list("funding_source__name").annotate(v=Sum("purchase_cost")).order_by("-v")
        widgets.append(_w("by_funding", "Purchase value by funding source", "bar",
                          {**_items((n or "Unspecified", _f(v)) for n, v in fs), "format": "money"}))
    return widgets


# ================================================================== operations
def operations(facility, ctx, q):
    tz, today, now = facility_tz(facility), facility_today(facility), timezone.now()
    fid, widgets = facility.id, []
    wo = WorkOrder.objects.filter(facility_id=fid, is_active=True)
    open_q = ~Q(status__in=OPEN_EXCLUDE)
    k = wo.aggregate(open=Count("id", filter=open_q), overdue=Count("id", filter=open_q & Q(due_date__lt=today)),
                     bd30=Count("id", filter=Q(work_order_type="BREAKDOWN", reported_at__gte=now - timedelta(days=30))
                                & ~Q(status="CANCELLED")))
    pm30 = summarise(evaluate(r, 0, today, tz) for r in pm_rows(facility, today - timedelta(days=29), today))
    down_states = ["UNDER_MAINTENANCE", "OUT_OF_SERVICE"]
    down_qs = Equipment.objects.filter(facility_id=fid, is_active=True, operational_state__in=down_states)
    widgets += [_kpi("open_wo", "Open work orders", k["open"]), _kpi("overdue_wo", "Overdue work orders", k["overdue"]),
                _kpi("breakdowns_30", "Breakdowns (30 days)", k["bd30"]),
                _kpi("pm_compliance_30", "PM compliance (30 days)", pm30["compliance_percent"], "percent"),
                _kpi("down_now", "Equipment down now", down_qs.count())]
    if ctx.has("calibration.view"):
        c = CalibrationSchedule.objects.filter(
            facility_id=fid, is_active=True, equipment__is_active=True, equipment__lifecycle_stage="COMMISSIONED"
        ).aggregate(over=Count("id", filter=Q(next_due_date__lt=today)),
                    soon=Count("id", filter=Q(next_due_date__gte=today, next_due_date__lte=today + timedelta(days=30))))
        widgets += [_kpi("cal_overdue", "Calibration overdue", c["over"]),
                    _kpi("cal_due_30", "Calibration due in 30 days", c["soon"])]
    in30 = Q(end_date__gte=today, end_date__lte=today + timedelta(days=30))
    if ctx.has("amc.view"):
        renewed = AmcContract.objects.filter(facility_id=fid, is_active=True,
                                             renewed_from_contract_id__isnull=False).values("renewed_from_contract_id")
        widgets.append(_kpi("amc_30", "AMC expiring in 30 days", AmcContract.objects.filter(
            in30, facility_id=fid, is_active=True).exclude(pk__in=renewed).count()))
    if ctx.has("warranty.view"):
        widgets.append(_kpi("warranty_30", "Warranties expiring in 30 days",
                            Warranty.objects.filter(in30, facility_id=fid, is_active=True).count()))
    if ctx.has("licence.view"):
        renewed = EquipmentLicence.objects.filter(facility_id=fid, is_active=True,
                                                  renewed_from_licence_id__isnull=False).values("renewed_from_licence_id")
        widgets.append(_kpi("licence_30", "Licences expiring in 30 days", EquipmentLicence.objects.filter(
            facility_id=fid, is_active=True, expiry_date__gte=today,
            expiry_date__lte=today + timedelta(days=30)).exclude(pk__in=renewed).count()))
    if ctx.has("incident.view"):
        widgets.append(_kpi("open_incidents", "Open incidents", EquipmentIncident.objects.filter(
            facility_id=fid, is_active=True).exclude(status__in=("CLOSED", "CANCELLED")).count()))
    if ctx.has("recall.view"):
        widgets.append(_kpi("recall_pending", "Pending recall units", RecallAffectedUnit.objects.filter(
            facility_id=fid, is_active=True, status="PENDING").count()))
    if ctx.has("transfer.view"):
        widgets.append(_kpi("transfers_pending", "Pending transfers", EquipmentTransferRequest.objects.filter(
            facility_id=fid, is_active=True, status="PENDING").count()))
    if ctx.has("spare_part.view"):
        onhand = SparePartStockEntry.objects.filter(spare_part_id=OuterRef("pk")).values("spare_part_id").annotate(
            s=Sum("quantity")).values("s")
        low = SparePart.objects.filter(facility_id=fid, is_active=True, reorder_level__gt=0).annotate(
            onhand=Coalesce(Subquery(onhand), Value(ZERO), output_field=DecimalField())).filter(
            onhand__lte=F("reorder_level")).count()
        widgets.append(_kpi("low_stock", "Low-stock parts", low))
    year = wo.filter(created_at__gte=now - timedelta(days=365))
    widgets.append(_w("wo_by_status", "Work orders by status (12 months)", "bar", _items(
        year.values_list("status").annotate(n=Count("id")).order_by("status"))))
    widgets.append(_w("wo_by_priority", "Open work orders by priority", "bar", _items(
        wo.filter(open_q).values_list("priority").annotate(n=Count("id")).order_by("priority"))))
    age = wo.filter(open_q).aggregate(
        a=Count("id", filter=Q(created_at__gt=now - timedelta(days=8))),
        b=Count("id", filter=Q(created_at__lte=now - timedelta(days=8), created_at__gt=now - timedelta(days=31))),
        c=Count("id", filter=Q(created_at__lte=now - timedelta(days=31), created_at__gt=now - timedelta(days=91))),
        d=Count("id", filter=Q(created_at__lte=now - timedelta(days=91))))
    widgets.append(_w("wo_age", "Open work orders by age (days)", "bar",
                      _items([("0-7", age["a"]), ("8-30", age["b"]), ("31-90", age["c"]), ("over 90", age["d"])])))
    week0 = today - timedelta(days=today.weekday() + 77)
    weeks = {(week0 + timedelta(days=7 * i)): 0 for i in range(12)}
    for w, n in (wo.filter(work_order_type="BREAKDOWN", reported_at__gte=day_start(week0, tz)).exclude(status="CANCELLED")
                 .annotate(w=TruncWeek("reported_at", tzinfo=tz)).values_list("w").annotate(n=Count("id")).order_by()):
        if w.date() in weeks:
            weeks[w.date()] += n
    widgets.append(_w("breakdowns_week", "Breakdowns per week", "line", {
        "labels": [d.isoformat() for d in weeks], "series": [{"name": "Breakdowns", "values": list(weeks.values())}]}))
    m0 = add_months_first(today, -5)
    by_m = defaultdict(list)
    for r in pm_rows(facility, m0, today):
        by_m[r["due_date"].replace(day=1)].append(evaluate(r, 0, today, tz))
    months = month_list(m0, today)
    widgets.append(_w("pm_month", "PM compliance per month (%)", "line", {
        "labels": [m.strftime("%Y-%m") for m in months],
        "series": [{"name": "PM compliance %", "values": [summarise(by_m[m])["compliance_percent"] for m in months]}]}))
    rows = [r for r in compliance_due(facility=facility, can=ctx.has, within_days=90) if r["days_left"] >= 0][:10]
    widgets.append(_w("nearest_expiries", "10 nearest expiries", "table", {
        "columns": [{"key": "item_type", "label": "Type"}, {"key": "title", "label": "Item"},
                    {"key": "equipment", "label": "Equipment"}, {"key": "due_date", "label": "Due"},
                    {"key": "days_left", "label": "Days left"}],
        "rows": [{"item_type": r["item_type"], "title": r["title"],
                  "equipment": r["equipment"]["asset_tag"] if r["equipment"] else None,
                  "due_date": r["due_date"].isoformat(), "days_left": r["days_left"]} for r in rows]}))
    down = list(down_qs.values("id", "asset_tag", "name", "operational_state"))
    since = {}
    for eid, to_value, at in (EquipmentStateHistory.objects.filter(
            facility_id=fid, equipment_id__in=[d["id"] for d in down], change_type="OPERATIONAL")
            .order_by("equipment_id", "-created_at", "-id").distinct("equipment_id")
            .values_list("equipment_id", "to_value", "created_at")):
        since[eid] = (to_value, at)
    out = []
    for d in down:
        sv = since.get(d["id"])
        at = sv[1] if sv and sv[0] == d["operational_state"] else None
        out.append({"equipment": f'{d["asset_tag"]} - {d["name"]}', "state": d["operational_state"],
                    "down_since": at.astimezone(tz).strftime("%Y-%m-%d %H:%M") if at else None,
                    "hours_down": r2((now - at).total_seconds() / 3600) if at else None})
    out.sort(key=lambda r: (r["hours_down"] is None, -(r["hours_down"] or 0)))
    widgets.append(_w("down_now", "Equipment down now (top 10)", "table", {
        "columns": [{"key": "equipment", "label": "Equipment"}, {"key": "state", "label": "State"},
                    {"key": "down_since", "label": "Down since"}, {"key": "hours_down", "label": "Hours down"}],
        "rows": out[:10]}))
    return widgets


# ================================================================== utilization
def _ward_resolver(facility_id):
    locs = {l["id"]: l for l in Location.objects.filter(facility_id=facility_id).values(
        "id", "parent_location_id", "location_type", "name")}

    def ward_of(lid):
        cur, steps = lid, 0
        while cur in locs and steps < 12:
            if locs[cur]["location_type"] == "WARD":
                return cur, locs[cur]["name"]
            cur, steps = locs[cur]["parent_location_id"], steps + 1
        return (lid, locs[lid]["name"]) if lid in locs else (None, "No location")
    return ward_of


def utilization(facility, ctx, q):
    days = parse_int(q.get("days"), "days", 14, 1, 90)
    group_by = (q.get("group_by") or "department").lower()
    if group_by not in ("department", "location"):
        raise ValidationError({"group_by": ["Must be department or location."]})
    low, high = parse_int(q.get("low"), "low", 20, 0, 100), parse_int(q.get("high"), "high", 80, 0, 100)
    latest = latest_stat_date(facility)
    if latest is None:
        return [_kpi("avg_util", "Average utilization", None, "percent", "No statistics yet")]
    d_to = latest
    d_from = d_to - timedelta(days=days - 1)
    eq_qs = Equipment.objects.filter(facility_id=facility.id, is_active=True)
    sums = stat_sums(facility, eq_qs, d_from, d_to)
    tot = kpis(combine(sums.values()))
    info = _eq_info(facility)
    per = []
    for eid, s in sums.items():
        e = info.get(eid)
        if e and s["available"] > 0:
            per.append({"equipment": f'{e["asset_tag"]} - {e["name"]}', "available_hours": r2(s["available"] / 60),
                        "used_hours": r2(s["used"] / 60), "utilization_percent": r2(s["used"] * 100 / s["available"])})
    widgets = [_kpi("avg_util", "Average utilization", tot["utilization_percent"], "percent"),
               _kpi("avg_avail", "Average availability", tot["availability_percent"], "percent"),
               _kpi("used_hours", "Total used hours", r2(sum(s["used"] for s in sums.values()) / 60), "hours"),
               _kpi("under_low", f"Equipment below {low}%", sum(1 for p in per if p["utilization_percent"] < low)),
               _kpi("over_high", f"Equipment above {high}%", sum(1 for p in per if p["utilization_percent"] > high))]
    key = "equipment__owning_department_id" if group_by == "department" else "equipment__current_location_id"
    cells = defaultdict(lambda: [0, 0])
    ward_of = _ward_resolver(facility.id) if group_by == "location" else None
    for gid, d, used, avail in (EquipmentDailyStat.objects.filter(
            facility_id=facility.id, stat_date__gte=d_from, stat_date__lte=d_to, equipment__is_active=True)
            .values_list(key, "stat_date").annotate(u=Sum("used_minutes"), a=Sum("available_minutes")).order_by()):
        row = ward_of(gid) if ward_of else (gid, None)
        c = cells[(row, d)]
        c[0] += used or 0
        c[1] += avail or 0
    names = {}
    if group_by == "department":
        from apps.masters.models import Department
        names = dict(Department.objects.filter(facility_id=facility.id).values_list("id", "name"))
    row_keys = sorted({k[0] for k in cells}, key=lambda r: (r[1] or names.get(r[0], "Unassigned") or "").lower())[:40]
    dates = [d_from + timedelta(days=i) for i in range(days)]
    label = lambda r: r[1] or names.get(r[0], "Unassigned")
    widgets.append(_w("heatmap", f"Utilization by {group_by} and day", "heatmap", {
        "rows": [label(r) for r in row_keys], "columns": [d.isoformat() for d in dates], "unit": "%",
        "values": [[(r2(cells[(r, d)][0] * 100 / cells[(r, d)][1]) if (r, d) in cells and cells[(r, d)][1] else None)
                    for d in dates] for r in row_keys]}))
    elig = [p for p in per if p["available_hours"] >= 30]
    cols = [{"key": "equipment", "label": "Equipment"}, {"key": "available_hours", "label": "Available (h)"},
            {"key": "used_hours", "label": "Used (h)"}, {"key": "utilization_percent", "label": "Utilization %"}]
    widgets.append(_w("lowest", "10 lowest utilization", "table",
                      {"columns": cols, "rows": sorted(elig, key=lambda p: p["utilization_percent"])[:10]}))
    widgets.append(_w("highest", "10 highest utilization", "table",
                      {"columns": cols, "rows": sorted(elig, key=lambda p: -p["utilization_percent"])[:10]}))
    return widgets


# ================================================================== finance
def _latest_tco(facility):
    return list(TcoSnapshot.objects.filter(facility_id=facility.id, equipment__is_active=True)
                .order_by("equipment_id", "-as_of_date", "-id").distinct("equipment_id")
                .values("equipment_id", "equipment__asset_tag", "equipment__name", "total_cost_of_ownership",
                        "replacement_indicator", "maintenance_cost_ratio_percent", "age_years"))


def _monthly_costs(facility, tz, m0):
    start = day_start(m0, tz)
    labour, parts = defaultdict(lambda: ZERO), defaultdict(lambda: ZERO)
    for m, l, v in (WorkOrder.objects.filter(facility_id=facility.id, is_active=True, status__in=DONE,
                                             completed_at__gte=start)
                    .annotate(m=TruncMonth("completed_at", tzinfo=tz)).values_list("m")
                    .annotate(l=Sum("labour_cost"), v=Sum("vendor_cost")).order_by()):
        labour[m.date()] = (D(l), D(v))
    for m, c in (SparePartStockEntry.objects.filter(
            facility_id=facility.id, work_order__status__in=DONE, work_order__completed_at__gte=start)
            .annotate(m=TruncMonth("work_order__completed_at", tzinfo=tz)).values_list("m")
            .annotate(c=parts_cost_expr()).order_by()):
        parts[m.date()] = D(c)
    return labour, parts


def finance(facility, ctx, q):
    tz, today = facility_tz(facility), facility_today(facility)
    live = _live(facility)
    cap = live.aggregate(p=Sum("purchase_cost"), i=Sum("installation_cost"))
    book = sum(book_values(facility, live).values(), ZERO)
    accumulated = DepreciationEntry.objects.filter(facility_id=facility.id).aggregate(s=Sum("charge"))["s"]
    gl = Disposal.objects.filter(facility_id=facility.id, is_active=True, status="COMPLETED",
                                 disposal_date__gte=today - timedelta(days=365)).aggregate(s=Sum("gain_loss"))["s"]
    snaps = _latest_tco(facility)
    cand = [s for s in snaps if s["replacement_indicator"] != "NONE"]
    widgets = [_kpi("capitalised", "Capitalised cost", _f(D(cap["p"]) + D(cap["i"])), "money"),
               _kpi("accumulated", "Accumulated depreciation", _f(accumulated), "money"),
               _kpi("book", "Book value", _f(book), "money"),
               _kpi("gain_loss", "Gain or loss on disposals (12 months)", _f(gl), "money"),
               _kpi("candidates", "Replacement candidates", len(cand))]
    top = sorted(snaps, key=lambda s: -D(s["total_cost_of_ownership"]))[:10]
    widgets.append(_w("top_tco", "Top 10 assets by TCO", "table", {
        "columns": [{"key": "equipment", "label": "Equipment"}, {"key": "tco", "label": "TCO"},
                    {"key": "ratio", "label": "Maintenance ratio %"}, {"key": "indicator", "label": "Indicator"}],
        "rows": [{"equipment": f'{s["equipment__asset_tag"]} - {s["equipment__name"]}',
                  "tco": _f(s["total_cost_of_ownership"]), "ratio": _f(s["maintenance_cost_ratio_percent"]),
                  "indicator": s["replacement_indicator"]} for s in top]}))
    m0 = add_months_first(today, -11)
    months = month_list(m0, today)
    dep = {m: 0.0 for m in months}
    for m, c in (DepreciationEntry.objects.filter(facility_id=facility.id, period_month__gte=m0)
                 .values_list("period_month").annotate(c=Sum("charge")).order_by()):
        if m.replace(day=1) in dep:
            dep[m.replace(day=1)] = _f(c)
    labels = [m.strftime("%Y-%m") for m in months]
    widgets.append(_w("dep_month", "Monthly depreciation charge", "line",
                      {"labels": labels, "series": [{"name": "Charge", "values": list(dep.values())}]}))
    group_of, bv, info = category_groups(facility.id), book_values(facility, live), defaultdict(float)
    for pk, cid in live.values_list("pk", "equipment_model__category_id"):
        info[group_of(cid)[1]] += _f(bv.get(pk))
    widgets.append(_w("book_by_category", "Book value by category group", "bar",
                      {**_items(sorted(info.items(), key=lambda x: -x[1])), "format": "money", "horizontal": True}))
    labour, parts = _monthly_costs(facility, tz, m0)
    widgets.append(_w("maint_month", "Monthly maintenance cost", "line", {"labels": labels, "series": [{
        "name": "Labour + vendor + parts",
       "values": [_f(sum(labour.get(m, (ZERO, ZERO)), ZERO) + parts.get(m, ZERO)) for m in months]}]}))
    if ctx.has("charge.view"):
        from apps.billing.models import ChargeRecord   # Phase 11 (lazy)
        net = defaultdict(float)
        for m, s in (ChargeRecord.objects.filter(
                facility_id=facility.id, is_active=True, charge_date__gte=m0, status__in=("APPROVED", "REVERSED"))
                .annotate(m=TruncMonth("charge_date")).values_list("m").annotate(s=Sum("amount")).order_by()):
            net[m.replace(day=1)] = _f(s)
        widgets.append(_w("monthly_charges", "Monthly net charges (approved)", "line", {
            "labels": labels, "series": [{"name": "Net charges", "values": [net.get(m, 0.0) for m in months]}]}))
    return widgets


# ================================================================== analytics
def analytics(facility, ctx, q):
    tz, today, fid = facility_tz(facility), facility_today(facility), facility.id
    d_to = parse_date(q["to"], "to") if q.get("to") else today
    d_from = parse_date(q["from"], "from") if q.get("from") else today - timedelta(days=365)
    if d_from > d_to or (d_to - d_from).days > 731:
        raise ValidationError({"from": ["Invalid range (at most 2 years)."]})
    start, end = day_start(d_from, tz), day_start(d_to + timedelta(days=1), tz)
    bd = WorkOrder.objects.filter(facility_id=fid, is_active=True, work_order_type="BREAKDOWN",
                                  reported_at__gte=start, reported_at__lt=end).exclude(status="CANCELLED")
    widgets = []
    rep_eq = bd.values_list("equipment__asset_tag", "equipment__name").annotate(n=Count("id")).filter(n__gte=2) \
        .order_by("-n")[:20]
    widgets.append(_w("repeat_equipment", "Repeat failures by equipment (top 20)", "table", {
        "columns": [{"key": "equipment", "label": "Equipment"}, {"key": "failures", "label": "Breakdowns"}],
        "rows": [{"equipment": f"{t} - {n}", "failures": c} for t, n, c in rep_eq]}))
    rep_m = bd.values_list("equipment__equipment_model__model_name").annotate(n=Count("id")).filter(n__gte=2) \
        .order_by("-n")[:20]
    widgets.append(_w("repeat_model", "Repeat failures by equipment model (top 20)", "table", {
        "columns": [{"key": "model", "label": "Model"}, {"key": "failures", "label": "Breakdowns"}],
        "rows": [{"model": m, "failures": c} for m, c in rep_m]}))
    latest = latest_stat_date(facility)
    s_to = min(d_to, latest) if latest else None
    contracts = list(AmcContract.objects.filter(facility_id=fid, is_active=True, response_sla_hours__isnull=False)
                     .select_related("vendor"))
    if contracts:
        ids = [c.pk for c in contracts]
        resp = defaultdict(list)
        for cid, rep, visit in bd.filter(amc_contract_id__in=ids).values_list("amc_contract_id", "reported_at",
                                                                               "vendor_visit_at"):
            resp[cid].append(None if visit is None else (visit - rep).total_seconds() / 3600)
        cov = defaultdict(set)
        for cid, eid in AmcCoverage.objects.filter(facility_id=fid, amc_contract_id__in=ids).values_list(
                "amc_contract_id", "equipment_id"):
            cov[cid].add(eid)
        sums = stat_sums(facility, Equipment.objects.filter(facility_id=fid, pk__in={e for s in cov.values() for e in s}),
                         d_from, s_to) if s_to and s_to >= d_from else {}
        rows = []
        for c in contracts:
            hrs = [h for h in resp.get(c.pk, []) if h is not None]
            met = sum(1 for h in hrs if h <= c.response_sla_hours)
            up = kpis(combine(sums[e] for e in cov[c.pk] if e in sums))["uptime_percent"]
            rows.append({"contract": c.contract_number, "vendor": c.vendor.name, "sla_hours": c.response_sla_hours,
                         "work_orders": len(resp.get(c.pk, [])), "with_visit": len(hrs),
                         "sla_met_percent": r2(met * 100 / len(hrs)) if hrs else None,
                         "avg_response_hours": r2(sum(hrs) / len(hrs)) if hrs else None, "uptime_percent": up,
                         "uptime_guarantee": _f(c.uptime_guarantee_percent) if c.uptime_guarantee_percent is not None else None})
        widgets.append(_w("vendor_sla", "Vendor performance against AMC SLA", "table", {
            "columns": [{"key": k, "label": l} for k, l in (
                ("contract", "Contract"), ("vendor", "Vendor"), ("sla_hours", "SLA (h)"), ("work_orders", "Breakdown WOs"),
                ("with_visit", "With visit"), ("sla_met_percent", "SLA met %"), ("avg_response_hours", "Avg response (h)"),
                ("uptime_percent", "Uptime %"), ("uptime_guarantee", "Guaranteed %"))], "rows": rows}))
    if ctx.has("finance.view"):
        labour, parts = _monthly_costs(facility, tz, d_from.replace(day=1))
        months = month_list(d_from, d_to)
        widgets.append(_w("cost_trend", "Monthly cost trend", "line", {
            "labels": [m.strftime("%Y-%m") for m in months], "series": [
                {"name": "Labour", "values": [_f(labour.get(m, (ZERO, ZERO))[0]) for m in months]},
                {"name": "Vendor", "values": [_f(labour.get(m, (ZERO, ZERO))[1]) for m in months]},
                {"name": "Parts", "values": [_f(parts.get(m, ZERO)) for m in months]}]}))
    if s_to and s_to >= d_from:
        eq_qs = Equipment.objects.filter(facility_id=fid, is_active=True)
        sums, fail = stat_sums(facility, eq_qs, d_from, s_to), failure_stats(facility, eq_qs, d_from, s_to)
        group_of = category_groups(fid)
        cat_of = dict(eq_qs.values_list("pk", "equipment_model__category_id"))
        g = defaultdict(lambda: [[], [0, 0.0, 0]])
        for eid, s in sums.items():
            name = group_of(cat_of.get(eid))[1]
            g[name][0].append(s)
            f = fail.get(eid)
            if f:
                for i in range(3):
                    g[name][1][i] += f[i]
        rows = []
        for name, (ss, f) in sorted(g.items()):
            k = kpis(combine(ss), f[0], f[1], f[2])
            rows.append({"category": name, "failures": k["failures"], "mtbf_hours": k["mtbf_hours"],
                         "mttr_hours": k["mttr_hours"]})
        widgets.append(_w("mtbf_mttr", "MTBF and MTTR by category group", "table", {
            "columns": [{"key": "category", "label": "Category"}, {"key": "failures", "label": "Failures"},
                        {"key": "mtbf_hours", "label": "MTBF (h)"}, {"key": "mttr_hours", "label": "MTTR (h)"}],
            "rows": rows}))
    if ctx.has("finance.view"):
        cand = sorted((s for s in _latest_tco(facility) if s["replacement_indicator"] != "NONE"),
                      key=lambda s: -_f(s["maintenance_cost_ratio_percent"]))[:10]
        widgets.append(_w("replacement", "Top 10 replacement candidates", "table", {
            "columns": [{"key": "equipment", "label": "Equipment"}, {"key": "ratio", "label": "Maintenance ratio %"},
                        {"key": "age", "label": "Age (yrs)"}, {"key": "indicator", "label": "Indicator"}],
            "rows": [{"equipment": f'{s["equipment__asset_tag"]} - {s["equipment__name"]}',
                      "ratio": _f(s["maintenance_cost_ratio_percent"]), "age": _f(s["age_years"]),
                      "indicator": s["replacement_indicator"]} for s in cand]}))
    return widgets


BUILDERS = {"executive": executive, "operations": operations, "utilization": utilization,
            "finance": finance, "analytics": analytics}
