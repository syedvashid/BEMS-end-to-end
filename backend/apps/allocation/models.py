import uuid

from django.db import models
from django.db.models import F, Func
from django.utils import timezone

from apps.core.models import FacilityScopedModel
from apps.equipment.models import Equipment
from apps.foundation.models import Facility, User
from apps.masters.models import Department, Location


def _fk(model, **kw):
    return models.ForeignKey(model, on_delete=models.DO_NOTHING, db_constraint=False, related_name="+", **kw)


class UserDepartment(models.Model):
    """Child collection (replaced as a set): no is_active / row_version."""
    public_id = models.UUIDField(default=uuid.uuid4, editable=False)
    facility = models.ForeignKey(Facility, on_delete=models.DO_NOTHING, db_constraint=False, related_name="+")
    user = _fk(User)
    department = _fk(Department)
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.BigIntegerField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "user_departments"


class EquipmentAllocation(FacilityScopedModel):
    equipment = _fk(Equipment)
    department = _fk(Department, null=True, blank=True)
    location = _fk(Location, null=True, blank=True)
    source_module = models.TextField(default="MANUAL")
    patient_reference = models.TextField(null=True, blank=True)
    encounter_reference = models.TextField(null=True, blank=True)
    practitioner_name = models.TextField(null=True, blank=True)
    purpose = models.TextField(null=True, blank=True)
    assigned_at = models.DateTimeField(default=timezone.now)
    expected_release_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    released_by = models.BigIntegerField(null=True, blank=True)
    condition_on_release = models.TextField(null=True, blank=True)
    release_notes = models.TextField(null=True, blank=True)
    previous_location = _fk(Location, null=True, blank=True)
    gate_override = models.BooleanField(default=False)
    override_reason = models.TextField(null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "equipment_allocations"


class EquipmentReservation(FacilityScopedModel):
    equipment = _fk(Equipment)
    department = _fk(Department)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    purpose = models.TextField()
    procedure_reference = models.TextField(null=True, blank=True)
    status = models.TextField(default="CONFIRMED")
    cancel_reason = models.TextField(null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "equipment_reservations"


class EquipmentUsageLog(FacilityScopedModel):
    equipment = _fk(Equipment)
    allocation = _fk(EquipmentAllocation, null=True, blank=True)
    department = _fk(Department, null=True, blank=True)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField()
    # generated stored column in the database: never written by Django
    duration_minutes = models.GeneratedField(
        expression=Func(
            F("ended_at") - F("started_at"),
            template="round((extract(epoch from %(expressions)s) / 60.0)::numeric, 2)",
            output_field=models.DecimalField(max_digits=12, decimal_places=2)),
        output_field=models.DecimalField(max_digits=12, decimal_places=2), db_persist=True)
    operator_name = models.TextField(null=True, blank=True)
    patient_reference = models.TextField(null=True, blank=True)
    encounter_reference = models.TextField(null=True, blank=True)
    procedure_text = models.TextField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "equipment_usage_logs"


class EquipmentTransferRequest(FacilityScopedModel):
    equipment = _fk(Equipment)
    from_department = _fk(Department, null=True, blank=True)
    from_location = _fk(Location, null=True, blank=True)
    to_location = _fk(Location)
    to_department = _fk(Department, null=True, blank=True)
    reason = models.TextField()
    status = models.TextField(default="PENDING")
    decided_by = models.BigIntegerField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "equipment_transfer_requests"