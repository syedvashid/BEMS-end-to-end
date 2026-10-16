"""Phase 10 models. Tables come from db/sql/058 and 059 (managed = False)."""
from django.db import models
from django.utils import timezone

from apps.core.models import FacilityScopedModel
from apps.equipment.models import Equipment
from apps.foundation.models import Facility


class EquipmentDailyStat(models.Model):
    """Derived table rebuilt by apps.reports.stats. No is_active / row_version / trigger."""
    id = models.BigAutoField(primary_key=True)
    facility = models.ForeignKey(Facility, on_delete=models.DO_NOTHING, db_constraint=False, related_name="+")
    equipment = models.ForeignKey(Equipment, on_delete=models.DO_NOTHING, db_constraint=False, related_name="+")
    stat_date = models.DateField()
    in_service_minutes = models.IntegerField(default=0)
    downtime_planned_minutes = models.IntegerField(default=0)
    downtime_unplanned_minutes = models.IntegerField(default=0)
    available_minutes = models.IntegerField(default=0)
    used_minutes = models.IntegerField(default=0)
    allocated_minutes = models.IntegerField(default=0)
    session_count = models.IntegerField(default=0)
    breakdown_count = models.IntegerField(default=0)
    computed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "equipment_daily_stats"


class ReportRun(FacilityScopedModel):
    report_code = models.TextField()
    report_name = models.TextField()
    parameters = models.JSONField(default=dict)
    format = models.TextField()
    status = models.TextField(default="QUEUED")
    row_count = models.IntegerField(null=True, blank=True)
    original_filename = models.TextField(null=True, blank=True)
    storage_key = models.TextField(null=True, blank=True)
    file_size_bytes = models.BigIntegerField(null=True, blank=True)
    sha256 = models.TextField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    requested_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "report_runs"
