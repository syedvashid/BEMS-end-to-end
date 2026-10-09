import uuid
from datetime import timedelta

from django.db.models import Exists, F, OuterRef, Q
from django_filters import rest_framework as filters

from . import services
from .models import ChecklistTemplate, MaintenancePlan, SparePart, SparePartCategory, WorkOrder

PRIORITIES = [(p, p) for p in ("LOW", "MEDIUM", "HIGH", "CRITICAL")]


def _today(request):
    return services.today_for(request.bems.facility)


class ChecklistTemplateFilter(filters.FilterSet):
    category = filters.UUIDFilter(field_name="category__public_id")
    equipment_model = filters.UUIDFilter(field_name="equipment_model__public_id")
    search = filters.CharFilter(method="filter_search")

    class Meta:
        model = ChecklistTemplate
        fields = []

    def filter_search(self, qs, name, value):
        return qs.filter(Q(name__icontains=value) | Q(description__icontains=value))


class MaintenancePlanFilter(filters.FilterSet):
    equipment = filters.UUIDFilter(field_name="equipment__public_id")
    category = filters.UUIDFilter(field_name="equipment__equipment_model__category__public_id")
    checklist_template = filters.UUIDFilter(field_name="checklist_template__public_id")
    overdue = filters.BooleanFilter(method="filter_overdue")
    due_within_days = filters.NumberFilter(method="filter_due_within")
    search = filters.CharFilter(method="filter_search")

    class Meta:
        model = MaintenancePlan
        fields = []

    def filter_overdue(self, qs, name, value):
        today = _today(self.request)
        return qs.filter(next_due_date__lt=today) if value else qs.filter(next_due_date__gte=today)

    def filter_due_within(self, qs, name, value):
        return qs.filter(next_due_date__lte=_today(self.request) + timedelta(days=int(value)))

    def filter_search(self, qs, name, value):
        return qs.filter(Q(name__icontains=value) | Q(equipment__name__icontains=value)
                         | Q(equipment__asset_tag__icontains=value))


class WorkOrderFilter(filters.FilterSet):
    status = filters.CharFilter(method="filter_status")
    work_order_type = filters.ChoiceFilter(choices=[(t, t) for t in ("PREVENTIVE", "BREAKDOWN", "CORRECTIVE")])
    priority = filters.ChoiceFilter(choices=PRIORITIES)
    equipment = filters.UUIDFilter(field_name="equipment__public_id")
    assigned_to = filters.CharFilter(method="filter_assigned_to")
    overdue = filters.BooleanFilter(method="filter_overdue")
    reported_department = filters.UUIDFilter(field_name="reported_by_department__public_id")
    due_from = filters.DateFilter(field_name="due_date", lookup_expr="gte")
    due_to = filters.DateFilter(field_name="due_date", lookup_expr="lte")
    created_from = filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    created_to = filters.DateFilter(field_name="created_at", lookup_expr="date__lte")
    search = filters.CharFilter(method="filter_search")

    class Meta:
        model = WorkOrder
        fields = []

    def filter_status(self, qs, name, value):
        wanted = []
        for raw in self.request.query_params.getlist("status"):
            wanted += [s.strip().upper() for s in raw.split(",") if s.strip()]
        valid = {"OPEN", "ASSIGNED", "IN_PROGRESS", "WAITING_PARTS", "COMPLETED", "CLOSED", "CANCELLED"}
        wanted = [s for s in wanted if s in valid]
        return qs.filter(status__in=wanted) if wanted else qs

    def filter_assigned_to(self, qs, name, value):
        if value.strip().lower() == "me":
            return qs.filter(assigned_to_user_id=self.request.user.id)
        try:
            return qs.filter(assigned_to_user__public_id=uuid.UUID(value))
        except ValueError:
            return qs.none()

    def filter_overdue(self, qs, name, value):
        q = Q(due_date__lt=_today(self.request)) & ~Q(status__in=services.DONE_STATUSES)
        return qs.filter(q) if value else qs.exclude(q)

    def filter_search(self, qs, name, value):
        return qs.filter(Q(wo_number__icontains=value) | Q(equipment__name__icontains=value)
                         | Q(equipment__asset_tag__icontains=value) | Q(problem_description__icontains=value))


class SparePartFilter(filters.FilterSet):
    low_stock = filters.BooleanFilter(method="filter_low")
    category = filters.UUIDFilter(method="filter_category")
    search = filters.CharFilter(method="filter_search")

    class Meta:
        model = SparePart
        fields = []

    def filter_low(self, qs, name, value):
        return qs.filter(on_hand_quantity__lte=F("reorder_level")) if value \
            else qs.filter(on_hand_quantity__gt=F("reorder_level"))

    def filter_category(self, qs, name, value):
        return qs.filter(Exists(SparePartCategory.objects.filter(
            spare_part_id=OuterRef("pk"), category__public_id=value)))

    def filter_search(self, qs, name, value):
        return qs.filter(Q(part_code__icontains=value) | Q(name__icontains=value) | Q(description__icontains=value))
