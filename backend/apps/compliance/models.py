import uuid

from django.db import models
from django.utils import timezone

from apps.core.models import FacilityScopedModel
from apps.equipment.models import Equipment
from apps.foundation.models import Facility
from apps.masters.models import Vendor


def _fk(model, **kw):
    return models.ForeignKey(model, on_delete=models.DO_NOTHING, db_constraint=False, related_name="+", **kw)


class _Child(models.Model):
    id = models.BigAutoField(primary_key=True)
    public_id = models.UUIDField(default=uuid.uuid4, editable=False)
    facility = models.ForeignKey(Facility, on_delete=models.DO_NOTHING, db_constraint=False, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.BigIntegerField(null=True, blank=True)

    class Meta:
        abstract = True
        managed = False


class _Immutable(_Child):
    """Insert-only rows (bems_app has select + insert only). Guard against accidental ORM updates/deletes."""

    class Meta(_Child.Meta):
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError(f"{type(self).__name__} is immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError(f"{type(self).__name__} is immutable.")


class CalibrationSchedule(FacilityScopedModel):
    equipment = _fk(Equipment)
    frequency_type = models.TextField()
    frequency_value = models.IntegerField()
    lead_days = models.IntegerField(default=30)
    last_calibrated_date = models.DateField(null=True, blank=True)
    next_due_date = models.DateField()
    on_fail_hold_equipment = models.BooleanField(default=True)
    on_fail_open_work_order = models.BooleanField(default=True)
    notes = models.TextField(null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "calibration_schedules"


class CalibrationRecord(_Immutable):
    equipment = _fk(Equipment)
    calibration_schedule = _fk(CalibrationSchedule)
    performed_date = models.DateField()
    calibration_reason = models.TextField()
    performed_by_type = models.TextField()
    performer_vendor = _fk(Vendor, null=True, blank=True)
    performer_name = models.TextField(null=True, blank=True)
    reference_standard_details = models.TextField(null=True, blank=True)
    certificate_number = models.TextField(null=True, blank=True)
    result = models.TextField()
    readings = models.JSONField(default=list)
    deviation_summary = models.TextField(null=True, blank=True)
    next_due_date = models.DateField()
    notes = models.TextField(null=True, blank=True)

    class Meta(_Immutable.Meta):
        db_table = "calibration_records"


class CalibrationImpactReview(_Immutable):
    calibration_record = _fk(CalibrationRecord)
    review_notes = models.TextField()
    patient_impact_found = models.BooleanField()

    class Meta(_Immutable.Meta):
        db_table = "calibration_impact_reviews"


class Warranty(FacilityScopedModel):
    equipment = _fk(Equipment)
    vendor = _fk(Vendor, null=True, blank=True)
    warranty_type = models.TextField()
    start_date = models.DateField()
    end_date = models.DateField()
    reference_number = models.TextField(null=True, blank=True)
    coverage_terms = models.TextField(null=True, blank=True)
    covered_parts = models.TextField(null=True, blank=True)
    exclusions = models.TextField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "warranties"


class WarrantyClaim(FacilityScopedModel):
    warranty = _fk(Warranty)
    equipment = _fk(Equipment)
    work_order = _fk("maintenance.WorkOrder", null=True, blank=True)
    claim_number = models.TextField(null=True, blank=True)
    claim_date = models.DateField()
    description = models.TextField()
    status = models.TextField(default="RAISED")
    claim_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    resolved_date = models.DateField(null=True, blank=True)
    resolution_notes = models.TextField(null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "warranty_claims"


class AmcContract(FacilityScopedModel):
    contract_number = models.TextField()
    vendor = _fk(Vendor)
    contract_type = models.TextField()
    start_date = models.DateField()
    end_date = models.DateField()
    contract_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    covered_scope = models.TextField(null=True, blank=True)
    exclusions = models.TextField(null=True, blank=True)
    visit_frequency_per_year = models.SmallIntegerField(default=0)
    response_sla_hours = models.IntegerField(null=True, blank=True)
    uptime_guarantee_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    penalty_terms = models.TextField(null=True, blank=True)
    renewed_from_contract = _fk("AmcContract", null=True, blank=True)
    notes = models.TextField(null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "amc_contracts"


class AmcCoverage(_Child):
    amc_contract = _fk(AmcContract)
    equipment = _fk(Equipment)
    allocated_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    class Meta(_Child.Meta):
        db_table = "amc_coverages"


class EquipmentLicence(FacilityScopedModel):
    equipment = _fk(Equipment)
    licence_type = models.TextField()
    licence_number = models.TextField(null=True, blank=True)
    issuing_authority = models.TextField(null=True, blank=True)
    issue_date = models.DateField()
    expiry_date = models.DateField()
    renewed_from_licence = _fk("EquipmentLicence", null=True, blank=True)
    notes = models.TextField(null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "equipment_licences"