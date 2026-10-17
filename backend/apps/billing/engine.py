"""Billing engine (B1): pure, Decimal-based, no database access, no Django imports.

Every function takes timezone-aware datetimes plus the facility tzinfo and returns a result dict:
    {quantity, unit_label, unit_rate, amount, steps[], reason}
`reason` is None when something is charged, otherwise WITHIN_GRACE, BUNDLED or DISABLED (and amount is 0).
All amounts are rounded half up to 2 decimals.
"""
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Optional

RULES = ("HOURLY", "DAILY", "PER_USE", "PER_SESSION", "PER_ADMISSION", "BUNDLED", "DISABLED")
CHARGING_RULES = ("HOURLY", "DAILY", "PER_USE", "PER_SESSION", "PER_ADMISSION")
BASES = ("ALLOCATION", "USAGE_LOG")
ROUNDINGS = ("UP", "NEAREST")
DAY_MODES = ("CALENDAR_DAY", "BLOCK_24H")
ALLOWED_BASES = {
    "HOURLY": ("ALLOCATION", "USAGE_LOG"), "DAILY": ("ALLOCATION",), "PER_USE": ("ALLOCATION",),
    "PER_SESSION": ("USAGE_LOG",), "PER_ADMISSION": ("ALLOCATION", "USAGE_LOG"),
    "BUNDLED": ("ALLOCATION", "USAGE_LOG"), "DISABLED": ("ALLOCATION", "USAGE_LOG"),
}
CENT = Decimal("0.01")
ONE = Decimal(1)
DAY_MINUTES = Decimal(1440)


@dataclass(frozen=True)
class RuleConfig:
    billing_rule: str
    unit_rate: Decimal
    unit_label: str = "unit"
    grace_minutes: int = 0
    minimum_billable_minutes: int = 0
    rounding: str = "UP"
    daily_cap_amount: Optional[Decimal] = None
    day_block_mode: str = "CALENDAR_DAY"
    bundle_reference: Optional[str] = None


@dataclass(frozen=True)
class Block:
    index: int
    start: datetime
    end: datetime          # end of the part of the block that is billable (may be before full_end)
    full_end: datetime     # when the block is complete (calendar midnight, or start + 24 h x (index + 1))
    charge_date: object    # facility-local date of the block start


def money(x):
    return Decimal(x).quantize(CENT, rounding=ROUND_HALF_UP)


def _qty(x):
    return Decimal(x).quantize(CENT, rounding=ROUND_HALF_UP)


def minutes_between(start, end):
    return Decimal(str((end - start).total_seconds())) / 60


def fmt_minutes(minutes):
    secs = int((Decimal(minutes) * 60).to_integral_value(rounding=ROUND_HALF_UP))
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    out = f"{h} h {m:02d} min"
    return out + (f" {s:02d} s" if s else "")


def _local_midnight(d, tz):
    return datetime.combine(d, time.min, tzinfo=tz)


def _last_touched_date(end, tz):
    """Local date of the last instant the period touches (an end exactly at midnight belongs to the day before)."""
    local = end.astimezone(tz)
    d = local.date()
    return d - timedelta(days=1) if local.timetz().replace(tzinfo=None) == time.min else d


def calendar_days(start, end, tz):
    if end <= start:
        return 0
    return (_last_touched_date(end, tz) - start.astimezone(tz).date()).days + 1


def _result(cfg, quantity, amount, steps, reason=None):
    return {"quantity": _qty(quantity), "unit_label": cfg.unit_label, "unit_rate": money(cfg.unit_rate),
            "amount": money(amount), "steps": steps, "reason": reason}


def _none(cfg, steps, reason):
    return _result(cfg, 0, 0, steps, reason)


# ------------------------------------------------------------------ HOURLY
def hourly(cfg, start, end, tz):
    minutes = minutes_between(start, end)
    steps = [f"Duration {fmt_minutes(minutes)}; grace {cfg.grace_minutes} min; minimum {cfg.minimum_billable_minutes} min."]
    if minutes <= cfg.grace_minutes:
        steps.append("The duration does not exceed the grace period, so nothing is charged.")
        return _none(cfg, steps, "WITHIN_GRACE")
    billable = max(minutes, Decimal(cfg.minimum_billable_minutes))
    if billable > minutes:
        steps.append(f"The minimum billable duration of {cfg.minimum_billable_minutes} min applies.")
    hours = billable / 60
    if cfg.rounding == "NEAREST":
        units = hours.to_integral_value(rounding=ROUND_HALF_UP)
        how = "rounded to the nearest whole hour"
    else:
        units = hours.to_integral_value(rounding=ROUND_CEILING)
        how = "rounded up to a whole hour"
    if units < 1:
        units = ONE
        how += " (at least 1 unit once the grace is exceeded)"
    steps.append(f"{fmt_minutes(billable)} on an hourly rule gives {int(units)} unit{'s' if units != 1 else ''} ({how}).")
    amount = units * cfg.unit_rate
    steps.append(f"{int(units)} x {money(cfg.unit_rate)} = {money(amount)}.")
    if cfg.daily_cap_amount is not None:
        days = calendar_days(start, end, tz)
        limit = cfg.daily_cap_amount * days
        if amount > limit:
            steps.append(f"Daily cap {money(cfg.daily_cap_amount)} x {days} calendar day{'s' if days != 1 else ''} "
                         f"= {money(limit)}; the amount is limited to the cap.")
            amount = limit
        else:
            steps.append(f"Daily cap {money(cfg.daily_cap_amount)} x {days} calendar day{'s' if days != 1 else ''} "
                         f"= {money(limit)}; the cap is not reached.")
    return _result(cfg, units, amount, steps)


