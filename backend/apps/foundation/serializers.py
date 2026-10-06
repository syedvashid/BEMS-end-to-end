import re
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework import serializers

from .context import member_facilities
from .models import AuditLog, Facility, Permission, Role, User, UserFacilityRole

FACILITY_CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{1,29}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
ROLE_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
PHONE_RE = r"^[0-9+()\- ]{6,20}$"
PIN_RE = r"^[1-9][0-9]{5}$"


class PublicIdField(serializers.SlugRelatedField):
    """Related object by public_id (uuid). Invalid/unknown -> clean 400, never a 500."""
    default_error_messages = {"does_not_exist": "Unknown reference.", "invalid": "Invalid identifier."}

    def __init__(self, **kwargs):
        kwargs["slug_field"] = "public_id"
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        try:
            uuid.UUID(str(data))
        except ValueError:
            self.fail("invalid")
        return super().to_internal_value(data)

    def to_representation(self, obj):
        return str(obj.public_id)


class BlankToNullMixin:
    """'' becomes None for optional (allow_null) fields."""
    def to_internal_value(self, data):
        if hasattr(data, "items"):
            data = {
                k: (None if isinstance(v, str) and v.strip() == "" and getattr(self.fields.get(k), "allow_null", False) else v)
                for k, v in data.items()
            }
        return super().to_internal_value(data)


def _opt(max_length):
    return serializers.CharField(max_length=max_length, required=False, allow_null=True)


class FacilitySerializer(BlankToNullMixin, serializers.ModelSerializer):
    code = serializers.CharField(max_length=30)
    name = serializers.CharField(max_length=200)
    facility_type = serializers.ChoiceField(choices=["HOSPITAL", "CLINIC", "CAMPUS", "OTHER"], required=False)
    parent_facility = PublicIdField(queryset=Facility.objects.none(), required=False, allow_null=True)
    address_line1 = _opt(200)
    address_line2 = _opt(200)
    city = _opt(100)
    state = _opt(100)
    pin_code = serializers.RegexField(PIN_RE, required=False, allow_null=True)
    phone = serializers.RegexField(PHONE_RE, required=False, allow_null=True)
    email = serializers.EmailField(max_length=254, required=False, allow_null=True)
    registration_number = _opt(100)
    timezone = serializers.CharField(max_length=64, required=False)

    class Meta:
        model = Facility
        fields = [
            "public_id", "code", "name", "facility_type", "parent_facility", "address_line1", "address_line2",
            "city", "state", "pin_code", "phone", "email", "registration_number", "timezone",
            "is_active", "row_version", "created_at", "updated_at",
        ]
        read_only_fields = ["public_id", "is_active", "row_version", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ctx = getattr(self.context.get("request"), "bems", None)
        if ctx is not None:
            self.fields["parent_facility"].queryset = Facility.objects.filter(
                is_active=True, pk__in=member_facilities(ctx.user.id)
            )

    def validate_code(self, value):
        value = value.strip().upper()
        if not FACILITY_CODE_RE.match(value):
            raise serializers.ValidationError("Use 2-30 characters: A-Z, 0-9, '_' or '-'.")
        qs = Facility.objects.filter(is_active=True, code__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This code is already in use.")
        return value

    def validate_timezone(self, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise serializers.ValidationError("Unknown time zone.")
        return value

    def validate(self, attrs):
        parent = attrs.get("parent_facility")
        if parent is not None and self.instance is not None:
            node, depth = parent, 0
            while node is not None and depth < 25:
                if node.pk == self.instance.pk:
                    raise serializers.ValidationError({"parent_facility": ["A facility cannot be its own ancestor."]})
                node, depth = node.parent_facility, depth + 1
        return attrs


class UserSerializer(BlankToNullMixin, serializers.ModelSerializer):
    username = serializers.CharField(max_length=64)
    full_name = serializers.CharField(max_length=200)
    email = serializers.EmailField(max_length=254, required=False, allow_null=True)
    phone = serializers.RegexField(PHONE_RE, required=False, allow_null=True)
    employee_code = _opt(50)
    designation = _opt(100)
    facility_roles = serializers.SerializerMethodField()   # assignments in the CURRENT facility only

    class Meta:
        model = User
        fields = [
            "public_id", "username", "full_name", "email", "phone", "employee_code", "designation",
            "facility_roles", "is_active", "row_version", "created_at", "updated_at",
        ]
        read_only_fields = ["public_id", "is_active", "row_version", "created_at", "updated_at"]

    def validate_username(self, value):
        value = value.strip()
        if not USERNAME_RE.match(value):
            raise serializers.ValidationError("3-64 characters: letters, digits, '.', '_' or '-'; must start with a letter or digit.")
        qs = User.objects.filter(is_active=True, username=value)   # citext: case-insensitive
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This username is already in use.")
        return value

    def get_facility_roles(self, obj):
        rows = getattr(obj, "current_facility_roles", None)
        if rows is None:
            ctx = getattr(self.context.get("request"), "bems", None)
            if ctx is None or ctx.facility is None:
                return []
            rows = UserFacilityRole.objects.filter(
                user_id=obj.id, facility_id=ctx.facility.id, is_active=True, role__is_active=True
            ).select_related("role", "facility")
        return [
            {"facility": str(r.facility.public_id), "facility_code": r.facility.code,
             "role": str(r.role.public_id), "role_code": r.role.code}
            for r in rows
        ]


class RoleSerializer(BlankToNullMixin, serializers.ModelSerializer):
    code = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=100)
    description = _opt(500)
    permission_codes = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = ["public_id", "code", "name", "description", "is_system", "permission_codes",
                  "is_active", "row_version", "created_at", "updated_at"]
        read_only_fields = ["public_id", "is_system", "is_active", "row_version", "created_at", "updated_at"]

    def validate_code(self, value):
        value = value.strip().upper()
        if not ROLE_CODE_RE.match(value):
            raise serializers.ValidationError("Use A-Z, 0-9 and '_'; must start with a letter.")
        qs = Role.objects.filter(is_active=True, code=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This code is already in use.")
        return value

    def get_permission_codes(self, obj):
        rows = getattr(obj, "prefetched_perms", None)
        if rows is None:
            return sorted(
                obj.role_permissions.filter(permission__is_active=True).values_list("permission__code", flat=True)
            )
        return sorted(rp.permission.code for rp in rows)


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ["public_id", "code", "module", "description"]
        read_only_fields = fields


class RolePermissionsInputSerializer(serializers.Serializer):
    permission_codes = serializers.ListField(
        child=serializers.RegexField(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$", max_length=100),
        allow_empty=True, max_length=200,
    )
    row_version = serializers.IntegerField(min_value=1)


class FacilityRolesInputSerializer(serializers.Serializer):
    facility = serializers.UUIDField(required=False)
    roles = serializers.ListField(child=serializers.UUIDField(), allow_empty=True, max_length=20)

    def validate_roles(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError("Duplicate roles.")
        return value


class AuditLogSerializer(serializers.ModelSerializer):
    changed_fields = serializers.ListField(child=serializers.CharField(), read_only=True, allow_null=True)
    ip_address = serializers.CharField(read_only=True, allow_null=True)

    class Meta:
        model = AuditLog
        fields = [
            "id", "occurred_at", "actor_username", "action", "entity_type", "entity_public_id",
            "previous_value", "new_value", "changed_fields", "request_id", "ip_address",
            "http_method", "request_path",
        ]
        read_only_fields = fields