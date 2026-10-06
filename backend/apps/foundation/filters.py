from django_filters import rest_framework as df

from .models import AuditLog, Facility, Role, User


class FacilityFilter(df.FilterSet):
    code = df.CharFilter(field_name="code", lookup_expr="iexact")
    name = df.CharFilter(field_name="name", lookup_expr="icontains")
    city = df.CharFilter(field_name="city", lookup_expr="icontains")
    facility_type = df.CharFilter(field_name="facility_type", lookup_expr="exact")

    class Meta:
        model = Facility
        fields = []


class UserFilter(df.FilterSet):
    username = df.CharFilter(field_name="username", lookup_expr="icontains")
    full_name = df.CharFilter(field_name="full_name", lookup_expr="icontains")

    class Meta:
        model = User
        fields = []


class RoleFilter(df.FilterSet):
    code = df.CharFilter(field_name="code", lookup_expr="iexact")
    name = df.CharFilter(field_name="name", lookup_expr="icontains")
    is_system = df.BooleanFilter(field_name="is_system")

    class Meta:
        model = Role
        fields = []


class AuditLogFilter(df.FilterSet):
    entity_type = df.CharFilter(field_name="entity_type", lookup_expr="exact")
    entity_public_id = df.UUIDFilter(field_name="entity_public_id")
    actor = df.CharFilter(field_name="actor_username", lookup_expr="iexact")
    action = df.CharFilter(field_name="action", lookup_expr="exact")
    occurred_from = df.IsoDateTimeFilter(field_name="occurred_at", lookup_expr="gte")
    occurred_to = df.IsoDateTimeFilter(field_name="occurred_at", lookup_expr="lte")

    class Meta:
        model = AuditLog
        fields = []