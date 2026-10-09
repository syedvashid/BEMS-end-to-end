from decimal import Decimal

from django.db import transaction
from django.db.models import Count, DecimalField, Exists, OuterRef, Subquery, Sum
from django.db.models.functions import Coalesce
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, NotFound, ValidationError
from rest_framework.response import Response

from apps.core import audit
from apps.core.errors import Conflict
from apps.equipment.models import Equipment
from apps.foundation.models import User
from apps.foundation.permissions import deny
from apps.foundation.viewsets import UUID_RE, FacilityScopedViewSet

from . import services, stock
from .filters import ChecklistTemplateFilter, MaintenancePlanFilter, SparePartFilter, WorkOrderFilter
from .models import (
    ChecklistTemplate, ChecklistTemplateItem, EquipmentHold, MaintenancePlan, SparePart, SparePartCategory,
    SparePartStockEntry, WorkOrder, WorkOrderEvent,
)
from .serializers import (
    AssignSerializer, BreakdownSerializer, CancelSerializer, ChecklistSaveSerializer, ChecklistTemplateSerializer,
    CloseSerializer, CompleteSerializer, EmptySerializer, GeneratePlansSerializer, IssuePartSerializer,
    MaintenancePlanSerializer, NoteSerializer, ReasonSerializer, ReturnPartSerializer, SparePartCategoriesSerializer,
    SparePartSerializer, StockSerializer, WorkOrderCreateSerializer, WorkOrderDetailSerializer,
    WorkOrderListSerializer, WorkOrderUpdateSerializer, entry_repr, hold_repr, user_ref,
)

QTY0 = Decimal("0")


def crud_perms(prefix, **extra):
    perms = {
        "list": f"{prefix}.view", "retrieve": f"{prefix}.view", "create": f"{prefix}.add",
        "update": f"{prefix}.change", "partial_update": f"{prefix}.change", "destroy": f"{prefix}.delete",
    }
    perms.update(extra)
    return perms


def _usernames(ids):
    ids = {i for i in ids if i is not None}
    return dict(User.objects.filter(id__in=ids).values_list("id", "username")) if ids else {}


# ================================================================== checklist templates
class ChecklistTemplateViewSet(FacilityScopedViewSet):
    queryset = ChecklistTemplate.objects.select_related("category", "equipment_model")
    serializer_class = ChecklistTemplateSerializer
    required_permissions = crud_perms("checklist_template")
    include_inactive_permission = "checklist_template.delete"
    filterset_class = ChecklistTemplateFilter
    ordering_fields = ["name", "created_at"]
    ordering = ["name"]

    def scope_queryset(self, qs):
        counts = ChecklistTemplateItem.objects.filter(checklist_template_id=OuterRef("pk")) \
            .values("checklist_template_id").annotate(c=Count("id")).values("c")
        return super().scope_queryset(qs).annotate(item_count=Coalesce(Subquery(counts), 0))

    def check_can_modify(self, instance, action):
        """Delete gate: blocked while active maintenance plans use this template."""
        if action == "SOFT_DELETE":
            n = MaintenancePlan.objects.filter(
                facility_id=instance.facility_id, checklist_template_id=instance.pk, is_active=True).count()
            if n:
                raise Conflict(f"Cannot delete: {n} active maintenance plans still use this template.")


