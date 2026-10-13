"""Pure depreciation maths (Decimal only, no database, no Django).

Used by the monthly run, the projection and the disposal stub. Every amount is rounded half up to 2 decimals
per entry. A policy change only affects months that have not been charged yet, because callers pass the
opening value of the first month still to be charged.
"""
import calendar
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal("0.00")
_CENT = Decimal("0.01")
_HUNDRED = Decimal(100)
_TWELVE = Decimal(12)

STRAIGHT_LINE = "STRAIGHT_LINE"
WRITTEN_DOWN_VALUE = "WRITTEN_DOWN_VALUE"
PROJECTION_CAP_MONTHS = 600


def q2(value):
    """Round half up to 2 decimals."""
    return Decimal(value).quantize(_CENT, rounding=ROUND_HALF_UP)


def D(value):
    """None counts as zero; floats are converted through str to avoid binary noise."""
    if value is None:
        return Decimal(0)
    return value if isinstance(value, Decimal) else Decimal(str(value))


def month_start(d):
    return d.replace(day=1)


def add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def days_in_month(d):
    return calendar.monthrange(d.year, d.month)[1]


def capitalised_cost(purchase_cost, installation_cost):
    return q2(D(purchase_cost) + D(installation_cost))


def salvage_amount(cost, salvage_percent):
    return q2(D(cost) * D(salvage_percent) / _HUNDRED)


def start_date_for(start_rule, commissioning_date, invoice_date):
    """COMMISSIONING_DATE -> commissioning date. INVOICE_DATE -> invoice date, falling back to commissioning."""
    if start_rule == "INVOICE_DATE":
        return invoice_date or commissioning_date
    return commissioning_date


@dataclass(frozen=True)
class EntryCalc:
    period_month: date
    opening_value: Decimal
    charge: Decimal
    closing_value: Decimal
    days_charged: int


def _raw_monthly(method, cost, salvage, opening, useful_life_years, rate_percent):
    if method == STRAIGHT_LINE:
        return (cost - salvage) / (D(useful_life_years) * _TWELVE)
    if method == WRITTEN_DOWN_VALUE:
        return opening * D(rate_percent) / _HUNDRED / _TWELVE
    raise ValueError("Unknown depreciation method")


def month_charge(*, method, cost, salvage, opening, useful_life_years, rate_percent, fraction=Decimal(1)):
    """Charge for one month: raw monthly amount x fraction, rounded, never taking the value below salvage."""
    room = opening - salvage
    if room <= 0:
        return ZERO
    charge = q2(_raw_monthly(method, cost, salvage, opening, useful_life_years, rate_percent) * fraction)
    return min(charge, room)


def generate_entries(*, method, cost, salvage, start_date, opening_value, from_month, to_month,
                     useful_life_years=None, rate_percent=None, max_entries=None):
    """Monthly entries for every month from from_month through to_month (both first-of-month dates).

    The first month of the asset (the start date's month) is prorated by days: days from the start date to the
    end of the month, both inclusive, divided by the days in that month. Stops when the closing value reaches
    salvage (or when a charge rounds to zero)."""
    out = []
    opening = q2(D(opening_value))
    month = month_start(from_month)
    start_month = month_start(start_date)
    last = month_start(to_month)
    while month <= last:
        if max_entries is not None and len(out) >= max_entries:
            break
        dim = days_in_month(month)
        if month == start_month:
            days = dim - start_date.day + 1
        else:
            days = dim
        charge = month_charge(
            method=method, cost=cost, salvage=salvage, opening=opening, useful_life_years=useful_life_years,
            rate_percent=rate_percent, fraction=Decimal(days) / Decimal(dim))
        if charge <= 0:
            break
        closing = opening - charge
        out.append(EntryCalc(month, opening, charge, closing, days))
        opening = closing
        month = add_months(month, 1)
    return out


def stub_entry(*, method, cost, salvage, start_date, opening_value, disposal_date,
               useful_life_years=None, rate_percent=None):
    """Disposal-month entry prorated by days up to disposal_date (inclusive). None when nothing is left to charge."""
    month = month_start(disposal_date)
    dim = days_in_month(month)
    first_day = max(month, start_date)
    days = (disposal_date - first_day).days + 1
    if days <= 0:
        return None
    opening = q2(D(opening_value))
    charge = month_charge(
        method=method, cost=cost, salvage=salvage, opening=opening, useful_life_years=useful_life_years,
        rate_percent=rate_percent, fraction=Decimal(days) / Decimal(dim))
    if charge <= 0:
        return None
    return EntryCalc(month, opening, charge, opening - charge, days)


def projection(*, method, cost, salvage, start_date, last_closing, last_month, useful_life_years=None,
               rate_percent=None):
    """Future schedule from the month after the last entry down to salvage (cap 600 months).
    With no entry yet, pass last_closing=None and last_month=None: it starts at the start month with the cost."""
    if last_month is None:
        opening, first = cost, month_start(start_date)
    else:
        opening, first = q2(D(last_closing)), add_months(month_start(last_month), 1)
    return generate_entries(
        method=method, cost=cost, salvage=salvage, start_date=start_date, opening_value=opening,
        from_month=first, to_month=add_months(first, PROJECTION_CAP_MONTHS), useful_life_years=useful_life_years,
        rate_percent=rate_percent, max_entries=PROJECTION_CAP_MONTHS)


# ------------------------------------------------------------------ pure TCO helpers (used by tco.py)
def amc_fraction(contract_start, contract_end, as_of_date):
    """Share of the contract elapsed up to as_of_date: days inside [start, min(end, as_of)] / total days, 0..1."""
    total = (contract_end - contract_start).days + 1
    if total <= 0:
        return Decimal(0)
    inside = (min(contract_end, as_of_date) - contract_start).days + 1
    inside = max(0, min(inside, total))
    return Decimal(inside) / Decimal(total)


def age_years(commissioning_date, as_of_date):
    if commissioning_date is None or as_of_date < commissioning_date:
        return None
    return (Decimal((as_of_date - commissioning_date).days) / Decimal("365.25")).quantize(_CENT, rounding=ROUND_HALF_UP)


def replacement_indicator(ratio_percent, age, expected_life, threshold_percent):
    """REPLACE_RECOMMENDED when both conditions hold, REVIEW when exactly one does, else NONE.
    Unknown inputs count as not true. Returns (indicator, reasons)."""
    reasons = []
    if ratio_percent is not None and ratio_percent > D(threshold_percent):
        reasons.append("MAINTENANCE_COST_ABOVE_THRESHOLD")
    if age is not None and expected_life is not None and age > D(expected_life):
        reasons.append("AGE_BEYOND_EXPECTED_LIFE")
    indicator = {0: "NONE", 1: "REVIEW", 2: "REPLACE_RECOMMENDED"}[len(reasons)]
    return indicator, reasons
