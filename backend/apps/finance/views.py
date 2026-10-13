from django.utils import timezone  # noqa: F401  (kept for parity with other apps)
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.core.errors import Conflict
from apps.equipment.models import Equipment
from apps.foundation.viewsets import FacilityScopedViewSet
from apps.maintenance.services import today_for

from . import depreciation as dep
from . import lifecycle, tco
from . import services as fin
from .filters import (
    CandidateFilter, CondemnationFilter, DepreciationPolicyFilter, DisposalFilter, ReplacementPlanFilter,
)
from .models import (
    CondemnationRequest, DepreciationEntry, DepreciationPolicy, DepreciationRun, Disposal, ReplacementPlan,
    TcoSnapshot,
)
from .serializers import (
    ApproveSerializer, CondemnationCreateSerializer, CondemnationUpdateSerializer, DepreciationPolicySerializer,
    DepreciationRunSerializer, DisposalCreateSerializer, DisposalUpdateSerializer, FinanceSettingsSerializer,
    NoteRequiredSerializer, OpeningBookValueSerializer, ReasonSerializer, ReplacementPlanSerializer, RunSerializer,
    TcoGenerateSerializer, condemnation_repr, disposal_repr, entry_repr, settings_repr, snapshot_repr,
)


class _FinViewSet(FacilityScopedViewSet):
    def _body(self, ser_cls, partial=False):
        ser = ser_cls(data=self.request.data, partial=partial, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        data = dict(ser.validated_data)
        return data, data.pop("row_version", None)

    def _refusal_audited(self, action_name, entity, obj, call):
        """A refusal by a business gate has already rolled back: audit it in autocommit, then re-raise."""
        try:
            return call()
        except (Conflict, PermissionDenied) as exc:
            fin.audit_refused(self.request, action_name, entity, obj, exc)
            raise


# ================================================================== settings, policies, runs
class FinanceSettingsViewSet(_FinViewSet):
    """GET / PUT /finance-settings/ (PUT is an upsert)."""
    queryset = DepreciationPolicy.objects.none()
    http_method_names = ["get", "put", "head"]
    required_permissions = {"retrieve_settings": "finance.view", "upsert": "finance.manage"}

    def retrieve_settings(self, request, *args, **kwargs):
        return Response(settings_repr(fin.get_settings(self.ctx.facility)))

    def upsert(self, request, *args, **kwargs):
        data, version = self._body(FinanceSettingsSerializer)
        fin.upsert_settings(request=request, facility=self.ctx.facility, data=data, expected_version=version)
        return Response(settings_repr(fin.get_settings(self.ctx.facility)))


class DepreciationPolicyViewSet(_FinViewSet):
    queryset = DepreciationPolicy.objects.select_related("category", "equipment")
    serializer_class = DepreciationPolicySerializer
    audit_entity_type = "DepreciationPolicy"
    required_permissions = {"list": "finance.view", "retrieve": "finance.view", "create": "finance.manage",
                            "update": "finance.manage", "partial_update": "finance.manage",
                            "destroy": "finance.manage"}
    include_inactive_permission = "finance.manage"
    filterset_class = DepreciationPolicyFilter
    ordering_fields = ["method", "created_at"]
    ordering = ["-created_at", "-id"]


class DepreciationRunViewSet(_FinViewSet):
    queryset = DepreciationRun.objects.all()
    serializer_class = DepreciationRunSerializer
    http_method_names = ["get", "head"]
    required_permissions = {"list": "finance.view", "retrieve": "finance.view"}
    ordering_fields = ["started_at", "run_period", "status"]
    ordering = ["-started_at", "-id"]


class DepreciationRunActionViewSet(_FinViewSet):
    """POST /depreciation/run/ (optional body {"month": "YYYY-MM"})."""
    queryset = DepreciationRun.objects.all()
    http_method_names = ["post"]
    required_permissions = {"run": "finance.run"}

    def run(self, request, *args, **kwargs):
        data, _ = self._body(RunSerializer)
        _, summary = fin.run_depreciation(facility=self.ctx.facility, target_month=data.get("month"), request=request)
        return Response(summary)


class TcoActionViewSet(_FinViewSet):
    """POST /tco/generate/ (optional body {"as_of": "YYYY-MM-DD"})."""
    queryset = TcoSnapshot.objects.all()
    hide_inactive = False
    http_method_names = ["post"]
    required_permissions = {"generate": "finance.run"}

    def generate(self, request, *args, **kwargs):
        data, _ = self._body(TcoGenerateSerializer)
        return Response(tco.generate_tco_snapshots(facility=self.ctx.facility, as_of_date=data.get("as_of"),
                                                   request=request))


class FinanceSummaryViewSet(_FinViewSet):
    """GET /finance/summary/?group_by=category|department|funding_source|ownership_type|location"""
    queryset = Equipment.objects.all()
    http_method_names = ["get"]
    required_permissions = {"summary": "finance.view"}

    def summary(self, request, *args, **kwargs):
        group_by = request.query_params.get("group_by", "category")
        if group_by not in fin.GROUP_BY_CHOICES:
            raise ValidationError({"group_by": ["Choose one of: " + ", ".join(fin.GROUP_BY_CHOICES) + "."]})
        return Response(fin.finance_summary(self.ctx.facility, group_by))


# ================================================================== per-equipment finance
class EquipmentFinanceViewSet(_FinViewSet):
    queryset = Equipment.objects.all()
    http_method_names = ["get", "post", "head"]
    required_permissions = {"finance": "finance.view", "depreciation": "finance.view", "tco": "finance.view",
                            "tco_snapshots": "finance.view", "opening_book_value": "finance.manage",
                            "condemnation_check": "condemnation.view"}

    def scope_queryset(self, qs):
        return super().scope_queryset(qs).select_related("equipment_model")

    def finance(self, request, public_id=None):
        return Response(fin.equipment_finance_info(self.get_object()))

    def depreciation(self, request, public_id=None):
        eq = self.get_object()
        qs = DepreciationEntry.objects.filter(facility_id=eq.facility_id, equipment_id=eq.pk).order_by("-period_month")
        page = self.paginate_queryset(qs)
        resp = self.get_paginated_response([entry_repr(e) for e in page])
        resp.data["projection"] = [{**p, "period_month": p["period_month"].strftime("%Y-%m")}
                                   for p in fin.equipment_projection(eq)]
        return resp

    def tco(self, request, public_id=None):
        eq = self.get_object()
        res = tco.compute_tco(self.ctx.facility, [eq.pk], today_for(self.ctx.facility))
        return Response(res.get(eq.pk))

    def tco_snapshots(self, request, public_id=None):
        eq = self.get_object()
        qs = TcoSnapshot.objects.filter(facility_id=eq.facility_id, equipment_id=eq.pk).order_by("-as_of_date")
        page = self.paginate_queryset(qs)
        return self.get_paginated_response([snapshot_repr(s) for s in page])

    def opening_book_value(self, request, public_id=None):
        eq = self.get_object()
        data, _ = self._body(OpeningBookValueSerializer)
        self._refusal_audited("OPENING_BOOK_VALUE_REFUSED", "Equipment", eq, lambda: fin.set_opening_book_value(
            request=request, equipment=eq, as_of_month=data["as_of_month"], book_value=data["book_value"]))
        return Response(fin.equipment_finance_info(Equipment.objects.select_related("equipment_model").get(pk=eq.pk)),
                        status=201)

    def condemnation_check(self, request, public_id=None):
        eq = self.get_object()
        blockers = lifecycle.condemnation_blockers(eq)
        return Response({"can_request": not blockers, "blockers": blockers})


# ================================================================== condemnation
class CondemnationRequestViewSet(_FinViewSet):
    """No PUT, no DELETE: requests are cancelled or revoked, never deleted."""
    queryset = CondemnationRequest.objects.all()
    http_method_names = ["get", "post", "patch", "head"]
    audit_entity_type = "CondemnationRequest"
    filterset_class = CondemnationFilter
    ordering_fields = ["request_number", "status", "created_at", "book_value_at_request"]
    ordering = ["-created_at", "-id"]
    required_permissions = {
        "list": "condemnation.view", "retrieve": "condemnation.view", "create": "condemnation.add",
        "partial_update": "condemnation.view", "cancel": "condemnation.view",   # requester or approver (service)
        "approve": "condemnation.approve", "reject": "condemnation.approve", "revoke": "condemnation.approve",
        "disposal": "disposal.manage",
    }

    def scope_queryset(self, qs):
        return super().scope_queryset(qs).select_related("equipment", "source_verification_item")

    def _one(self, pk, detail=True):
        row = self.get_queryset().get(pk=pk)
        names = fin.usernames([row.created_by, row.decided_by])
        return condemnation_repr(row, names, detail=detail, request=self.request)

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        names = fin.usernames(o.created_by for o in page)
        return self.get_paginated_response([condemnation_repr(o, names) for o in page])

    def retrieve(self, request, *args, **kwargs):
        return Response(self._one(self.get_object().pk))

    def create(self, request, *args, **kwargs):
        data, _ = self._body(CondemnationCreateSerializer)
        eq = data.pop("equipment")
        cr = self._refusal_audited("CONDEMNATION_REQUEST_REFUSED", "Equipment", eq, lambda: lifecycle.request_condemnation(
            request=request, facility=self.ctx.facility, equipment=eq, data=data))
        return Response(self._one(cr.pk), status=201)

    def partial_update(self, request, *args, **kwargs):
        version = self.parse_row_version(request.data.get("row_version"))
        data, _ = self._body(CondemnationUpdateSerializer, partial=True)
        cr = self.get_object()
        lifecycle.update_request(request=request, cr=cr, expected_version=version, fields=data)
        return Response(self._one(cr.pk))

    @action(detail=True, methods=["post"])
    def approve(self, request, public_id=None):
        cr = self.get_object()
        data, version = self._body(ApproveSerializer)
        self._refusal_audited("CONDEMNATION_APPROVAL_REFUSED", "CondemnationRequest", cr, lambda: lifecycle.approve(
            request=request, cr=cr, committee_reference=data.get("committee_reference"),
            committee_decision_date=data.get("committee_decision_date"), note=data.get("note"),
            expected_version=version))
        return Response(self._one(cr.pk))

    @action(detail=True, methods=["post"])
    def reject(self, request, public_id=None):
        cr = self.get_object()
        data, version = self._body(NoteRequiredSerializer)
        lifecycle.reject(request=request, cr=cr, note=data["note"], expected_version=version)
        return Response(self._one(cr.pk))

    @action(detail=True, methods=["post"])
    def cancel(self, request, public_id=None):
        cr = self.get_object()
        data, version = self._body(ReasonSerializer)
        lifecycle.cancel_request(request=request, cr=cr, reason=data["reason"], expected_version=version)
        return Response(self._one(cr.pk))

    @action(detail=True, methods=["post"])
    def revoke(self, request, public_id=None):
        cr = self.get_object()
        data, version = self._body(ReasonSerializer)
        self._refusal_audited("CONDEMNATION_REVOKE_REFUSED", "CondemnationRequest", cr, lambda: lifecycle.revoke(
            request=request, cr=cr, reason=data["reason"], expected_version=version))
        return Response(self._one(cr.pk))

    @action(detail=True, methods=["post"], url_path="disposal")
    def disposal(self, request, public_id=None):
        cr = self.get_object()
        data, _ = self._body(DisposalCreateSerializer)
        d = self._refusal_audited("DISPOSAL_CREATE_REFUSED", "CondemnationRequest", cr, lambda: lifecycle.create_disposal(
            request=request, cr=cr, data=data))
        return Response(_disposal_one(d.pk, self), status=201)


# ================================================================== disposals
def _disposal_one(pk, view):
    d = Disposal.objects.select_related("equipment", "condemnation_request", "recipient_vendor").get(
        pk=pk, facility_id=view.ctx.facility.id)
    return disposal_repr(d, fin.usernames([d.completed_by]))


class DisposalViewSet(_FinViewSet):
    """No POST here (a disposal is created from its condemnation request), no PUT, no DELETE."""
    queryset = Disposal.objects.all()
    http_method_names = ["get", "patch", "post", "head"]
    audit_entity_type = "Disposal"
    filterset_class = DisposalFilter
    ordering_fields = ["disposal_number", "disposal_date", "status", "proceeds_amount", "created_at"]
    ordering = ["-created_at", "-id"]
    required_permissions = {"list": "disposal.view", "retrieve": "disposal.view", "partial_update": "disposal.manage",
                            "complete": "disposal.manage", "cancel": "disposal.manage"}

    def scope_queryset(self, qs):
        return super().scope_queryset(qs).select_related("equipment", "condemnation_request", "recipient_vendor")

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        names = fin.usernames(d.completed_by for d in page)
        return self.get_paginated_response([disposal_repr(d, names) for d in page])

    def retrieve(self, request, *args, **kwargs):
        return Response(_disposal_one(self.get_object().pk, self))

    def partial_update(self, request, *args, **kwargs):
        data, version = self._body(DisposalUpdateSerializer, partial=True)
        if version is None:
            version = self.parse_row_version(request.data.get("row_version"))
        d = self.get_object()
        lifecycle.update_disposal(request=request, disposal=d, expected_version=version, fields=data)
        return Response(_disposal_one(d.pk, self))

    @action(detail=True, methods=["post"])
    def complete(self, request, public_id=None):
        d = self.get_object()
        data, version = self._body(_EmptyBody)
        self._refusal_audited("DISPOSAL_COMPLETE_REFUSED", "Disposal", d, lambda: lifecycle.complete_disposal(
            request=request, disposal=d, expected_version=version))
        return Response(_disposal_one(d.pk, self))

    @action(detail=True, methods=["post"])
    def cancel(self, request, public_id=None):
        d = self.get_object()
        data, version = self._body(ReasonSerializer)
        lifecycle.cancel_disposal(request=request, disposal=d, reason=data["reason"], expected_version=version)
        return Response(_disposal_one(d.pk, self))


from .serializers import _In as _EmptyBody  # noqa: E402  (body with only an optional row_version)


# ================================================================== replacement planning
class ReplacementPlanViewSet(_FinViewSet):
    queryset = ReplacementPlan.objects.select_related("equipment", "replaced_by_equipment")
    serializer_class = ReplacementPlanSerializer
    audit_entity_type = "ReplacementPlan"
    required_permissions = {"list": "finance.view", "retrieve": "finance.view", "create": "finance.manage",
                            "update": "finance.manage", "partial_update": "finance.manage",
                            "destroy": "finance.manage"}
    include_inactive_permission = "finance.manage"
    filterset_class = ReplacementPlanFilter
    ordering_fields = ["planned_year", "priority", "status", "estimated_cost", "created_at"]
    ordering = ["planned_year", "-id"]


class ReplacementCandidateViewSet(_FinViewSet):
    """GET /replacement-candidates/: equipment whose latest TCO snapshot says REVIEW or REPLACE_RECOMMENDED."""
    queryset = TcoSnapshot.objects.all()
    hide_inactive = False
    http_method_names = ["get", "head"]
    required_permissions = {"list": "finance.view"}
    filterset_class = CandidateFilter
    ordering_fields = ["maintenance_cost_ratio_percent", "total_cost_of_ownership", "age_years", "as_of_date"]
    ordering = ["-total_cost_of_ownership", "-id"]

    def scope_queryset(self, qs):
        fid = self.ctx.facility.id
        latest = TcoSnapshot.objects.filter(facility_id=fid).order_by("equipment_id", "-as_of_date") \
            .distinct("equipment_id").values("id")
        return qs.filter(
            facility_id=fid, id__in=latest, replacement_indicator__in=("REVIEW", "REPLACE_RECOMMENDED"),
            equipment__is_active=True, equipment__lifecycle_stage__in=("COMMISSIONED", "CONDEMNED"),
        ).select_related("equipment__equipment_model__category", "equipment__owning_department")

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        ids = [s.equipment_id for s in page]
        books = fin.latest_entries(ids)
        planned = set(ReplacementPlan.objects.filter(
            facility_id=self.ctx.facility.id, equipment_id__in=ids, is_active=True,
            status__in=("CANDIDATE", "APPROVED_FOR_BUDGET", "DEFERRED")).values_list("equipment_id", flat=True))
        rows = []
        for s in page:
            e = s.equipment
            _, reasons = dep.replacement_indicator(s.maintenance_cost_ratio_percent, s.age_years,
                                                   s.expected_life_years, s.threshold_percent)
            b = books.get(s.equipment_id)
            cat, dept = e.equipment_model.category, e.owning_department
            rows.append({
                **snapshot_repr(s), "reasons": reasons,
                "equipment": {"public_id": str(e.public_id), "asset_tag": e.asset_tag, "name": e.name,
                              "lifecycle_stage": e.lifecycle_stage,
                              "category": cat.name if cat else None, "department": dept.name if dept else None},
                "book_value": b.closing_value if b is not None and e.ownership_type == "OWNED" else None,
                "has_open_plan": s.equipment_id in planned,
            })
        return self.get_paginated_response(rows)
