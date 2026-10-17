from django.db.models import Q
from django_filters import rest_framework as filters

from . import engine
from .models import ChargeItem, ChargeMapping, ChargeRecord

STATUSES = ("PENDING_REVIEW", "APPROVED", "CANCELLED", "REVERSED")


def _choices(values):
    return [(v, v) for v in values]


class ChargeItemFilter(filters.FilterSet):
    search = filters.CharFilter(method="filter_search")

    class Meta:
        model = ChargeItem
        fields = []

    def filter_search(self, qs, name, value):
        return qs.filter(Q(item_code__icontains=value) | Q(name__icontains=value))


class ChargeMappingFilter(filters.FilterSet):
    equipment = filters.UUIDFilter(field_name="equipment__public_id")
    category = filters.UUIDFilter(field_name="category__public_id")
    charge_item = filters.UUIDFilter(field_name="charge_item__public_id")
    billing_rule = filters.ChoiceFilter(choices=_choices(engine.RULES))
    active_on = filters.DateFilter(method="filter_active_on")
    search = filters.CharFilter(method="filter_search")

    class Meta:
        model = ChargeMapping
        fields = []

    def filter_active_on(self, qs, name, value):
        return qs.filter(effective_from__lte=value).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=value))

    def filter_search(self, qs, name, value):
        return qs.filter(Q(equipment__asset_tag__icontains=value) | Q(equipment__name__icontains=value)
                         | Q(category__name__icontains=value) | Q(charge_item__item_code__icontains=value)
                         | Q(charge_item__name__icontains=value))


class ChargeRecordFilter(filters.FilterSet):
    status = filters.ChoiceFilter(choices=_choices(STATUSES))
    record_type = filters.ChoiceFilter(choices=_choices(("CHARGE", "REVERSAL")))
    source_type = filters.ChoiceFilter(choices=_choices(engine.BASES))
    equipment = filters.UUIDFilter(field_name="equipment__public_id")
    department = filters.UUIDFilter(field_name="department__public_id")
    patient_reference = filters.CharFilter(field_name="patient_reference", lookup_expr="iexact")
    encounter_reference = filters.CharFilter(field_name="encounter_reference", lookup_expr="iexact")
    billing_rule = filters.ChoiceFilter(choices=_choices(engine.CHARGING_RULES))
    charge_date_from = filters.DateFilter(field_name="charge_date", lookup_expr="gte")
    charge_date_to = filters.DateFilter(field_name="charge_date", lookup_expr="lte")
    exported = filters.BooleanFilter(method="filter_exported")
    search = filters.CharFilter(method="filter_search")

    class Meta:
        model = ChargeRecord
        fields = []

    def filter_exported(self, qs, name, value):
        return qs.filter(exported_at__isnull=not value)

    def filter_search(self, qs, name, value):
        return qs.filter(record_number__icontains=value)
