"""PM compliance (B5). Completed on or before due_date + grace = compliant; open and past due(+grace) = non-compliant;
open and not yet past due = pending (excluded from the percentage)."""
from datetime import timedelta

from apps.maintenance.models import WorkOrder

from .common import equipment_filter, r2

DONE = ("COMPLETED", "CLOSED")


def pm_rows(facility, d_from, d_to, category=None, department=None):
    qs = WorkOrder.objects.filter(
        facility_id=facility.id, is_active=True, work_order_type="PREVENTIVE",
        due_date__gte=d_from, due_date__lte=d_to).exclude(status="CANCELLED")
    if category is not None or department is not None:
        qs = qs.filter(equipment__in=equipment_filter(facility, category=category, department=department))
    return list(qs.order_by("due_date", "id").values(
        "wo_number", "equipment__asset_tag", "equipment__name", "maintenance_plan__name",
        "due_date", "status", "completed_at"))


def evaluate(row, grace, today, tz):
    """'YES' | 'NO' | 'PENDING'."""
    due = row["due_date"] + timedelta(days=grace)
    done = row["completed_at"] if row["status"] in DONE else None
    if done is not None:
        return "YES" if done.astimezone(tz).date() <= due else "NO"
    return "NO" if due < today else "PENDING"


def summarise(results):
    """results: iterable of 'YES' | 'NO' | 'PENDING'."""
    yes = no = pend = 0
    for r in results:
        if r == "YES":
            yes += 1
        elif r == "NO":
            no += 1
        else:
            pend += 1
    total = yes + no
    return {"total": total, "compliant": yes, "pending": pend,
            "compliance_percent": r2(yes * 100 / total) if total else None}
