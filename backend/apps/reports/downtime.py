"""In-service windows, downtime merging, per-day rows and KPI formulas (B1). Interval maths is pure."""
from bisect import bisect_right
from collections import defaultdict
from datetime import timedelta

from django.db.models import Min, Q, Sum
from django.utils import timezone

from apps.allocation.models import EquipmentAllocation, EquipmentUsageLog
from apps.equipment.models import EquipmentCommissioning, EquipmentStateHistory
from apps.maintenance.models import EquipmentHold, WorkOrder

from .common import day_start, facility_tz, local_date, r2
from .models import EquipmentDailyStat

INF = float("inf")
END_STATES = ("CONDEMNED", "DISPOSED")
SUM_KEYS = ("in_service", "planned", "unplanned", "available", "used", "allocated", "sessions", "breakdowns")


# ------------------------------------------------------------------ pure interval maths (epoch seconds)
def merge(intervals):
    out = []
    for s, e in sorted(intervals):
        if e <= s:
            continue
        if out and s <= out[-1][1]:
            if e > out[-1][1]:
                out[-1] = (out[-1][0], e)
        else:
            out.append((s, e))
    return out


def clip(intervals, lo, hi):
    out = []
    for s, e in intervals:
        s2, e2 = max(s, lo), min(e, hi)
        if s2 < e2:
            out.append((s2, e2))
    return out


def subtract(a, b):
    """a minus b; both merged and sorted."""
    out, j = [], 0
    for s, e in a:
        cur = s
        while j < len(b) and b[j][1] <= cur:
            j += 1
        k = j
        while k < len(b) and b[k][0] < e:
            if b[k][0] > cur:
                out.append((cur, b[k][0]))
            cur = max(cur, b[k][1])
            if cur >= e:
                break
            k += 1
        if cur < e:
            out.append((cur, e))
    return out


class Timeline:
    """Merged intervals with a fast 'seconds inside [lo, hi)' query."""
    __slots__ = ("iv", "ends")

    def __init__(self, iv):
        self.iv = iv
        self.ends = [e for _, e in iv]

    def seconds(self, lo, hi):
        total = 0.0
        for i in range(bisect_right(self.ends, lo), len(self.iv)):
            s, e = self.iv[i]
            if s >= hi:
                break
            total += min(e, hi) - max(s, lo)
        return total


# ------------------------------------------------------------------ KPI formulas
def empty_sums():
    return {k: 0 for k in SUM_KEYS}


def combine(sums_iter):
    out = empty_sums()
    for s in sums_iter:
        for k in SUM_KEYS:
            out[k] += s.get(k, 0)
    return out


def _pct(n, d):
    return None if not d else r2(n * 100 / d)


def kpis(sums, failures=0, repair_hours=0.0, repaired=0):
    ins, un = sums["in_service"], sums["unplanned"]
    return {
        "availability_percent": _pct(sums["available"], ins),
        "uptime_percent": _pct(ins - un, ins),
        "utilization_percent": _pct(sums["used"], sums["available"]),
        "occupancy_percent": _pct(sums["allocated"], ins),
        "failures": failures,
        "mtbf_hours": r2((ins - un) / 60 / failures) if failures else None,
        "mttr_hours": r2(repair_hours / repaired) if repaired else None,
    }


def sums_from_rows(rows):
    m = {"in_service": "in_service_minutes", "planned": "downtime_planned_minutes",
         "unplanned": "downtime_unplanned_minutes", "available": "available_minutes", "used": "used_minutes",
         "allocated": "allocated_minutes", "sessions": "session_count", "breakdowns": "breakdown_count"}
    return {k: sum(r[v] for r in rows) for k, v in m.items()}


# ------------------------------------------------------------------ loaders (set-based per batch)
def load_windows(facility, equipment_ids, tz):
    """{equipment_id: (start_date, end_date_exclusive_or_None)} for equipment that was ever commissioned."""
    ids = list(equipment_ids)
    starts = dict(EquipmentCommissioning.objects.filter(
        facility_id=facility.id, equipment_id__in=ids, is_active=True, commissioning_date__isnull=False,
    ).values("equipment_id").annotate(d=Min("commissioning_date")).values_list("equipment_id", "d"))
    last = {}
    for eid, to_value, created_at in EquipmentStateHistory.objects.filter(
            facility_id=facility.id, equipment_id__in=ids, change_type="LIFECYCLE",
    ).order_by("equipment_id", "created_at", "id").values_list("equipment_id", "to_value", "created_at"):
        last[eid] = (to_value, created_at)
    out = {}
    for eid, start in starts.items():
        end = None
        lv = last.get(eid)
        if lv and lv[0] in END_STATES:          # a later move back to COMMISSIONED makes it the last row: open-ended
            end = local_date(lv[1], tz)
        if end is not None and end <= start:
            continue
        out[eid] = (start, end)
    return out