# ================================================================== maintenance plans
class MaintenancePlanViewSet(FacilityScopedViewSet):
    queryset = MaintenancePlan.objects.select_related("equipment", "checklist_template", "default_assignee_user")
    serializer_class = MaintenancePlanSerializer
    required_permissions = crud_perms(
        "maintenance_plan", generate="maintenance_plan.add", due="maintenance_plan.view",
        generate_work_order="work_order.change")
    include_inactive_permission = "maintenance_plan.delete"
    filterset_class = MaintenancePlanFilter
    ordering_fields = ["name", "next_due_date", "priority", "created_at"]
    ordering = ["next_due_date", "id"]

    @action(detail=False, methods=["post"])
    def generate(self, request):
        ser = GeneratePlansSerializer(data=request.data, context=self.get_serializer_context())
        self.reject_unknown_fields(request.data, allowed=set(ser.fields))
        ser.is_valid(raise_exception=True)
        d = dict(ser.validated_data)
        d["default_assignee"] = d.get("default_assignee")
        with transaction.atomic():
            result = services.generate_plans(request=request, facility=self.ctx.facility, **d)
        return Response(result, status=201)

    @action(detail=False, methods=["get"])
    def due(self, request):
        try:
            within = int(request.query_params.get("within_days", 30))
        except ValueError:
            raise ValidationError({"within_days": ["A valid integer is required."]})
        within = max(0, min(within, 730))
        today = services.today_for(self.ctx.facility)
        open_wo = WorkOrder.objects.filter(maintenance_plan_id=OuterRef("pk")).exclude(
            status__in=services.DONE_STATUSES).order_by("-id")
        qs = self.get_queryset().filter(
            equipment__lifecycle_stage="COMMISSIONED", next_due_date__lte=services_add_days(today, within)
        ).annotate(
            open_wo_public_id=Subquery(open_wo.values("public_id")[:1]),
            open_wo_number=Subquery(open_wo.values("wo_number")[:1]),
            open_wo_status=Subquery(open_wo.values("status")[:1]),
        ).order_by("next_due_date", "id")
        page = self.paginate_queryset(qs)
        rows = []
        for p in page:
            delta = (p.next_due_date - today).days
            e = p.equipment
            rows.append({
                "public_id": str(p.public_id), "name": p.name, "priority": p.priority,
                "frequency_type": p.frequency_type, "frequency_value": p.frequency_value,
                "next_due_date": p.next_due_date, "last_performed_date": p.last_performed_date,
                "is_overdue": delta < 0, "days_left": max(delta, 0), "days_overdue": max(-delta, 0),
                "equipment": {"public_id": str(e.public_id), "asset_tag": e.asset_tag, "name": e.name,
                              "operational_state": e.operational_state},
                "open_work_order": ({"public_id": str(p.open_wo_public_id), "wo_number": p.open_wo_number,
                                     "status": p.open_wo_status} if p.open_wo_public_id else None),
            })
        return self.get_paginated_response(rows)

    @action(detail=True, methods=["post"], url_path="generate-work-order")
    def generate_work_order(self, request, public_id=None):
        self.reject_unknown_fields(request.data, allowed=set())
        plan = self.get_object()
        with transaction.atomic():
            wo = services.create_pm_work_order(request=request, plan=plan, due_date=plan.next_due_date)
        if wo is None:
            raise Conflict("A work order already exists for this plan and due date.")
        return Response(WorkOrderDetailSerializer(wo, context=self.get_serializer_context()).data, status=201)


def services_add_days(d, n):
    from datetime import timedelta
    return d + timedelta(days=n)