# ------------------------------------------------------------------ DAILY
def daily_blocks(cfg, start, end, tz):
    """Billable day blocks of a period (one unit each). len(blocks) is the DAILY quantity of the whole period."""
    if end <= start:
        return []
    if cfg.day_block_mode == "BLOCK_24H":
        minutes = minutes_between(start, end)
        if minutes <= cfg.grace_minutes:
            return []
        full = int((minutes // DAY_MINUTES))
        rem = minutes - full * DAY_MINUTES
        out = []
        for i in range(full):
            b0 = start + timedelta(hours=24 * i)
            b1 = start + timedelta(hours=24 * (i + 1))
            out.append(Block(i, b0, b1, b1, b0.astimezone(tz).date()))
        if full == 0 or rem > cfg.grace_minutes:
            b0 = start + timedelta(hours=24 * full)
            out.append(Block(full, b0, end, start + timedelta(hours=24 * (full + 1)), b0.astimezone(tz).date()))
        return out
    first = start.astimezone(tz).date()
    last = _last_touched_date(end, tz)
    out = []
    for i in range((last - first).days + 1):
        d = first + timedelta(days=i)
        full_end = _local_midnight(d + timedelta(days=1), tz)
        out.append(Block(i, max(start, _local_midnight(d, tz)), min(end, full_end), full_end, d))
    return out


def block_result(cfg, block):
    steps = [f"Day block {block.index + 1} ({block.charge_date.isoformat()}): 1 unit x {money(cfg.unit_rate)}."]
    return _result(cfg, 1, cfg.unit_rate, steps)


def daily(cfg, start, end, tz):
    minutes = minutes_between(start, end)
    mode = "24-hour blocks" if cfg.day_block_mode == "BLOCK_24H" else "calendar days"
    steps = [f"Duration {fmt_minutes(minutes)}; counting {mode}"
             + (f" with a {cfg.grace_minutes} min grace for the remainder." if cfg.day_block_mode == "BLOCK_24H" else ".")]
    blocks = daily_blocks(cfg, start, end, tz)
    if not blocks:
        steps.append("Nothing is charged for this period.")
        return _none(cfg, steps, "WITHIN_GRACE")
    units = len(blocks)
    if cfg.day_block_mode == "BLOCK_24H":
        steps.append(f"{fmt_minutes(minutes)} gives {units} block{'s' if units != 1 else ''} of 24 h.")
    else:
        steps.append(f"The period touches {units} calendar day{'s' if units != 1 else ''}.")
    amount = units * cfg.unit_rate
    steps.append(f"{units} x {money(cfg.unit_rate)} = {money(amount)}.")
    return _result(cfg, units, amount, steps)


# ------------------------------------------------------------------ one charge per use / session / admission
_PER_TEXT = {"PER_USE": "One charge per allocation (use).", "PER_SESSION": "One charge per usage session.",
             "PER_ADMISSION": "One charge per encounter and mapping."}


def per_unit(cfg):
    steps = [_PER_TEXT[cfg.billing_rule], f"1 x {money(cfg.unit_rate)} = {money(cfg.unit_rate)}."]
    return _result(cfg, 1, cfg.unit_rate, steps)


def evaluate(cfg, start, end, tz):
    """Dispatch on the billing rule. BUNDLED and DISABLED never produce a charge."""
    rule = cfg.billing_rule
    if rule == "HOURLY":
        return hourly(cfg, start, end, tz)
    if rule == "DAILY":
        return daily(cfg, start, end, tz)
    if rule in ("PER_USE", "PER_SESSION", "PER_ADMISSION"):
        return per_unit(cfg)
    if rule == "BUNDLED":
        return _none(cfg, [f"Covered by package {cfg.bundle_reference or '(no reference)'}; no separate charge."], "BUNDLED")
    if rule == "DISABLED":
        return _none(cfg, ["Billing is disabled for this equipment; no charge."], "DISABLED")
    raise ValueError("Unknown billing rule.")
