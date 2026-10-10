import uuid

from django.db import models
from django.utils import timezone

from apps.core.models import FacilityScopedModel
from apps.equipment.models import Equipment
from apps.foundation.models import Facility, User
from apps.masters.models import Department, EquipmentCategory, EquipmentModel, Vendor


def _fk(model, **kw):
    # Composite (facility_id, x_id) FKs are enforced in the database; Django keeps a plain reference.
    return models.ForeignKey(model, on_delete=models.DO_NOTHING, db_constraint=False, related_name="+", **kw)


class _Child(models.Model):
    """Immutable / child-collection tables: no is_active, no row_version."""
    id = models.BigAutoField(primary_key=True)
    public_id = models.UUIDField(default=uuid.uuid4, editable=False)
    facility = models.ForeignKey(Facility, on_delete=models.DO_NOTHING, db_constraint=False, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.BigIntegerField(null=True, blank=True)

    class Meta:
        abstract = True
        managed = False


class ChecklistTemplate(FacilityScopedModel):
    name = models.TextField()
    description = models.TextField(null=True, blank=True)
    category = _fk(EquipmentCategory, null=True, blank=True)
    equipment_model = _fk(EquipmentModel, null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "checklist_templates"


class ChecklistTemplateItem(_Child):
    checklist_template = _fk(ChecklistTemplate)
    sequence = models.IntegerField()
    item_text = models.TextField()
    item_type = models.TextField()
    unit = models.TextField(null=True, blank=True)
    min_value = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    max_value = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)

    class Meta(_Child.Meta):
        db_table = "checklist_template_items"


class MaintenancePlan(FacilityScopedModel):
    name = models.TextField()
    equipment = _fk(Equipment)
    checklist_template = _fk(ChecklistTemplate, null=True, blank=True)
    frequency_type = models.TextField()
    frequency_value = models.IntegerField()
    lead_days = models.IntegerField(default=7)
    priority = models.TextField(default="MEDIUM")
    default_assignee_user = _fk(User, null=True, blank=True)
    start_date = models.DateField()
    last_performed_date = models.DateField(null=True, blank=True)
    next_due_date = models.DateField()
    notes = models.TextField(null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "maintenance_plans"


class WorkOrder(FacilityScopedModel):
    wo_number = models.TextField()
    work_order_type = models.TextField()
    priority = models.TextField(default="MEDIUM")
    status = models.TextField(default="OPEN")
    equipment = _fk(Equipment)
    maintenance_plan = _fk(MaintenancePlan, null=True, blank=True)
    parent_work_order = _fk("WorkOrder", null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    problem_description = models.TextField(null=True, blank=True)
    reported_at = models.DateTimeField(default=timezone.now)
    reported_by_name = models.TextField(null=True, blank=True)
    reported_by_department = _fk(Department, null=True, blank=True)
    equipment_unusable = models.BooleanField(default=False)
    assigned_to_user = _fk(User, null=True, blank=True)
    assigned_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.BigIntegerField(null=True, blank=True)
    signoff_name = models.TextField(null=True, blank=True)
    root_cause = models.TextField(null=True, blank=True)
    action_taken = models.TextField(null=True, blank=True)
    labour_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    vendor_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    coverage_source = models.TextField(null=True, blank=True)
    source_calibration_record = _fk("compliance.CalibrationRecord", null=True, blank=True)
    warranty = _fk("compliance.Warranty", null=True, blank=True)
    amc_contract = _fk("compliance.AmcContract", null=True, blank=True)
    service_provider_vendor = _fk(Vendor, null=True, blank=True)
    vendor_call_reference = models.TextField(null=True, blank=True)
    vendor_engineer_name = models.TextField(null=True, blank=True)
    vendor_visit_at = models.DateTimeField(null=True, blank=True)
    standby_equipment = _fk(Equipment, null=True, blank=True)
    downtime_start = models.DateTimeField(null=True, blank=True)
    downtime_end = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.TextField(null=True, blank=True)
    status_note = models.TextField(null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "work_orders"


class WorkOrderEvent(_Child):
    work_order = _fk(WorkOrder)
    event_type = models.TextField()
    from_status = models.TextField(null=True, blank=True)
    to_status = models.TextField(null=True, blank=True)
    note = models.TextField(null=True, blank=True)

    class Meta(_Child.Meta):
        db_table = "work_order_events"


class WorkOrderChecklistItem(FacilityScopedModel):
    work_order = _fk(WorkOrder)
    sequence = models.IntegerField()
    item_text = models.TextField()
    item_type = models.TextField()
    unit = models.TextField(null=True, blank=True)
    min_value = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    max_value = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    result = models.TextField(null=True, blank=True)
    measured_value = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    remarks = models.TextField(null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "work_order_checklist_items"


class EquipmentHold(FacilityScopedModel):
    equipment = _fk(Equipment)
    hold_type = models.TextField()
    source_type = models.TextField()
    work_order = _fk(WorkOrder, null=True, blank=True)
    calibration_record = _fk("compliance.CalibrationRecord", null=True, blank=True)
    reason = models.TextField()
    started_at = models.DateTimeField(default=timezone.now)
    released_at = models.DateTimeField(null=True, blank=True)
    released_by = models.BigIntegerField(null=True, blank=True)
    release_reason = models.TextField(null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "equipment_holds"


class SparePart(FacilityScopedModel):
    part_code = models.TextField()
    name = models.TextField()
    description = models.TextField(null=True, blank=True)
    unit = models.TextField(default="pcs")
    reorder_level = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    standard_unit_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "spare_parts"


class SparePartCategory(_Child):
    spare_part = _fk(SparePart)
    category = _fk(EquipmentCategory)

    class Meta(_Child.Meta):
        db_table = "spare_part_categories"


class SparePartStockEntry(_Child):
    """Immutable ledger: bems_app has select + insert only. On-hand = sum(quantity)."""
    spare_part = _fk(SparePart)
    entry_type = models.TextField()
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    work_order = _fk(WorkOrder, null=True, blank=True)
    related_entry = _fk("SparePartStockEntry", null=True, blank=True)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    supplier_vendor = _fk(Vendor, null=True, blank=True)
    reference_note = models.TextField(null=True, blank=True)
    reason = models.TextField(null=True, blank=True)

    class Meta(_Child.Meta):
        db_table = "spare_part_stock_entries"