# ================================================================== work orders
class WorkOrderViewSet(FacilityScopedViewSet):
    queryset = WorkOrder.objects.all()
    audit_entity_type = "WorkOrder"
    filterset_class = WorkOrderFilter
    ordering_fields = ["wo_number", "status", "priority", "due_date", "reported_at", "created_at"]
    ordering = ["-created_at", "-id"]
    http_method_names = ["get", "post", "patch", "head", "delete"]   # DELETE answers 405 (cancel instead)
    required_permissions = {
        "list": "work_order.view", "retrieve": "work_order.view", "events": "work_order.view",
        "parts": "work_order.view", "create": "work_order.change", "partial_update": "work_order.change",
        "update": "work_order.change", "destroy": "work_order.change",
        "report_breakdown": "work_order.add", "assign": "work_order.assign", "assignees": "work_order.assign",
        "start": "work_order.execute", "waiting_parts": "work_order.execute", "resume": "work_order.execute",
        "complete": "work_order.execute", "notes": "work_order.execute", "checklist": "work_order.execute",
        "return_part": "work_order.execute", "close": "work_order.close", "cancel": "work_order.close",
    }

    def scope_queryset(self, qs):
        return super().scope_queryset(qs).select_related(
            "equipment", "equipment__current_location", "assigned_to_user", "reported_by_department",
            "maintenance_plan", "parent_work_order", "service_provider_vendor", "standby_equipment")

    def get_serializer_class(self):
        if self.action == "list":
            return WorkOrderListSerializer
        if self.action in ("update", "partial_update"):
            return WorkOrderUpdateSerializer
        return WorkOrderDetailSerializer

    def check_can_modify(self, instance, action):
        if instance.status in services.LOCKED_STATUSES:
            raise Conflict("A closed or cancelled work order can no longer be edited.")

    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed("DELETE")

    def _detail(self, pk):
        return WorkOrderDetailSerializer(self.get_queryset().get(pk=pk), context=self.get_serializer_context()).data

    # ---------------------------------------------------------------- create
    def create(self, request, *args, **kwargs):
        ser = WorkOrderCreateSerializer(data=request.data, context=self.get_serializer_context())
        self.reject_unknown_fields(request.data, allowed=set(ser.fields))
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            wo = services.create_work_order(request=request, facility=self.ctx.facility, **dict(ser.validated_data))
        return Response(self._detail(wo.pk), status=201)

    @action(detail=False, methods=["post"], url_path="report-breakdown")
    def report_breakdown(self, request):
        ser = BreakdownSerializer(data=request.data, context=self.get_serializer_context())
        self.reject_unknown_fields(request.data, allowed=set(ser.fields))
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            wo = services.report_breakdown(request=request, facility=self.ctx.facility, **dict(ser.validated_data))
        # a ward user (work_order.add only) gets the created order back; the detail shows no actions for them
        return Response(self._detail(wo.pk), status=201)

    @action(detail=False, methods=["get"])
    def assignees(self, request):
        fid = self.ctx.facility.id
        users = User.objects.filter(
            is_active=True, facility_roles__facility_id=fid, facility_roles__is_active=True,
            facility_roles__role__is_active=True,
            facility_roles__role__role_permissions__permission__code="work_order.execute",
            facility_roles__role__role_permissions__permission__is_active=True,
        ).distinct().order_by("full_name")
        return Response({"results": [user_ref(u) for u in users]})

    # ---------------------------------------------------------------- status actions
    def _act(self, request, ser_cls, call):
        ser = ser_cls(data=request.data, context=self.get_serializer_context())
        self.reject_unknown_fields(request.data, allowed=set(ser.fields) | {"row_version"})
        ser.is_valid(raise_exception=True)
        version = self.parse_row_version(request.data.get("row_version"))
        with transaction.atomic():
            wo = self.get_object_for_update()
            call(wo, dict(ser.validated_data), version)
        return Response(self._detail(wo.pk))

    @action(detail=True, methods=["post"])
    def assign(self, request, public_id=None):
        return self._act(request, AssignSerializer, lambda wo, d, v: services.assign(
            request=request, wo=wo, user=d["assigned_to"], note=d.get("note"), expected_version=v))

    @action(detail=True, methods=["post"])
    def start(self, request, public_id=None):
        return self._act(request, EmptySerializer, lambda wo, d, v: services.start(
            request=request, wo=wo, expected_version=v))

    @action(detail=True, methods=["post"], url_path="waiting-parts")
    def waiting_parts(self, request, public_id=None):
        return self._act(request, ReasonSerializer, lambda wo, d, v: services.set_waiting_parts(
            request=request, wo=wo, reason=d["reason"], expected_version=v))

    @action(detail=True, methods=["post"])
    def resume(self, request, public_id=None):
        return self._act(request, EmptySerializer, lambda wo, d, v: services.resume(
            request=request, wo=wo, expected_version=v))

    @action(detail=True, methods=["post"])
    def complete(self, request, public_id=None):
        return self._act(request, CompleteSerializer, lambda wo, d, v: services.complete(
            request=request, wo=wo, data=d, expected_version=v))

    @action(detail=True, methods=["post"])
    def close(self, request, public_id=None):
        return self._act(request, CloseSerializer, lambda wo, d, v: services.close(
            request=request, wo=wo, signoff_name=d["signoff_name"], expected_version=v))

    @action(detail=True, methods=["post"])
    def cancel(self, request, public_id=None):
        return self._act(request, CancelSerializer, lambda wo, d, v: services.cancel(
            request=request, wo=wo, reason=d["reason"], next_due_date=d.get("next_due_date"), expected_version=v))

    @action(detail=True, methods=["post"])
    def notes(self, request, public_id=None):
        ser = NoteSerializer(data=request.data)
        self.reject_unknown_fields(request.data, allowed=set(ser.fields))
        ser.is_valid(raise_exception=True)
        wo = self.get_object()
        services.add_note(request=request, wo=wo, text=ser.validated_data["note"])
        return Response(self._detail(wo.pk), status=201)

    @action(detail=True, methods=["put"])
    def checklist(self, request, public_id=None):
        ser = ChecklistSaveSerializer(data=request.data)
        self.reject_unknown_fields(request.data, allowed=set(ser.fields))
        ser.is_valid(raise_exception=True)
        wo = self.get_object()
        services.save_checklist(request=request, wo=wo, results=[dict(i) for i in ser.validated_data["items"]])
        return Response(self._detail(wo.pk))

    # ---------------------------------------------------------------- history and parts
    @action(detail=True, methods=["get"])
    def events(self, request, public_id=None):
        wo = self.get_object()
        qs = WorkOrderEvent.objects.filter(facility_id=wo.facility_id, work_order_id=wo.pk).order_by("-created_at", "-id")
        page = self.paginate_queryset(qs)
        names = _usernames(e.created_by for e in page)
        return self.get_paginated_response([{
            "public_id": str(e.public_id), "event_type": e.event_type, "from_status": e.from_status,
            "to_status": e.to_status, "note": e.note, "created_at": e.created_at,
            "created_by": names.get(e.created_by) or "system"} for e in page])

    @action(detail=True, methods=["get", "post"], url_path="parts")
    def parts(self, request, public_id=None):
        if request.method == "POST":
            if not self.ctx.has("work_order.execute"):
                deny(request, self, "issue_part", ("work_order.execute",))
            ser = IssuePartSerializer(data=request.data, context=self.get_serializer_context())
            self.reject_unknown_fields(request.data, allowed=set(ser.fields))
            ser.is_valid(raise_exception=True)
            d = ser.validated_data
            wo = self.get_object()
            entry = stock.issue_part(request=request, wo=wo, spare_part=d["spare_part"], quantity=d["quantity"],
                                     unit_cost=d.get("unit_cost"))
            entry = SparePartStockEntry.objects.select_related("spare_part").get(pk=entry.pk)
            return Response(entry_repr(entry, _usernames([entry.created_by])), status=201)
        wo = self.get_object()
        qs = SparePartStockEntry.objects.filter(facility_id=wo.facility_id, work_order_id=wo.pk) \
            .select_related("spare_part").order_by("-created_at", "-id")
        returned = dict(SparePartStockEntry.objects.filter(
            facility_id=wo.facility_id, work_order_id=wo.pk, entry_type="RETURN"
        ).values_list("related_entry_id").annotate(t=Sum("quantity")))
        page = self.paginate_queryset(qs)
        names = _usernames(e.created_by for e in page)
        return self.get_paginated_response([
            entry_repr(e, names, (-e.quantity - returned.get(e.pk, QTY0)) if e.entry_type == "CONSUMPTION" else None)
            for e in page])

    @action(detail=True, methods=["post"], url_path=rf"parts/(?P<entry>{UUID_RE})/return")
    def return_part(self, request, public_id=None, entry=None):
        ser = ReturnPartSerializer(data=request.data)
        self.reject_unknown_fields(request.data, allowed=set(ser.fields))
        ser.is_valid(raise_exception=True)
        wo = self.get_object()
        orig = SparePartStockEntry.objects.filter(
            public_id=entry, facility_id=wo.facility_id, work_order_id=wo.pk, entry_type="CONSUMPTION"
        ).select_related("spare_part").first()
        if orig is None:
            raise NotFound()
        ret = stock.return_part(request=request, wo=wo, entry=orig, quantity=ser.validated_data.get("quantity"))
        ret = SparePartStockEntry.objects.select_related("spare_part").get(pk=ret.pk)
        return Response(entry_repr(ret, _usernames([ret.created_by])), status=201)


