import uuid

from django.db import models
from django.utils import timezone

from apps.core.models import FacilityScopedModel
from apps.equipment.models import Equipment
from apps.foundation.models import Facility
from apps.maintenance.models import WorkOrder
from apps.masters.models import Department, EquipmentModel, Location, Vendor


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


# ------------------------------------------------------------------ incidents
class EquipmentIncident(FacilityScopedModel):
    incident_number = models.TextField()
    equipment = _fk(Equipment)
    incident_type = models.TextField()
    severity = models.TextField()
    occurred_at = models.DateTimeField()
    reported_by_name = models.TextField(null=True, blank=True)
    department = _fk(Department, null=True, blank=True)
    location = _fk(Location, null=True, blank=True)
    description = models.TextField()
    immediate_action = models.TextField(null=True, blank=True)
    patient_reference = models.TextField(null=True, blank=True)
    encounter_reference = models.TextField(null=True, blank=True)
    patient_affected = models.BooleanField(default=False)
    staff_affected = models.BooleanField(default=False)
    status = models.TextField(default="REPORTED")
    investigated_by = models.BigIntegerField(null=True, blank=True)
    root_cause = models.TextField(null=True, blank=True)
    corrective_action = models.TextField(null=True, blank=True)
    preventive_action = models.TextField(null=True, blank=True)
    investigation_notes = models.TextField(null=True, blank=True)
    reportable_to_regulator = models.BooleanField(default=False)
    regulator_report_reference = models.TextField(null=True, blank=True)
    regulator_reported_on = models.DateField(null=True, blank=True)
    work_order = _fk(WorkOrder, null=True, blank=True)
    closure_notes = models.TextField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.BigIntegerField(null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "equipment_incidents"


class IncidentEvent(_Child):
    incident = _fk(EquipmentIncident)
    event_type = models.TextField()
    from_status = models.TextField(null=True, blank=True)
    to_status = models.TextField(null=True, blank=True)
    note = models.TextField(null=True, blank=True)

    class Meta(_Child.Meta):
        db_table = "incident_events"


# ------------------------------------------------------------------ recalls
class RecallNotice(FacilityScopedModel):
    notice_number = models.TextField()
    reference_number = models.TextField(null=True, blank=True)
    title = models.TextField()
    notice_type = models.TextField()
    source = models.TextField()
    issued_by_vendor = _fk(Vendor, null=True, blank=True)
    issued_date = models.DateField(null=True, blank=True)
    received_date = models.DateField(null=True, blank=True)
    urgency = models.TextField()
    action_type = models.TextField()
    stop_use = models.BooleanField(default=False)
    description = models.TextField()
    required_action = models.TextField(null=True, blank=True)
    affected_serials_note = models.TextField(null=True, blank=True)
    status = models.TextField(default="OPEN")
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.BigIntegerField(null=True, blank=True)
    close_notes = models.TextField(null=True, blank=True)
    cancel_reason = models.TextField(null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "recall_notices"


class RecallNoticeModel(_Child):
    recall_notice = _fk(RecallNotice)
    equipment_model = _fk(EquipmentModel)

    class Meta(_Child.Meta):
        db_table = "recall_notice_models"


class RecallAffectedUnit(FacilityScopedModel):
    recall_notice = _fk(RecallNotice)
    equipment = _fk(Equipment)
    status = models.TextField(default="PENDING")
    identified_by = models.TextField()
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.BigIntegerField(null=True, blank=True)
    resolution_notes = models.TextField(null=True, blank=True)
    vendor_reference = models.TextField(null=True, blank=True)
    work_order = _fk(WorkOrder, null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "recall_affected_units"


# ------------------------------------------------------------------ physical verification
class PhysicalVerification(FacilityScopedModel):
    verification_number = models.TextField()
    title = models.TextField()
    scope_type = models.TextField()
    department = _fk(Department, null=True, blank=True)
    location = _fk(Location, null=True, blank=True)
    planned_date = models.DateField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.TextField(default="PLANNED")
    conducted_by_name = models.TextField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    expected_count = models.IntegerField(null=True, blank=True)
    found_count = models.IntegerField(null=True, blank=True)
    elsewhere_count = models.IntegerField(null=True, blank=True)
    missing_count = models.IntegerField(null=True, blank=True)
    unexpected_count = models.IntegerField(null=True, blank=True)
    cancel_reason = models.TextField(null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "physical_verifications"


class PhysicalVerificationItem(FacilityScopedModel):
    verification = _fk(PhysicalVerification)
    equipment = _fk(Equipment)
    expected_location = _fk(Location, null=True, blank=True)
    expected_department = _fk(Department, null=True, blank=True)
    result = models.TextField(default="PENDING")
    found_location = _fk(Location, null=True, blank=True)
    scanned_at = models.DateTimeField(null=True, blank=True)
    scanned_by = models.BigIntegerField(null=True, blank=True)
    tag_status = models.TextField(default="OK")
    notes = models.TextField(null=True, blank=True)
    resolution = models.TextField(default="NONE")
    resolution_notes = models.TextField(null=True, blank=True)
    resolved_by = models.BigIntegerField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "physical_verification_items"
