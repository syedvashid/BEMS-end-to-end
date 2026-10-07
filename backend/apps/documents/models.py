import uuid

from django.db import models
from django.utils import timezone

from apps.core.models import FacilityScopedModel


class Document(FacilityScopedModel):
    document_type = models.CharField(max_length=40)
    title = models.CharField(max_length=200)
    description = models.CharField(max_length=1000, null=True, blank=True)
    entity_type = models.CharField(max_length=50)
    entity_public_id = models.UUIDField()
    expiry_date = models.DateField(null=True, blank=True)
    current_version_no = models.IntegerField(default=1)

    class Meta(FacilityScopedModel.Meta):
        db_table = "documents"


class DocumentVersion(models.Model):
    """Immutable: the DB role bems_app has SELECT and INSERT only."""
    id = models.BigAutoField(primary_key=True)
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    facility = models.ForeignKey(
        "foundation.Facility", on_delete=models.DO_NOTHING, db_constraint=False, related_name="+"
    )
    document = models.ForeignKey(
        Document, on_delete=models.DO_NOTHING, db_constraint=False, related_name="versions"
    )
    version_no = models.IntegerField()
    original_filename = models.CharField(max_length=255)
    storage_key = models.CharField(max_length=120, unique=True)
    content_type = models.CharField(max_length=120)
    size_bytes = models.BigIntegerField()
    sha256 = models.CharField(max_length=64)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    created_by = models.BigIntegerField(null=True, blank=True, editable=False)

    class Meta:
        managed = False
        db_table = "document_versions"
        ordering = ["-version_no"]