class _Data:
    def __init__(self):
        self.unpl = defaultdict(list)
        self.plan = defaultdict(list)
        self.usage = defaultdict(list)
        self.alloc = defaultdict(list)
        self.sessions = defaultdict(lambda: defaultdict(int))
        self.breaks = defaultdict(lambda: defaultdict(int))


def load_intervals(facility, ids, tz, d_from, d_to, now):
    fid = facility.id
    rs, re_ = day_start(d_from, tz), day_start(d_to + timedelta(days=1), tz)
    data = _Data()
    holds = EquipmentHold.objects.filter(
        facility_id=fid, equipment_id__in=ids, is_active=True, started_at__lt=re_,
    ).filter(Q(released_at__isnull=True) | Q(released_at__gt=rs))
    for eid, s, e, src, wtype in holds.values_list(
            "equipment_id", "started_at", "released_at", "source_type", "work_order__work_order_type"):
        iv = (s.timestamp(), (e or now).timestamp())
        (data.plan if (src == "WORK_ORDER" and wtype == "PREVENTIVE") else data.unpl)[eid].append(iv)
    bd = WorkOrder.objects.filter(
        facility_id=fid, equipment_id__in=ids, is_active=True, work_order_type="BREAKDOWN",
        downtime_start__isnull=False, downtime_start__lt=re_,
    ).exclude(status="CANCELLED").filter(Q(downtime_end__isnull=True) | Q(downtime_end__gt=rs))
    for eid, ds, de in bd.values_list("equipment_id", "downtime_start", "downtime_end"):
        data.unpl[eid].append((ds.timestamp(), (de or now).timestamp()))
    rep = WorkOrder.objects.filter(
        facility_id=fid, equipment_id__in=ids, is_active=True, work_order_type="BREAKDOWN",
        reported_at__gte=rs, reported_at__lt=re_).exclude(status="CANCELLED")
    for eid, r in rep.values_list("equipment_id", "reported_at"):
        data.breaks[eid][local_date(r, tz)] += 1
    for eid, s, e in EquipmentUsageLog.objects.filter(
            facility_id=fid, equipment_id__in=ids, is_active=True, started_at__lt=re_, ended_at__gt=rs,
    ).values_list("equipment_id", "started_at", "ended_at"):
        data.usage[eid].append((s.timestamp(), e.timestamp()))
        if s >= rs:
            data.sessions[eid][local_date(s, tz)] += 1
    al = EquipmentAllocation.objects.filter(
        facility_id=fid, equipment_id__in=ids, is_active=True, assigned_at__lt=re_,
    ).filter(Q(released_at__isnull=True) | Q(released_at__gt=rs))
    for eid, s, e in al.values_list("equipment_id", "assigned_at", "released_at"):
        data.alloc[eid].append((s.timestamp(), (e or now).timestamp()))
    return data


