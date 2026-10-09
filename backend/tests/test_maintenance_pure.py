"""Pure unit tests (no database). Run: python -m pytest -q tests/test_maintenance_pure.py"""
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from apps.maintenance import services

SQL_DIR = Path(__file__).resolve().parents[2] / "db" / "sql"


def test_month_end_and_interval_maths():
    assert services.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert services.add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert services.add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)
    assert services.add_months(date(2026, 12, 15), 1) == date(2027, 1, 15)
    assert services.add_interval(date(2026, 3, 1), "DAYS", 90) == date(2026, 5, 30)
    assert services.add_interval(date(2026, 3, 31), "MONTHS", 6) == date(2026, 9, 30)


def test_python_transition_table_matches_the_sql_seed():
    sql = (SQL_DIR / "028_work_orders.sql").read_text()
    seeded = set(re.findall(r"\('([A-Z_]+)','([A-Z_]+)'\)", sql.split("insert into work_order_transitions")[1].split("on conflict")[0]))
    assert seeded == services.TRANSITIONS


def test_every_status_pair_outside_the_table_is_blocked():
    statuses = ["OPEN", "ASSIGNED", "IN_PROGRESS", "WAITING_PARTS", "COMPLETED", "CLOSED", "CANCELLED"]
    for a in statuses:
        for b in statuses:
            wo = SimpleNamespace(status=a)
            if (a, b) in services.TRANSITIONS:
                services._check_transition(wo, b)
            else:
                try:
                    services._check_transition(wo, b)
                except Exception as exc:
                    assert getattr(exc, "status_code", None) == 409
                else:
                    raise AssertionError(f"{a} -> {b} should be blocked")


def test_out_of_range_measurement_is_forced_to_fail():
    item = SimpleNamespace(item_type="MEASUREMENT", result="PASS", measured_value=Decimal("9.9"),
                           min_value=Decimal("1"), max_value=Decimal("5"))
    assert services.evaluate_item(item) == "FAIL"
    item.measured_value = Decimal("3")
    assert services.evaluate_item(item) == "PASS"
    item.result, item.measured_value = "NA", Decimal("99")
    assert services.evaluate_item(item) == "NA"
    chk = SimpleNamespace(item_type="CHECK", result="PASS", measured_value=None, min_value=None, max_value=None)
    assert services.evaluate_item(chk) == "PASS"


def test_permission_sql_maps_department_user_to_view_and_add_only():
    sql = (SQL_DIR / "031_maintenance_permissions.sql").read_text()
    assert "r.code = 'DEPARTMENT_USER' and p.code in ('work_order.view','work_order.add')" in sql
