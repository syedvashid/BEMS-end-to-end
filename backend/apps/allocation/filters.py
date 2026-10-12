from django.db.models import Q
from django_filters import rest_framework as filters

from .models import EquipmentAllocation, EquipmentReservation, EquipmentTransferRequest, EquipmentUsageLog

SOURCES = [(s, s) for s in ("IPD", "OT", "ICU", "ER", "RADIOLOGY", "LAB", "MANUAL")]


class AllocationFilter(filters.FilterSet):
    equipment = filters.UUIDFilter(field_name="equipment__public_id")
    department = filters.UUIDFilter(field_name="department__public_id")
    location = filters.UUIDFilter(field_name="location__public_id")
    active = filters.BooleanFilter(method="filter_active")        # active = not released
    source_module = filters.ChoiceFilter(choices=SOURCES)
    patient_reference = filters.CharFilter(field_name="patient_reference", lookup_expr="iexact")
    assigned_from = filters.DateFilter(field_name="assigned_at", lookup_expr="date__gte")
    assigned_to = filters.DateFilter(field_name="assigned_at", lookup_expr="date__lte")
    search = filters.CharFilter(method="filter_search")

    class Meta:
        model = EquipmentAllocation
        fields = []

    def filter_active(self, qs, name, value):
        return qs.filter(released_at__isnull=bool(value))

    def filter_search(self, qs, name, value):
        return qs.filter(Q(equipment__asset_tag__icontains=value) | Q(equipment__name__icontains=value)
                         | Q(patient_reference__icontains=value) | Q(practitioner_name__icontains=value))


class ReservationFilter(filters.FilterSet):
    equipment = filters.UUIDFilter(field_name="equipment__public_id")
    department = filters.UUIDFilter(field_name="department__public_id")
    status = filters.ChoiceFilter(choices=[(s, s) for s in ("CONFIRMED", "CANCELLED", "FULFILLED", "NO_SHOW")])
    window_from = filters.IsoDateTimeFilter(method="filter_from")   # bookings overlapping [window_from, window_to)
    window_to = filters.IsoDateTimeFilter(method="filter_to")
    mine = filters.BooleanFilter(method="filter_mine")
    search = filters.CharFilter(method="filter_search")

    class Meta:
        model = EquipmentReservation
        fields = []

    def filter_from(self, qs, name, value):
        return qs.filter(end_at__gt=value)

    def filter_to(self, qs, name, value):
        return qs.filter(start_at__lt=value)

    def filter_mine(self, qs, name, value):
        q = Q(created_by=self.request.user.id)
        return qs.filter(q) if value else qs.exclude(q)

    def filter_search(self, qs, name, value):
        return qs.filter(Q(equipment__asset_tag__icontains=value) | Q(equipment__name__icontains=value)
                         | Q(purpose__icontains=value))


class UsageLogFilter(filters.FilterSet):
    equipment = filters.UUIDFilter(field_name="equipment__public_id")
    department = filters.UUIDFilter(field_name="department__public_id")
    date_from = filters.DateFilter(field_name="started_at", lookup_expr="date__gte")
    date_to = filters.DateFilter(field_name="started_at", lookup_expr="date__lte")
    search = filters.CharFilter(method="filter_search")

    class Meta:
        model = EquipmentUsageLog
        fields = []

    def filter_search(self, qs, name, value):
        return qs.filter(Q(equipment__asset_tag__icontains=value) | Q(equipment__name__icontains=value)
                         | Q(operator_name__icontains=value) | Q(procedure_text__icontains=value)
                         | Q(patient_reference__icontains=value))


class TransferFilter(filters.FilterSet):
    status = filters.ChoiceFilter(choices=[(s, s) for s in ("PENDING", "APPROVED", "REJECTED", "CANCELLED")])
    equipment = filters.UUIDFilter(field_name="equipment__public_id")
    to_department = filters.UUIDFilter(field_name="to_department__public_id")
    mine = filters.BooleanFilter(method="filter_mine")
    search = filters.CharFilter(method="filter_search")

    class Meta:
        model = EquipmentTransferRequest
        fields = []

    def filter_mine(self, qs, name, value):
        q = Q(created_by=self.request.user.id)
        return qs.filter(q) if value else qs.exclude(q)

    def filter_search(self, qs, name, value):
        return qs.filter(Q(equipment__asset_tag__icontains=value) | Q(equipment__name__icontains=value)
                         | Q(reason__icontains=value))