def compute_rows(facility, equipment_ids, d_from, d_to, now=None):
    """Daily stat rows (dicts with equipment_id, stat_date and the minute columns) for equipment in the range."""
    tz, now = facility_tz(facility), now or timezone.now()
    windows = load_windows(facility, equipment_ids, tz)
    ids = [e for e, (s, en) in windows.items() if s <= d_to and (en is None or en > d_from)]
    if not ids:
        return []
    data = load_intervals(facility, ids, tz, d_from, d_to, now)
    rows = []
    for eid in sorted(ids):
        w_start, w_end = windows[eid]
        first = max(d_from, w_start)
        last = d_to if w_end is None else min(d_to, w_end - timedelta(days=1))
        if first > last:
            continue
        lo = day_start(w_start, tz).timestamp()
        hi = day_start(w_end, tz).timestamp() if w_end else INF
        unplanned = merge(clip(data.unpl[eid], lo, hi))
        planned = subtract(merge(clip(data.plan[eid], lo, hi)), unplanned)   # planned only where not unplanned
        t_un, t_pl = Timeline(unplanned), Timeline(planned)
        t_us, t_al = Timeline(merge(data.usage[eid])), Timeline(merge(data.alloc[eid]))
        sess, brk = data.sessions[eid], data.breaks[eid]
        d = first
        while d <= last:
            a = day_start(d, tz).timestamp()
            b = day_start(d + timedelta(days=1), tz).timestamp()
            dm = min(1440, round((b - a) / 60))
            un = min(dm, round(t_un.seconds(a, b) / 60))
            pl = min(dm - un, round(t_pl.seconds(a, b) / 60))
            rows.append({
                "equipment_id": eid, "stat_date": d, "in_service_minutes": dm,
                "downtime_planned_minutes": pl, "downtime_unplanned_minutes": un, "available_minutes": dm - pl - un,
                "used_minutes": min(1440, round(t_us.seconds(a, b) / 60)),
                "allocated_minutes": min(1440, round(t_al.seconds(a, b) / 60)),
                "session_count": sess.get(d, 0), "breakdown_count": brk.get(d, 0)})
            d += timedelta(days=1)
    return rows


# ------------------------------------------------------------------ period queries over the stored daily rows
def stat_sums(facility, eq_qs, d_from, d_to):
    rows = (EquipmentDailyStat.objects.filter(
        facility_id=facility.id, stat_date__gte=d_from, stat_date__lte=d_to, equipment__in=eq_qs)
        .values("equipment_id").annotate(
        in_service=Sum("in_service_minutes"), planned=Sum("downtime_planned_minutes"),
        unplanned=Sum("downtime_unplanned_minutes"), available=Sum("available_minutes"), used=Sum("used_minutes"),
        allocated=Sum("allocated_minutes"), sessions=Sum("session_count"), breakdowns=Sum("breakdown_count"))
        .order_by())
    return {r["equipment_id"]: {k: int(r[k] or 0) for k in SUM_KEYS} for r in rows}


def failure_stats(facility, eq_qs, d_from, d_to):
    """{equipment_id: [failures, repair_hours_sum, repaired_count]} from BREAKDOWN work orders with a downtime start."""
    tz = facility_tz(facility)
    rs, re_ = day_start(d_from, tz), day_start(d_to + timedelta(days=1), tz)
    qs = WorkOrder.objects.filter(
        facility_id=facility.id, is_active=True, work_order_type="BREAKDOWN", downtime_start__isnull=False,
        downtime_start__gte=rs, downtime_start__lt=re_, equipment__in=eq_qs).exclude(status="CANCELLED")
    out = defaultdict(lambda: [0, 0.0, 0])
    for eid, ds, de in qs.values_list("equipment_id", "downtime_start", "downtime_end"):
        out[eid][0] += 1
        if de is not None:
            out[eid][1] += (de - ds).total_seconds() / 3600
            out[eid][2] += 1
    return out


def equipment_kpi_rows(facility, eq_qs, d_from, d_to):
    sums = stat_sums(facility, eq_qs, d_from, d_to)
    if not sums:
        return []
    fail = failure_stats(facility, eq_qs, d_from, d_to)
    info = {e["id"]: e for e in eq_qs.values(
        "id", "public_id", "asset_tag", "name", "equipment_model__category__name", "owning_department__name")}
    rows = []
    for eid, s in sums.items():
        e = info.get(eid)
        if e is None:
            continue
        f = fail.get(eid, [0, 0.0, 0])
        rows.append({
            "equipment_id": eid, "public_id": str(e["public_id"]), "asset_tag": e["asset_tag"], "name": e["name"],
            "category": e["equipment_model__category__name"], "department": e["owning_department__name"],
            "in_service_hours": r2(s["in_service"] / 60), "planned_downtime_hours": r2(s["planned"] / 60),
            "unplanned_downtime_hours": r2(s["unplanned"] / 60), "available_hours": r2(s["available"] / 60),
            "used_hours": r2(s["used"] / 60), "allocated_hours": r2(s["allocated"] / 60), "sessions": s["sessions"],
            **kpis(s, f[0], f[1], f[2])})
    return rows
