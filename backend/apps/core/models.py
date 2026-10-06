import uuid

from django.db import models
from django.utils import timezone


class BaseQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class BaseModel(models.Model):
    """Standard columns. Tables are created by raw SQL (managed = False).
    Children must declare `class Meta(BaseModel.Meta): db_table = "..."`.
    created_at/updated_at/row_version are maintained by the DB trigger touch_row()."""
    id = models.BigAutoField(primary_key=True)
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    created_by = models.BigIntegerField(null=True, blank=True, editable=False)
    updated_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_by = models.BigIntegerField(null=True, blank=True, editable=False)
    is_active = models.BooleanField(default=True)
    row_version = models.IntegerField(default=1)

    objects = BaseQuerySet.as_manager()

    class Meta:
        abstract = True
        managed = False


class FacilityScopedModel(BaseModel):
    """Base for every facility-scoped business table (Phase 2+)."""
    facility = models.ForeignKey(
        "foundation.Facility", on_delete=models.DO_NOTHING, db_constraint=False, related_name="+"
    )

    class Meta(BaseModel.Meta):
        abstract = True