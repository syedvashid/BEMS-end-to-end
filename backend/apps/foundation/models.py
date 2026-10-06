from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel, FacilityScopedModel


class Facility(BaseModel):
    code = models.TextField()
    name = models.TextField()
    facility_type = models.TextField(default="HOSPITAL")
    parent_facility = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.DO_NOTHING, db_constraint=False, related_name="children"
    )
    address_line1 = models.TextField(null=True, blank=True)
    address_line2 = models.TextField(null=True, blank=True)
    city = models.TextField(null=True, blank=True)
    state = models.TextField(null=True, blank=True)
    pin_code = models.TextField(null=True, blank=True)
    phone = models.TextField(null=True, blank=True)
    email = models.TextField(null=True, blank=True)
    registration_number = models.TextField(null=True, blank=True)
    timezone = models.TextField(default="Asia/Kolkata")

    class Meta(BaseModel.Meta):
        db_table = "facilities"


class User(BaseModel):
    """Global identity. username/email are citext in the DB (case-insensitive equality)."""
    username = models.TextField()
    full_name = models.TextField()
    email = models.TextField(null=True, blank=True)
    phone = models.TextField(null=True, blank=True)
    employee_code = models.TextField(null=True, blank=True)
    designation = models.TextField(null=True, blank=True)
    # reserved for the future auth phase, unused now
    password_hash = models.TextField(null=True, blank=True)
    failed_login_count = models.IntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    must_change_password = models.BooleanField(default=False)

    is_authenticated = True   # DRF/permission checks treat a resolved User as authenticated
    is_anonymous = False

    class Meta(BaseModel.Meta):
        db_table = "users"


class Permission(BaseModel):
    code = models.TextField()
    module = models.TextField()
    description = models.TextField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "permissions"


class Role(BaseModel):
    code = models.TextField()
    name = models.TextField()
    description = models.TextField(null=True, blank=True)
    is_system = models.BooleanField(default=False)

    class Meta(BaseModel.Meta):
        db_table = "roles"


class RolePermission(models.Model):
    """Join table, replaced as a set. Documented exception: no is_active/row_version."""
    id = models.BigAutoField(primary_key=True)
    role = models.ForeignKey(Role, on_delete=models.DO_NOTHING, db_constraint=False, related_name="role_permissions")
    permission = models.ForeignKey(Permission, on_delete=models.DO_NOTHING, db_constraint=False, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.BigIntegerField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "role_permissions"


class UserFacilityRole(FacilityScopedModel):
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING, db_constraint=False, related_name="facility_roles")
    role = models.ForeignKey(Role, on_delete=models.DO_NOTHING, db_constraint=False, related_name="user_assignments")

    class Meta(FacilityScopedModel.Meta):
        db_table = "user_facility_roles"


class AuditLog(models.Model):
    """Read-only mirror of audit_log. Writes go through apps.core.audit.record()."""
    id = models.BigAutoField(primary_key=True)
    chain_seq = models.BigIntegerField()
    occurred_at = models.DateTimeField()
    facility = models.ForeignKey(
        Facility, null=True, on_delete=models.DO_NOTHING, db_constraint=False, related_name="+"
    )
    actor_user_id = models.BigIntegerField(null=True)
    actor_username = models.TextField(null=True)
    action = models.TextField()
    entity_type = models.TextField(null=True)
    entity_public_id = models.UUIDField(null=True)
    previous_value = models.JSONField(null=True)
    new_value = models.JSONField(null=True)
    changed_fields = ArrayField(models.TextField(), null=True)
    request_id = models.TextField(null=True)
    ip_address = models.GenericIPAddressField(null=True)
    user_agent = models.TextField(null=True)
    http_method = models.TextField(null=True)
    request_path = models.TextField(null=True)
    prev_hash = models.TextField()
    row_hash = models.TextField()

    class Meta:
        managed = False
        db_table = "audit_log"

    def save(self, *args, **kwargs):
        raise RuntimeError("audit_log is append-only; use apps.core.audit.record().")

    def delete(self, *args, **kwargs):
        raise RuntimeError("audit_log is append-only.")