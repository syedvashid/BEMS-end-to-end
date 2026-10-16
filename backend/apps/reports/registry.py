"""Report registry (B6). One register() call per report; no central switch.
Phase 11 registers BILLING_EVENTS the same way from its own module (import it in its AppConfig.ready)."""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable, Optional

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .common import facility_today, facility_tz, get_scoped, parse_date, parse_int

FORMATS = ("CSV", "XLSX", "PDF")
RESERVED = {"page", "page_size"}


@dataclass(frozen=True)
class Param:
    name: str
    label: str
    type: str = "string"        # string | date | month | integer | boolean | choice | ref
    required: bool = False
    choices: tuple = ()
    entity: Optional[str] = None  # for ref: department|category|location|equipment|vendor|funding_source|part|verification
    default: Any = None           # value or callable(today) -> value
    min: Optional[int] = None
    max: Optional[int] = None


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    type: str = "text"          # text | number | money | percent | date | datetime | bool
    finance: bool = False       # shown only to users holding finance.view


@dataclass
class ReportDef:
    code: str
    name: str
    category: str
    description: str
    run: Callable                 # run(rc) -> (rows_iterable_of_dicts, summary_dict | callable | None)
    permissions: tuple = ()       # all required (plus report.view / report.export)
    any_of: tuple = ()            # at least one required when not empty
    params: tuple = ()
    columns: tuple = ()
    hide_columns: Optional[Callable] = None   # params -> set of column keys not shown for these params


_REG = {}


def register(defn):
    if defn.code in _REG:
        raise ValueError(f"Report {defn.code} is already registered.")
    _REG[defn.code] = defn


def load_definitions():
    from . import report_definitions  # noqa: F401  (registers on import)


def get(code):
    load_definitions()
    return _REG.get(code)


def can_run(defn, ctx, base="report.view"):
    return (ctx.has(base) and all(ctx.has(p) for p in defn.permissions)
            and (not defn.any_of or any(ctx.has(p) for p in defn.any_of)))


def visible(ctx, base="report.view"):
    load_definitions()
    return sorted((d for d in _REG.values() if can_run(d, ctx, base)), key=lambda d: (d.category, d.name))


def visible_columns(defn, params, ctx):
    hide = defn.hide_columns(params) if defn.hide_columns else set()
    return [c for c in defn.columns if c.key not in hide and not (c.finance and not ctx.has("finance.view"))]


# ------------------------------------------------------------------ parameters
def _entity_model(name):
    from apps.equipment.models import Equipment
    from apps.maintenance.models import SparePart
    from apps.masters.models import Department, EquipmentCategory, FundingSource, Location, Vendor
    from apps.safety.models import PhysicalVerification
    return {"department": Department, "category": EquipmentCategory, "location": Location, "vendor": Vendor,
            "funding_source": FundingSource, "equipment": Equipment, "part": SparePart,
            "verification": PhysicalVerification}[name]


def _coerce(p, v, facility):
    if p.type == "date":
        d = parse_date(v, p.name)
        return d, d.isoformat()
    if p.type == "month":
        s = str(v).strip()
        try:
            d = date.fromisoformat(s + "-01") if len(s) == 7 else date.fromisoformat(s)
        except ValueError:
            raise ValidationError({p.name: ["Enter a valid month (YYYY-MM)."]})
        d = d.replace(day=1)
        return d, d.isoformat()
    if p.type == "integer":
        n = parse_int(v, p.name, None, p.min if p.min is not None else -10**9, p.max if p.max is not None else 10**9)
        return n, n
    if p.type == "boolean":
        s = str(v).strip().lower()
        if s in ("true", "1", "yes"):
            return True, True
        if s in ("false", "0", "no"):
            return False, False
        raise ValidationError({p.name: ["Must be true or false."]})
    if p.type == "choice":
        s = str(v).strip().upper()
        if s not in p.choices:
            raise ValidationError({p.name: [f"Must be one of: {', '.join(p.choices)}."]})
        return s, s
    if p.type == "ref":
        obj = get_scoped(_entity_model(p.entity), facility, v, p.name)
        return obj, str(obj.public_id)
    s = str(v).strip()
    if len(s) > 100:
        raise ValidationError({p.name: ["Too long."]})
    if p.choices and s.upper() not in p.choices:
        raise ValidationError({p.name: [f"Must be one of: {', '.join(p.choices)}."]})
    return (s.upper() if p.choices else s), (s.upper() if p.choices else s)


def validate_params(defn, facility, raw):
    """-> (clean values for running, JSON-safe normalised values for storing). Unknown parameters are rejected."""
    raw = {k: v for k, v in dict(raw).items() if k not in RESERVED}
    specs = {p.name: p for p in defn.params}
    unknown = sorted(set(raw) - set(specs))
    if unknown:
        raise ValidationError({k: ["Unknown parameter."] for k in unknown})
    today = facility_today(facility)
    clean, norm = {}, {}
    for p in defn.params:
        v = raw.get(p.name)
        if v in (None, ""):
            v = p.default(today) if callable(p.default) else p.default
            if v in (None, ""):
                if p.required:
                    raise ValidationError({p.name: ["This parameter is required."]})
                continue
        clean[p.name], norm[p.name] = _coerce(p, v, facility)
    for a, b in (("from", "to"), ("from_month", "to_month")):
        if a in clean and b in clean and clean[a] > clean[b]:
            raise ValidationError({b: ["Must not be before the start."]})
    return clean, norm


# ------------------------------------------------------------------ running
class RunContext:
    def __init__(self, facility, ctx, params):
        self.facility, self.ctx, self.p = facility, ctx, params
        self.tz, self.today, self.now = facility_tz(facility), facility_today(facility), timezone.now()

    def can(self, code):
        return self.ctx.has(code)


def max_rows():
    return int(getattr(settings, "BEMS_REPORT_MAX_ROWS", 50000))


def inline_rows():
    return int(getattr(settings, "BEMS_REPORT_INLINE_ROWS", 5000))


def pdf_max_rows():
    return int(getattr(settings, "BEMS_REPORT_PDF_MAX_ROWS", 2000))


def too_many_rows(cap):
    return ValidationError({"non_field_errors": [
        f"This report has more than {cap} rows. Narrow the filters (dates, department, category) and try again."]})


def cell(v, tz):
    if isinstance(v, datetime):
        return v.astimezone(tz).strftime("%Y-%m-%d %H:%M")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


def tabulate(rows, columns, tz, cap):
    """Rows (dicts) -> list of lists aligned to the visible columns; enforces the row cap."""
    keys = [c.key for c in columns]
    out = []
    for r in rows:
        if len(out) >= cap:
            raise too_many_rows(cap)
        out.append([cell(r.get(k), tz) for k in keys])
    return out


def resolve_summary(summary, tz):
    if callable(summary):
        summary = summary()
    return None if summary is None else {k: cell(v, tz) for k, v in summary.items()}
