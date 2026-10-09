import uuid

from django.db import models
from django.utils import timezone

from apps.core.models import FacilityScopedModel
from apps.foundation.models import Facility
from apps.masters.models import Department, EquipmentModel, FundingSource, Location, Vendor


def _fk(model, **kw):
    # Composite (facility_id, x_id) FKs are enforced in the database; Django keeps a plain reference.
    return models.ForeignKey(model, on_delete=models.DO_NOTHING, db_constraint=False, related_name="+", **kw)


class Equipment(FacilityScopedModel):
    asset_tag = models.CharField(max_length=20)
    qr_code_value = models.CharField(max_length=20)
    legacy_asset_id = models.CharField(max_length=100, null=True, blank=True)
    equipment_model = _fk(EquipmentModel)
    name = models.CharField(max_length=200)
    serial_number = models.CharField(max_length=100, null=True, blank=True)

    lifecycle_stage = models.CharField(max_length=20, default="RECEIVED")
    operational_state = models.CharField(max_length=20, null=True, blank=True)
    owning_department = _fk(Department, null=True, blank=True)
    current_location = _fk(Location, null=True, blank=True)
    criticality = models.CharField(max_length=10, default="MEDIUM")

    ownership_type = models.CharField(max_length=20, default="OWNED")
    owner_vendor = _fk(Vendor, null=True, blank=True)
    ownership_end_date = models.DateField(null=True, blank=True)
    funding_source = _fk(FundingSource, null=True, blank=True)

    supplier_vendor = _fk(Vendor, null=True, blank=True)
    purchase_order_number = models.CharField(max_length=100, null=True, blank=True)
    purchase_order_date = models.DateField(null=True, blank=True)
    grn_number = models.CharField(max_length=100, null=True, blank=True)
    grn_date = models.DateField(null=True, blank=True)
    invoice_number = models.CharField(max_length=100, null=True, blank=True)
    invoice_date = models.DateField(null=True, blank=True)
    purchase_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    installation_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    expected_life_years = models.IntegerField(null=True, blank=True)
    custom_attributes = models.JSONField(default=dict)
    notes = models.CharField(max_length=2000, null=True, blank=True)
    is_legacy_entry = models.BooleanField(default=False)

    class Meta(FacilityScopedModel.Meta):
        db_table = "equipment"


class EquipmentCommissioning(FacilityScopedModel):
    equipment = _fk(Equipment)
    installation_date = models.DateField(null=True, blank=True)
    installation_engineer_name = models.CharField(max_length=200, null=True, blank=True)
    installation_vendor = _fk(Vendor, null=True, blank=True)
    installation_notes = models.CharField(max_length=2000, null=True, blank=True)
    acceptance_test_result = models.CharField(max_length=20, null=True, blank=True)
    acceptance_test_notes = models.CharField(max_length=2000, null=True, blank=True)
    acceptance_date = models.DateField(null=True, blank=True)
    accepted_by = models.BigIntegerField(null=True, blank=True)
    handed_over_department = _fk(Department, null=True, blank=True)
    handover_received_by_name = models.CharField(max_length=200, null=True, blank=True)
    training_conducted = models.BooleanField(default=False)
    training_notes = models.CharField(max_length=2000, null=True, blank=True)
    commissioning_date = models.DateField(null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "equipment_commissioning"


class EquipmentStateHistory(models.Model):
    """Immutable: bems_app has select + insert only."""
    public_id = models.UUIDField(default=uuid.uuid4, editable=False)
    facility = models.ForeignKey(Facility, on_delete=models.DO_NOTHING, db_constraint=False, related_name="+")
    equipment = _fk(Equipment)
    change_type = models.CharField(max_length=20)
    from_value = models.CharField(max_length=30, null=True, blank=True)
    to_value = models.CharField(max_length=30)
    reason = models.CharField(max_length=1000)
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.BigIntegerField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "equipment_state_history"


class EquipmentMovement(models.Model):
    """Immutable: bems_app has select + insert only."""
    public_id = models.UUIDField(default=uuid.uuid4, editable=False)
    facility = models.ForeignKey(Facility, on_delete=models.DO_NOTHING, db_constraint=False, related_name="+")
    equipment = _fk(Equipment)
    from_location = _fk(Location, null=True, blank=True)
    to_location = models.ForeignKey(
        Location, on_delete=models.DO_NOTHING, db_constraint=False, related_name="+", related_query_name="+")
    from_department = models.ForeignKey(
        Department, on_delete=models.DO_NOTHING, db_constraint=False, null=True, blank=True, related_name="+")
    to_department = models.ForeignKey(
        Department, on_delete=models.DO_NOTHING, db_constraint=False, null=True, blank=True, related_name="+")
    reason = models.CharField(max_length=1000)
    moved_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.BigIntegerField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "equipment_movements"
