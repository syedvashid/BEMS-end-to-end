import django_filters as df
from django.db import connection
from django.db.models import Q

from apps.masters.models import Location

from .models import Equipment
from .serializers import CRITICALITY, LIFECYCLE_STAGES, OPERATIONAL_STATES, OWNERSHIP_TYPES

_choices = lambda values: [(v, v) for v in values]   # noqa: E731


class CsvInFilter(df.BaseInFilter, df.CharFilter):
    """?lifecycle_stage=RECEIVED,INSTALLED (comma separated, parameterised IN)."""


class EquipmentFilter(df.FilterSet):
    category = df.UUIDFilter(field_name="equipment_model__category__public_id")
    equipment_model = df.UUIDFilter(field_name="equipment_model__public_id")
    manufacturer = df.UUIDFilter(field_name="equipment_model__manufacturer__public_id")
    lifecycle_stage = CsvInFilter(field_name="lifecycle_stage", lookup_expr="in")
    operational_state = CsvInFilter(field_name="operational_state", lookup_expr="in")
    department = df.UUIDFilter(field_name="owning_department__public_id")
    location = df.UUIDFilter(method="filter_location")
    location_subtree = df.BooleanFilter(method="filter_noop")
    ownership_type = df.ChoiceFilter(choices=_choices(OWNERSHIP_TYPES))
    criticality = df.ChoiceFilter(choices=_choices(CRITICALITY))
    supplier = df.UUIDFilter(field_name="supplier_vendor__public_id")
    funding_source = df.UUIDFilter(field_name="funding_source__public_id")
    is_legacy_entry = df.BooleanFilter()
    invoice_date_from = df.DateFilter(field_name="invoice_date", lookup_expr="gte")
    invoice_date_to = df.DateFilter(field_name="invoice_date", lookup_expr="lte")
    search = df.CharFilter(method="filter_search")

    class Meta:
        model = Equipment
        fields = []

    def filter_noop(self, queryset, name, value):
        return queryset

    def filter_location(self, queryset, name, value):
        fid = self.request.bems.facility.id
        root = Location.objects.filter(public_id=value, facility_id=fid, is_active=True) \
            .values_list("id", flat=True).first()
        if root is None:
            return queryset.none()
        flag = str(self.data.get("location_subtree", "true")).lower()
        if flag in ("false", "0"):
            return queryset.filter(current_location_id=root)
        with connection.cursor() as cur:
            cur.execute("SELECT location_subtree_ids(%s, %s)", [fid, root])
            ids = [r[0] for r in cur.fetchall()]
        return queryset.filter(current_location_id__in=ids)

    def filter_search(self, queryset, name, value):
        term = (value or "").strip()[:100]
        if not term:
            return queryset
        return queryset.filter(
            Q(name__icontains=term) | Q(equipment_model__model_name__icontains=term)
            | Q(equipment_model__model_number__icontains=term) | Q(serial_number__icontains=term)
            | Q(equipment_model__manufacturer__name__icontains=term)
            | Q(current_location__name__icontains=term) | Q(current_location__code__icontains=term)
            | Q(qr_code_value__icontains=term) | Q(asset_tag__icontains=term)
            | Q(legacy_asset_id__icontains=term))
