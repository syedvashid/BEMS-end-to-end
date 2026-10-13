import uuid
from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.core.models import FacilityScopedModel
from apps.equipment.models import Equipment
from apps.foundation.models import Facility
from apps.masters.models import EquipmentCategory, Vendor


def _fk(model, **kw):
    # Composite (facility_id, x_id) FKs are enforced in the database; Django keeps a plain reference.
    return models.ForeignKey(model, on_delete=models.DO_NOTHING, db_constraint=False, related_name="+", **kw)


class _Immutable(models.Model):
    """Insert-only rows (bems_app has select + insert only)."""
    id = models.BigAutoField(primary_key=True)
    public_id = models.UUIDField(default=uuid.uuid4, editable=False)
    facility = models.ForeignKey(Facility, on_delete=models.DO_NOTHING, db_constraint=False, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.BigIntegerField(null=True, blank=True)

    class Meta:
        abstract = True
        managed = False

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError(f"{type(self).__name__} is immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError(f"{type(self).__name__} is immutable.")


class FinanceSettings(FacilityScopedModel):
    maintenance_cost_threshold_percent = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("60.00"))
    committee_required_above_book_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "finance_settings"


class DepreciationPolicy(FacilityScopedModel):
    category = _fk(EquipmentCategory, null=True, blank=True)
    equipment = _fk(Equipment, null=True, blank=True)
    method = models.TextField()
    useful_life_years = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    rate_percent = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    salvage_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("5"))
    start_rule = models.TextField(default="COMMISSIONING_DATE")
    notes = models.TextField(null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "depreciation_policies"


class DepreciationRun(FacilityScopedModel):
    run_period = models.DateField()
    status = models.TextField(default="RUNNING")
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    assets_processed = models.IntegerField(default=0)
    entries_created = models.IntegerField(default=0)
    skipped_no_policy = models.IntegerField(default=0)
    skipped_no_cost = models.IntegerField(default=0)
    skipped_no_start_date = models.IntegerField(default=0)
    total_charge = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    triggered_by_system = models.BooleanField(default=False)
    error_message = models.TextField(null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "depreciation_runs"


class DepreciationEntry(_Immutable):
    equipment = _fk(Equipment)
    period_month = models.DateField()
    entry_type = models.TextField()
    opening_value = models.DecimalField(max_digits=14, decimal_places=2)
    charge = models.DecimalField(max_digits=14, decimal_places=2)
    closing_value = models.DecimalField(max_digits=14, decimal_places=2)
    method = models.TextField(null=True, blank=True)
    policy = _fk(DepreciationPolicy, null=True, blank=True)
    run = _fk(DepreciationRun, null=True, blank=True)
    days_charged = models.IntegerField(null=True, blank=True)

    class Meta(_Immutable.Meta):
        db_table = "depreciation_entries"


class TcoSnapshot(_Immutable):
    equipment = _fk(Equipment)
    as_of_date = models.DateField()
    acquisition_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    installation_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    labour_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    vendor_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    parts_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    amc_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    salvage_value = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    total_cost_of_ownership = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    maintenance_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    maintenance_cost_ratio_percent = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    age_years = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    expected_life_years = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    usage_hours = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    session_count = models.IntegerField(default=0)
    cost_per_hour = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    cost_per_use = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    threshold_percent = models.DecimalField(max_digits=6, decimal_places=2)
    replacement_indicator = models.TextField(default="NONE")

    class Meta(_Immutable.Meta):
        db_table = "tco_snapshots"


class CondemnationRequest(FacilityScopedModel):
    request_number = models.TextField()
    equipment = _fk(Equipment)
    reason_category = models.TextField()
    justification = models.TextField()
    technical_assessment = models.TextField(null=True, blank=True)
    technical_assessment_by_name = models.TextField(null=True, blank=True)
    book_value_at_request = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    source_verification_item = _fk("safety.PhysicalVerificationItem", null=True, blank=True)
    status = models.TextField(default="REQUESTED")
    committee_reference = models.TextField(null=True, blank=True)
    committee_decision_date = models.DateField(null=True, blank=True)
    decided_by = models.BigIntegerField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(null=True, blank=True)
    revoked = models.BooleanField(default=False)
    cancel_reason = models.TextField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "condemnation_requests"


class Disposal(FacilityScopedModel):
    disposal_number = models.TextField()
    equipment = _fk(Equipment)
    condemnation_request = _fk(CondemnationRequest)
    disposal_method = models.TextField()
    disposal_date = models.DateField(null=True, blank=True)
    recipient_name = models.TextField(null=True, blank=True)
    recipient_vendor = _fk(Vendor, null=True, blank=True)
    proceeds_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    decontamination_done = models.BooleanField(default=False)
    decontamination_notes = models.TextField(null=True, blank=True)
    data_wipe_required = models.BooleanField(default=False)
    data_wipe_done = models.BooleanField(default=False)
    recycler_name = models.TextField(null=True, blank=True)
    ewaste_certificate_number = models.TextField(null=True, blank=True)
    book_value_at_disposal = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    gain_loss = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    status = models.TextField(default="IN_PROGRESS")
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.BigIntegerField(null=True, blank=True)
    cancel_reason = models.TextField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "disposals"


class ReplacementPlan(FacilityScopedModel):
    equipment = _fk(Equipment)
    planned_year = models.SmallIntegerField()
    estimated_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    priority = models.TextField(default="MEDIUM")
    status = models.TextField(default="CANDIDATE")
    justification = models.TextField(null=True, blank=True)
    replaced_by_equipment = _fk(Equipment, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "replacement_plans"
