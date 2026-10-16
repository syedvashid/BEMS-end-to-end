"""Shared helpers: facility-timezone dates, parameter parsing, equipment filters, book values, paging."""
import uuid
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from django.db import connection
from django.db.models import Case, DecimalField, ExpressionWrapper, F, Q, Sum, Value, When
from django.db.models.functions import Abs
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

DEC = DecimalField(max_digits=20, decimal_places=4)
ZERO = Decimal("0")


def D(v):
    return Decimal(v) if v is not None else ZERO


def r2(x):
    if x is None:
        return None
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ------------------------------------------------------------------ dates
def facility_tz(facility):
    try:
        return ZoneInfo(facility.timezone or "Asia/Kolkata")
    except Exception:
        return ZoneInfo("Asia/Kolkata")


def facility_today(facility, now=None):
    return (now or timezone.now()).astimezone(facility_tz(facility)).date()


def day_start(d, tz):
    return datetime.combine(d, time.min, tzinfo=tz)


def years_ago(d, n):
    try:
        return d.replace(year=d.year - n)
    except ValueError:
        return d.replace(year=d.year - n, day=28)


def add_months_first(d, n):
    total = d.year * 12 + d.month - 1 + n
    return date(total // 12, total % 12 + 1, 1)


def month_list(first, last):
    out, cur = [], first.replace(day=1)
    while cur <= last:
        out.append(cur)
        cur = add_months_first(cur, 1)
    return out


def local_date(dt, tz):
    return dt.astimezone(tz).date() if dt is not None else None


# ------------------------------------------------------------------ parsing
def parse_date(raw, name):
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(str(raw).strip())
    except ValueError:
        raise ValidationError({name: ["Enter a valid date (YYYY-MM-DD)."]})


def parse_int(raw, name, default, lo, hi):
    if raw in (None, ""):
        return default
    try:
        if isinstance(raw, bool):
            raise ValueError
        v = int(raw)
    except (TypeError, ValueError):
        raise ValidationError({name: ["A valid integer is required."]})
    if v < lo or v > hi:
        raise ValidationError({name: [f"Must be between {lo} and {hi}."]})
    return v


def parse_uuid(raw, name):
    try:
        return uuid.UUID(str(raw))
    except (ValueError, AttributeError, TypeError):
        raise ValidationError({name: ["Enter a valid id."]})


def get_scoped(model, facility, public_id, name):
    """Active row of this facility by public_id; a generic validation error otherwise (no leakage)."""
    obj = model.objects.filter(facility_id=facility.id, public_id=parse_uuid(public_id, name), is_active=True).first()
    if obj is None:
        raise ValidationError({name: ["Unknown value."]})
    return obj


def split_multi(request, name):
    vals = []
    for raw in request.query_params.getlist(name):
        vals.extend(v.strip() for v in raw.split(",") if v.strip())
    return vals


# ------------------------------------------------------------------ equipment filters
def location_subtree_ids(facility_id, root_id):
    with connection.cursor() as cur:
        cur.execute("select * from location_subtree_ids(%s, %s)", [facility_id, root_id])
        out = []
        for row in cur.fetchall():
            v = row[0]
            if isinstance(v, (list, tuple)):
                out.extend(v)
            elif v is not None:
                out.append(v)
    return out or [root_id]


def equipment_filter(facility, *, category=None, department=None, location=None, equipment=None, base=None):
    from apps.equipment.models import Equipment
    qs = base if base is not None else Equipment.objects.filter(facility_id=facility.id, is_active=True)
    if equipment is not None:
        qs = qs.filter(pk=equipment.pk)
    if department is not None:
        qs = qs.filter(owning_department_id=department.pk)
    if category is not None:
        qs = qs.filter(Q(equipment_model__category_id=category.pk)
                       | Q(equipment_model__category__parent_category_id=category.pk))
    if location is not None:
        qs = qs.filter(current_location_id__in=location_subtree_ids(facility.id, location.pk))
    return qs


def category_groups(facility_id):
    """Returns group_of(category_id) -> (group_id, group_name); the group is the top-level category."""
    from apps.masters.models import EquipmentCategory
    cats = {c.pk: (c.name, c.parent_category_id) for c in EquipmentCategory.objects.filter(facility_id=facility_id)}

    def group_of(cid):
        name, parent = cats.get(cid, ("Uncategorised", None))
        if parent in cats:
            return parent, cats[parent][0]
        return cid, name
    return group_of


def book_values(facility, eq_qs):
    """{equipment_id: Decimal}. Latest depreciation closing value, else capitalised cost."""
    from apps.finance.models import DepreciationEntry
    out = {pk: D(p) + D(i) for pk, p, i in eq_qs.values_list("pk", "purchase_cost", "installation_cost")}
    latest = (DepreciationEntry.objects.filter(facility_id=facility.id, equipment__in=eq_qs)
              .order_by("equipment_id", "-period_month", "-id").distinct("equipment_id")
              .values_list("equipment_id", "closing_value"))
    for eid, closing in latest:
        out[eid] = D(closing)
    return out


def parts_cost_expr():
    """Aggregate: consumption adds, returns subtract (sign of stored quantity is ignored)."""
    cost = ExpressionWrapper(Abs(F("quantity")) * F("unit_cost"), output_field=DEC)
    return Sum(Case(When(entry_type="CONSUMPTION", then=cost), When(entry_type="RETURN", then=-cost),
                    default=Value(ZERO), output_field=DEC), output_field=DEC)


# ------------------------------------------------------------------ paging
def paginate(request, source, default=25, cap=100):
    """{count,next,previous,results} for a list or a queryset (sliced in the database)."""
    try:
        page = max(1, int(request.query_params.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        size = min(cap, max(1, int(request.query_params.get("page_size", default))))
    except (TypeError, ValueError):
        size = default
    start = (page - 1) * size
    if isinstance(source, (list, tuple)):
        count, items = len(source), list(source[start:start + size])
    else:
        count, items = source.count(), list(source[start:start + size])

    def link(p):
        q = request.query_params.copy()
        q["page"] = p
        return request.build_absolute_uri(request.path) + "?" + q.urlencode()
    return {"count": count, "next": link(page + 1) if start + size < count else None,
            "previous": link(page - 1) if page > 1 else None, "results": items}


def page_number(request):
    try:
        return max(1, int(request.query_params.get("page", 1)))
    except (TypeError, ValueError):
        return 1
