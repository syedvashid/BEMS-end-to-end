"""Phase 11 models. Tables come from db/sql/062-065 (managed = False)."""
from django.db import models

from apps.allocation.models import EquipmentAllocation, EquipmentUsageLog
from apps.core.models import FacilityScopedModel
from apps.equipment.models import Equipment
from apps.masters.models import Department, EquipmentCategory


def _fk(model, **kw):
    return models.ForeignKey(model, on_delete=models.DO_NOTHING, db_constraint=False, related_name="+", **kw)


class ChargeItem(FacilityScopedModel):
    item_code = models.TextField()
    name = models.TextField()
    unit_label = models.TextField()
    default_rate = models.DecimalField(max_digits=14, decimal_places=2)
    description = models.TextField(null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "charge_items"


class ChargeSettings(FacilityScopedModel):
    auto_approve = models.BooleanField(default=False)

    class Meta(FacilityScopedModel.Meta):
        db_table = "charge_settings"


class ChargeMapping(FacilityScopedModel):
    equipment = _fk(Equipment, null=True, blank=True)
    category = _fk(EquipmentCategory, null=True, blank=True)
    charge_item = _fk(ChargeItem)
    billing_rule = models.TextField()
    basis = models.TextField(default="ALLOCATION")
    rate_override = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    minimum_billable_minutes = models.IntegerField(default=0)
    grace_minutes = models.IntegerField(default=0)
    rounding = models.TextField(default="UP")
    daily_cap_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    day_block_mode = models.TextField(default="CALENDAR_DAY")
    bundle_reference = models.TextField(null=True, blank=True)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "charge_mappings"


class ChargeRecord(FacilityScopedModel):
    """Immutable except for the status, approval, cancel, reversal and export columns (database trigger)."""
    record_number = models.TextField()
    idempotency_key = models.TextField()
    record_type = models.TextField(default="CHARGE")
    source_type = models.TextField()
    allocation = _fk(EquipmentAllocation, null=True, blank=True)
    usage_log = _fk(EquipmentUsageLog, null=True, blank=True)
    equipment = _fk(Equipment)
    charge_mapping = _fk(ChargeMapping)
    charge_item = _fk(ChargeItem)
    billing_rule = models.TextField()
    basis = models.TextField()
    unit_label = models.TextField()
    unit_rate = models.DecimalField(max_digits=14, decimal_places=2)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    period_key = models.TextField()
    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)
    charge_date = models.DateField()
    patient_reference = models.TextField()
    encounter_reference = models.TextField(null=True, blank=True)
    department = _fk(Department, null=True, blank=True)
    calculation = models.JSONField(default=dict)
    status = models.TextField(default="PENDING_REVIEW")
    approved_by = models.BigIntegerField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.BigIntegerField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.TextField(null=True, blank=True)
    reverses_record = models.ForeignKey("self", on_delete=models.DO_NOTHING, db_constraint=False, related_name="+",
                                        null=True, blank=True)
    reversal_reason = models.TextField(null=True, blank=True)
    corrects_record = models.ForeignKey("self", on_delete=models.DO_NOTHING, db_constraint=False, related_name="+",
                                        null=True, blank=True)
    exported_at = models.DateTimeField(null=True, blank=True)
    exported_by = models.BigIntegerField(null=True, blank=True)
    export_reference = models.TextField(null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "charge_records"