# ================================================================== spare parts
class SparePartViewSet(FacilityScopedViewSet):
    queryset = SparePart.objects.all()
    serializer_class = SparePartSerializer
    required_permissions = crud_perms(
        "spare_part", categories="spare_part.change", stock="spare_part.stock", stock_entries="spare_part.view")
    include_inactive_permission = "spare_part.delete"
    filterset_class = SparePartFilter
    ordering_fields = ["part_code", "name", "created_at", "on_hand_quantity"]
    ordering = ["part_code"]

    def scope_queryset(self, qs):
        total = SparePartStockEntry.objects.filter(spare_part_id=OuterRef("pk")).values("spare_part_id") \
            .annotate(t=Sum("quantity")).values("t")
        return super().scope_queryset(qs).annotate(on_hand_quantity=Coalesce(
            Subquery(total), Decimal("0"), output_field=DecimalField(max_digits=14, decimal_places=3)))

    def check_can_modify(self, instance, action):
        """Delete gate: blocked while on-hand stock is greater than zero."""
        if action == "SOFT_DELETE" and stock.on_hand(instance) > 0:
            raise Conflict("Cannot delete: this part still has stock on hand.")

    def _detail(self, pk):
        return SparePartSerializer(self.get_queryset().get(pk=pk), context=self.get_serializer_context()).data

    @action(detail=True, methods=["put"])
    def categories(self, request, public_id=None):
        ser = SparePartCategoriesSerializer(data=request.data)
        self.reject_unknown_fields(request.data, allowed={"categories", "row_version"})
        ser.is_valid(raise_exception=True)
        expected = self.parse_row_version(request.data.get("row_version"))
        wanted = list(dict.fromkeys(ser.validated_data["categories"]))
        from apps.masters.models import EquipmentCategory
        with transaction.atomic():
            part = self.get_object_for_update()
            if part.row_version != expected:
                from apps.core.errors import StaleVersion
                raise StaleVersion(current_row_version=part.row_version)
            cats = list(EquipmentCategory.objects.filter(
                facility_id=part.facility_id, is_active=True, public_id__in=wanted))
            if len(cats) != len(wanted):
                raise ValidationError({"categories": ["Unknown reference."]})
            before = sorted(str(c.category.public_id) for c in
                            SparePartCategory.objects.filter(spare_part_id=part.pk).select_related("category"))
            SparePartCategory.objects.filter(spare_part_id=part.pk).delete()
            SparePartCategory.objects.bulk_create([
                SparePartCategory(facility_id=part.facility_id, spare_part=part, category=c,
                                  created_by=request.user.id) for c in cats])
            part.updated_by = request.user.id
            part.save(update_fields=["updated_by"])   # touch trigger bumps row_version
            after = sorted(str(c.public_id) for c in cats)
            audit.record(request=request, action="UPDATE", facility_id=part.facility_id, entity_type="SparePart",
                         entity_public_id=part.public_id, previous={"categories": before},
                         new={"categories": after}, changed_fields=["categories"])
        return Response(self._detail(part.pk))

    @action(detail=True, methods=["post"])
    def stock(self, request, public_id=None):
        ser = StockSerializer(data=request.data, context=self.get_serializer_context())
        self.reject_unknown_fields(request.data, allowed=set(ser.fields))
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        part = self.get_object()
        if d["entry_type"] == "RECEIPT":
            entry = stock.receive_stock(request=request, spare_part=part, quantity=d["quantity"],
                                        unit_cost=d.get("unit_cost"), supplier_vendor=d.get("supplier_vendor"),
                                        reference_note=d.get("reference_note"))
        else:
            entry = stock.adjust_stock(request=request, spare_part=part, quantity=d["quantity"], reason=d["reason"])
        return Response({"entry": entry_repr(SparePartStockEntry.objects.select_related("spare_part").get(pk=entry.pk),
                                             _usernames([entry.created_by])),
                         "part": self._detail(part.pk)}, status=201)

    @action(detail=True, methods=["get"], url_path="stock-entries")
    def stock_entries(self, request, public_id=None):
        part = self.get_object()
        qs = SparePartStockEntry.objects.filter(facility_id=part.facility_id, spare_part_id=part.pk) \
            .select_related("spare_part", "work_order").order_by("-created_at", "-id")
        page = self.paginate_queryset(qs)
        names = _usernames(e.created_by for e in page)
        rows = []
        for e in page:
            row = entry_repr(e, names)
            row["work_order"] = e.work_order.wo_number if e.work_order_id else None
            rows.append(row)
        return self.get_paginated_response(rows)
