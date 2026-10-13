import django_filters as df

from .models import CondemnationRequest, DepreciationPolicy, Disposal, ReplacementPlan, TcoSnapshot


class DepreciationPolicyFilter(df.FilterSet):
    scope = df.ChoiceFilter(choices=[("CATEGORY", "CATEGORY"), ("EQUIPMENT", "EQUIPMENT")], method="f_scope")
    category = df.UUIDFilter(field_name="category__public_id")
    equipment = df.UUIDFilter(field_name="equipment__public_id")

    class Meta:
        model = DepreciationPolicy
        fields = ["method"]

    def f_scope(self, qs, name, value):
        return qs.filter(equipment__isnull=False) if value == "EQUIPMENT" else qs.filter(category__isnull=False)


class CondemnationFilter(df.FilterSet):
    equipment = df.UUIDFilter(field_name="equipment__public_id")
    mine = df.BooleanFilter(method="f_mine")
    date_from = df.DateFilter(field_name="created_at", lookup_expr="date__gte")
    date_to = df.DateFilter(field_name="created_at", lookup_expr="date__lte")
    search = df.CharFilter(field_name="request_number", lookup_expr="icontains")

    class Meta:
        model = CondemnationRequest
        fields = ["status", "reason_category"]

    def f_mine(self, qs, name, value):
        return qs.filter(created_by=self.request.user.id) if value else qs


class DisposalFilter(df.FilterSet):
    method = df.CharFilter(field_name="disposal_method")
    equipment = df.UUIDFilter(field_name="equipment__public_id")
    date_from = df.DateFilter(field_name="disposal_date", lookup_expr="gte")
    date_to = df.DateFilter(field_name="disposal_date", lookup_expr="lte")
    search = df.CharFilter(field_name="disposal_number", lookup_expr="icontains")

    class Meta:
        model = Disposal
        fields = ["status"]


class ReplacementPlanFilter(df.FilterSet):
    equipment = df.UUIDFilter(field_name="equipment__public_id")

    class Meta:
        model = ReplacementPlan
        fields = ["status", "priority", "planned_year"]


class CandidateFilter(df.FilterSet):
    indicator = df.ChoiceFilter(field_name="replacement_indicator",
                                choices=[("REVIEW", "REVIEW"), ("REPLACE_RECOMMENDED", "REPLACE_RECOMMENDED")])
    category = df.UUIDFilter(field_name="equipment__equipment_model__category__public_id")
    department = df.UUIDFilter(field_name="equipment__owning_department__public_id")

    class Meta:
        model = TcoSnapshot
        fields = []
