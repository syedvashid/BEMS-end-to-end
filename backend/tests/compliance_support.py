import uuid
from datetime import date, timedelta

from django.db import connection

from apps.equipment.models import Equipment
from apps.masters.models import EquipmentCategory, EquipmentModel, Vendor

API = "/api/v1"


def client(api, user, fac):
    return api(user.username, fac)


def make_equipment(fac, stage="COMMISSIONED", cal_days=365):
    cat = EquipmentCategory.objects.filter(facility=fac, is_active=True).first() or EquipmentCategory.objects.create(
        facility=fac, code=f"C{uuid.uuid4().hex[:6]}", name="Cat", risk_class="MEDIUM",
        default_calibration_interval_days=cal_days)
    model = EquipmentModel.objects.create(
        facility=fac, category=cat, model_name=f"M{uuid.uuid4().hex[:6]}", model_number="1")
    tag = f"T{uuid.uuid4().hex[:10]}"
    return Equipment.objects.create(
        facility=fac, asset_tag=tag, qr_code_value=tag, equipment_model=model, name="Test device",
        lifecycle_stage=stage, operational_state="IN_SERVICE" if stage == "COMMISSIONED" else None)


def make_vendor(fac):
    return Vendor.objects.create(facility=fac, name=f"V{uuid.uuid4().hex[:6]}")


def days(n):
    return (date.today() + timedelta(days=n)).isoformat()


def schedule(c, eq, **kw):
    r = c.post(f"{API}/calibration-schedules/", {"equipment": str(eq.public_id), "frequency_type": "DAYS",
                                                  "frequency_value": 365, **kw}, format="json")
    assert r.status_code == 201, r.content
    return r.json()


def record(c, eq, result="PASS", performed=None, **kw):
    body = {"equipment": str(eq.public_id), "performed_date": performed or days(-1), "performed_by_type": "IN_HOUSE",
            "performer_name": "Engineer", "result": result, **kw}
    return c.post(f"{API}/calibration-records/", body, format="json")


def audit_count(action):
    with connection.cursor() as cur:
        cur.execute("select count(*) from audit_log where action = %s", [action])
        return cur.fetchone()[0]