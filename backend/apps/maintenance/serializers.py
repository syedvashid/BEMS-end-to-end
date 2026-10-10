from decimal import Decimal

from rest_framework import serializers

from apps.equipment.models import Equipment
from apps.equipment.serializers import ScopedFieldsMixin, ref
from apps.foundation.models import User
from apps.foundation.serializers import BlankToNullMixin, PublicIdField
from apps.masters.models import Department, EquipmentCategory, EquipmentModel, Vendor
from apps.compliance.models import AmcContract, Warranty
from . import services
from .models import (
    ChecklistTemplate, ChecklistTemplateItem, EquipmentHold, MaintenancePlan, SparePart, SparePartCategory,
    SparePartStockEntry, WorkOrder, WorkOrderChecklistItem,
)

PRIORITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
WO_TYPES = ["PREVENTIVE", "BREAKDOWN", "CORRECTIVE"]
COVERAGE = ["WARRANTY", "AMC", "PAID", "IN_HOUSE"]
ZERO = Decimal("0")


def _fac(serializer):
    return getattr(getattr(serializer.context.get("request"), "bems", None), "facility", None)


def user_ref(u):
    return None if u is None else {"public_id": str(u.public_id), "username": u.username, "full_name": u.full_name}


def _usernames(ids):
    ids = {i for i in ids if i is not None}
    return dict(User.objects.filter(id__in=ids).values_list("id", "username")) if ids else {}


class UserField(PublicIdField):
    """Active user by public_id (global table); membership is checked by the service."""
    def __init__(self, **kw):
        super().__init__(queryset=User.objects.filter(is_active=True), **kw)


# ================================================================== checklist templates
class ChecklistItemInputSerializer(BlankToNullMixin, serializers.Serializer):
    sequence = serializers.IntegerField(min_value=1, required=False)   # ignored: order of the array decides
    item_text = serializers.CharField(max_length=500)
    item_type = serializers.ChoiceField(choices=["CHECK", "MEASUREMENT"])
    unit = serializers.CharField(max_length=30, required=False, allow_null=True)
    min_value = serializers.DecimalField(max_digits=14, decimal_places=4, required=False, allow_null=True)
    max_value = serializers.DecimalField(max_digits=14, decimal_places=4, required=False, allow_null=True)

    def validate(self, a):
        a["item_text"] = a["item_text"].strip()
        if not a["item_text"]:
            raise serializers.ValidationError({"item_text": ["This field may not be blank."]})
        lo, hi = a.get("min_value"), a.get("max_value")
        if lo is not None and hi is not None and lo > hi:
            raise serializers.ValidationError({"min_value": ["Minimum cannot be greater than maximum."]})
        if a["item_type"] == "CHECK":
            a["unit"] = a["min_value"] = a["max_value"] = None
        return a


def replace_items(template, items, uid):
    ChecklistTemplateItem.objects.filter(checklist_template_id=template.pk).delete()
    ChecklistTemplateItem.objects.bulk_create([
        ChecklistTemplateItem(
            facility_id=template.facility_id, checklist_template=template, sequence=i, item_text=it["item_text"],
            item_type=it["item_type"], unit=it.get("unit"), min_value=it.get("min_value"),
            max_value=it.get("max_value"), created_by=uid) for i, it in enumerate(items, start=1)])


def item_repr(i):
    return {"sequence": i.sequence, "item_text": i.item_text, "item_type": i.item_type, "unit": i.unit,
            "min_value": i.min_value, "max_value": i.max_value}


class ChecklistTemplateSerializer(ScopedFieldsMixin, BlankToNullMixin, serializers.ModelSerializer):
    name = serializers.CharField(max_length=200)
    description = serializers.CharField(max_length=2000, required=False, allow_null=True)
    category = PublicIdField(queryset=EquipmentCategory.objects.none(), required=False, allow_null=True)
    equipment_model = PublicIdField(queryset=EquipmentModel.objects.none(), required=False, allow_null=True)
    items = ChecklistItemInputSerializer(many=True, required=False, max_length=100, write_only=True)
    SCOPED = {"category": EquipmentCategory, "equipment_model": EquipmentModel}

    class Meta:
        model = ChecklistTemplate
        fields = ["public_id", "name", "description", "category", "equipment_model", "items",
                  "is_active", "row_version", "created_at", "updated_at"]
        read_only_fields = ["public_id", "is_active", "row_version", "created_at", "updated_at"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("This field may not be blank.")
        fac = _fac(self)
        if fac is not None:
            qs = ChecklistTemplate.objects.filter(facility_id=fac.id, is_active=True, name__iexact=value)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError("A checklist template with this name already exists.")
        return value

    def create(self, validated_data):
        items = validated_data.pop("items", None)
        obj = super().create(validated_data)
        if items:
            replace_items(obj, items, validated_data.get("created_by"))
        return obj

    def update(self, instance, validated_data):
        items = validated_data.pop("items", None)
        obj = super().update(instance, validated_data)
        if items is not None:
            replace_items(obj, items, validated_data.get("updated_by"))
        return obj

    def to_representation(self, o):
        data = super().to_representation(o)
        data["category"] = ref(o.category, "code", "name")
        data["equipment_model"] = ref(o.equipment_model, "model_name", "model_number")
        if getattr(self.context.get("view"), "action", None) == "list":
            data["item_count"] = getattr(o, "item_count", None)
        else:
            data["items"] = [item_repr(i) for i in
                             ChecklistTemplateItem.objects.filter(checklist_template_id=o.pk).order_by("sequence")]
        return data


# ================================================================== maintenance plans
class MaintenancePlanSerializer(ScopedFieldsMixin, BlankToNullMixin, serializers.ModelSerializer):
    name = serializers.CharField(max_length=200)
    equipment = PublicIdField(queryset=Equipment.objects.none())
    checklist_template = PublicIdField(queryset=ChecklistTemplate.objects.none(), required=False, allow_null=True)
    frequency_type = serializers.ChoiceField(choices=["DAYS", "MONTHS"])
    frequency_value = serializers.IntegerField(min_value=1, max_value=3650)
    lead_days = serializers.IntegerField(min_value=0, max_value=365, required=False)
    priority = serializers.ChoiceField(choices=PRIORITIES, required=False)
    default_assignee = UserField(source="default_assignee_user", required=False, allow_null=True)
    notes = serializers.CharField(max_length=2000, required=False, allow_null=True)
    SCOPED = {"equipment": Equipment, "checklist_template": ChecklistTemplate}

    class Meta:
        model = MaintenancePlan
        fields = ["public_id", "name", "equipment", "checklist_template", "frequency_type", "frequency_value",
                  "lead_days", "priority", "default_assignee", "start_date", "last_performed_date",
                  "next_due_date", "notes", "is_active", "row_version", "created_at", "updated_at"]
        read_only_fields = ["public_id", "is_active", "row_version", "created_at", "updated_at"]
        extra_kwargs = {"start_date": {"required": False}, "next_due_date": {"required": False}}

    def validate(self, a):
        inst, fac = self.instance, _fac(self)
        if inst is not None and "equipment" in a and a["equipment"].pk != inst.equipment_id:
            raise serializers.ValidationError({"equipment": ["The equipment of a plan cannot be changed."]})
        user = a.get("default_assignee_user")
        if user is not None and fac is not None and not services.assignee_ok(fac.id, user.pk):
            raise serializers.ValidationError({"default_assignee": [
                "User must be an active member of this facility with permission to execute work orders."]})
        name = a["name"].strip() if "name" in a else (inst.name if inst else None)
        eq = a.get("equipment") or (None if inst is None else inst.equipment)
        if fac is not None and name and eq is not None:
            qs = MaintenancePlan.objects.filter(facility_id=fac.id, is_active=True, equipment_id=eq.pk, name__iexact=name)
            if inst:
                qs = qs.exclude(pk=inst.pk)
            if qs.exists():
                raise serializers.ValidationError({"name": ["This equipment already has an active plan with this name."]})
        if "name" in a:
            a["name"] = name
        if inst is None:   # create: derive the dates
            start = a.get("start_date") or (services.today_for(fac) if fac else None)
            a["start_date"] = start
            if "next_due_date" not in a or a["next_due_date"] is None:
                last = a.get("last_performed_date")
                a["next_due_date"] = services.add_interval(last, a["frequency_type"], a["frequency_value"]) \
                    if last else start
        return a

    def to_representation(self, o):
        data = super().to_representation(o)
        e = o.equipment
        data["equipment"] = {"public_id": str(e.public_id), "asset_tag": e.asset_tag, "name": e.name}
        data["checklist_template"] = ref(o.checklist_template, "name") if o.checklist_template_id else None
        data["default_assignee"] = user_ref(o.default_assignee_user) if o.default_assignee_user_id else None
        return data


class GeneratePlansSerializer(ScopedFieldsMixin, BlankToNullMixin, serializers.Serializer):
    name = serializers.CharField(max_length=200)
    equipment_model = PublicIdField(queryset=EquipmentModel.objects.none(), required=False, allow_null=True)
    category = PublicIdField(queryset=EquipmentCategory.objects.none(), required=False, allow_null=True)
    frequency_type = serializers.ChoiceField(choices=["DAYS", "MONTHS"], required=False, allow_null=True)
    frequency_value = serializers.IntegerField(min_value=1, max_value=3650, required=False, allow_null=True)
    checklist_template = PublicIdField(queryset=ChecklistTemplate.objects.none(), required=False, allow_null=True)
    lead_days = serializers.IntegerField(min_value=0, max_value=365, required=False, default=7)
    priority = serializers.ChoiceField(choices=PRIORITIES, required=False, default="MEDIUM")
    default_assignee = UserField(required=False, allow_null=True)
    last_performed_date = serializers.DateField(required=False, allow_null=True)
    start_date = serializers.DateField(required=False, allow_null=True)
    SCOPED = {"equipment_model": EquipmentModel, "category": EquipmentCategory, "checklist_template": ChecklistTemplate}


# ================================================================== work orders
def is_overdue(o, today):
    return bool(o.due_date and o.due_date < today and o.status not in services.DONE_STATUSES)


def available_actions(o, ctx):
    s, has = o.status, ctx.has
    acts = []
    if has("work_order.assign") and s in ("OPEN", "ASSIGNED"):
        acts.append("assign")
    if has("work_order.execute"):
        if s in ("OPEN", "ASSIGNED"):
            acts.append("start")
        if s == "IN_PROGRESS":
            acts += ["waiting_parts", "complete"]
        if s == "WAITING_PARTS":
            acts.append("resume")
        if s in ("IN_PROGRESS", "WAITING_PARTS"):
            acts.append("checklist")
        if s in ("IN_PROGRESS", "WAITING_PARTS", "COMPLETED"):
            acts.append("parts")
        acts.append("note")
    if has("work_order.close"):
        if s == "COMPLETED":
            acts.append("close")
        if s in ("OPEN", "ASSIGNED", "IN_PROGRESS", "WAITING_PARTS"):
            acts.append("cancel")
    if has("work_order.change") and s not in services.LOCKED_STATUSES:
        acts.append("edit")
    return acts


def hold_repr(h):
    return {"public_id": str(h.public_id), "hold_type": h.hold_type, "source_type": h.source_type,
            "reason": h.reason, "started_at": h.started_at, "released_at": h.released_at,
            "release_reason": h.release_reason,
            "work_order": ({"public_id": str(h.work_order.public_id), "wo_number": h.work_order.wo_number}
                           if h.work_order_id else None),
            "calibration_record": ({"public_id": str(h.calibration_record.public_id),
                                    "performed_date": h.calibration_record.performed_date,
                                    "result": h.calibration_record.result}
                                   if h.calibration_record_id else None)}

def _coverage_block(o, ctx, today):
    """Compliance data on a work order, each part only for users who may view it."""
    out = {"warranty": None, "amc_contract": None, "coverage_suggestion": None, "source_calibration_record": None}
    if ctx.has("warranty.view") and o.warranty_id:
        w = o.warranty
        out["warranty"] = {"public_id": str(w.public_id), "warranty_type": w.warranty_type,
                           "reference_number": w.reference_number, "start_date": w.start_date, "end_date": w.end_date}
    if ctx.has("amc.view") and o.amc_contract_id:
        c = o.amc_contract
        out["amc_contract"] = {"public_id": str(c.public_id), "contract_number": c.contract_number,
                               "contract_type": c.contract_type, "start_date": c.start_date, "end_date": c.end_date}
    if (ctx.has("warranty.view") or ctx.has("amc.view")) and o.work_order_type in ("BREAKDOWN", "CORRECTIVE") \
            and o.status not in services.LOCKED_STATUSES:
        from apps.compliance.services import suggest_coverage
        out["coverage_suggestion"] = suggest_coverage(o.equipment, today)
    if ctx.has("calibration.view") and o.source_calibration_record_id:
        r = o.source_calibration_record
        out["source_calibration_record"] = {
            "public_id": str(r.public_id), "performed_date": r.performed_date, "result": r.result,
            "certificate_number": r.certificate_number, "equipment_public_id": str(o.equipment.public_id)}
    return out

class WorkOrderListSerializer(serializers.BaseSerializer):
    def to_representation(self, o):
        today = services.today_for(self.context["request"].bems.facility)
        e = o.equipment
        return {
            "public_id": str(o.public_id), "wo_number": o.wo_number, "work_order_type": o.work_order_type,
            "priority": o.priority, "status": o.status,
            "equipment": {"public_id": str(e.public_id), "asset_tag": e.asset_tag, "name": e.name},
            "due_date": o.due_date, "reported_at": o.reported_at, "problem_description": o.problem_description,
            "equipment_unusable": o.equipment_unusable,
            "assigned_to": user_ref(o.assigned_to_user) if o.assigned_to_user_id else None,
            "is_overdue": is_overdue(o, today), "created_at": o.created_at, "row_version": o.row_version,
        }


class WorkOrderDetailSerializer(serializers.BaseSerializer):
    def to_representation(self, o):
        ctx = self.context["request"].bems
        today = services.today_for(ctx.facility)
        e = o.equipment
        items = WorkOrderChecklistItem.objects.filter(work_order_id=o.pk, is_active=True).order_by("sequence")
        ledger = SparePartStockEntry.objects.filter(work_order_id=o.pk, entry_type__in=["CONSUMPTION", "RETURN"])
        parts_cost = -sum((x.quantity * (x.unit_cost or ZERO) for x in ledger), ZERO)
        labour, vendor = o.labour_cost or ZERO, o.vendor_cost or ZERO
        names = _usernames([o.closed_by])
        hold_rows = EquipmentHold.objects.filter(work_order_id=o.pk).select_related(
            "work_order", "calibration_record").order_by("-started_at")
        standby = o.standby_equipment if o.standby_equipment_id else None
        return {
            "public_id": str(o.public_id), "wo_number": o.wo_number, "work_order_type": o.work_order_type,
            "priority": o.priority, "status": o.status, "status_note": o.status_note,
            "equipment": {"public_id": str(e.public_id), "asset_tag": e.asset_tag, "name": e.name,
                          "operational_state": e.operational_state, "lifecycle_stage": e.lifecycle_stage,
                          "current_location": ref(e.current_location, "code", "name")},
            "maintenance_plan": ref(o.maintenance_plan, "name") if o.maintenance_plan_id else None,
            "parent_work_order": ref(o.parent_work_order, "wo_number") if o.parent_work_order_id else None,
            "due_date": o.due_date, "is_overdue": is_overdue(o, today),
            "problem_description": o.problem_description, "reported_at": o.reported_at,
            "reported_by_name": o.reported_by_name,
            "reported_by_department": ref(o.reported_by_department, "code", "name") if o.reported_by_department_id else None,
            "equipment_unusable": o.equipment_unusable,
            "assigned_to": user_ref(o.assigned_to_user) if o.assigned_to_user_id else None,
            "assigned_at": o.assigned_at, "started_at": o.started_at, "completed_at": o.completed_at,
            "closed_at": o.closed_at, "closed_by": names.get(o.closed_by), "signoff_name": o.signoff_name,
            "root_cause": o.root_cause, "action_taken": o.action_taken, "cancel_reason": o.cancel_reason,
            "coverage_source": o.coverage_source,
            **_coverage_block(o, ctx, today),
            "service_provider_vendor": ref(o.service_provider_vendor, "name") if o.service_provider_vendor_id else None,
            "vendor_call_reference": o.vendor_call_reference, "vendor_engineer_name": o.vendor_engineer_name,
            "vendor_visit_at": o.vendor_visit_at,
            "standby_equipment": ({"public_id": str(standby.public_id), "asset_tag": standby.asset_tag,
                                   "name": standby.name} if standby else None),
            "downtime_start": o.downtime_start, "downtime_end": o.downtime_end,
            "labour_cost": o.labour_cost, "vendor_cost": o.vendor_cost,
            "parts_cost": parts_cost, "total_cost": labour + vendor + parts_cost,
            "checklist_items": [{
                "sequence": i.sequence, "item_text": i.item_text, "item_type": i.item_type, "unit": i.unit,
                "min_value": i.min_value, "max_value": i.max_value, "result": i.result,
                "measured_value": i.measured_value, "remarks": i.remarks} for i in items],
            "holds": [hold_repr(h) for h in hold_rows],
            "available_actions": available_actions(o, ctx),
            "row_version": o.row_version, "created_at": o.created_at, "updated_at": o.updated_at,
        }


class WorkOrderUpdateSerializer(ScopedFieldsMixin, BlankToNullMixin, serializers.ModelSerializer):
    priority = serializers.ChoiceField(choices=PRIORITIES, required=False)
    root_cause = serializers.CharField(max_length=4000, required=False, allow_null=True)
    action_taken = serializers.CharField(max_length=4000, required=False, allow_null=True)
    labour_cost = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False, allow_null=True)
    vendor_cost = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False, allow_null=True)
    coverage_source = serializers.ChoiceField(choices=COVERAGE, required=False, allow_null=True)
    warranty_id = PublicIdField(source="warranty", queryset=Warranty.objects.none(), required=False, allow_null=True)
    amc_contract_id = PublicIdField(source="amc_contract", queryset=AmcContract.objects.none(),
                                    required=False, allow_null=True)
    service_provider_vendor = PublicIdField(queryset=Vendor.objects.none(), required=False, allow_null=True)
    vendor_call_reference = serializers.CharField(max_length=200, required=False, allow_null=True)
    vendor_engineer_name = serializers.CharField(max_length=200, required=False, allow_null=True)
    vendor_visit_at = serializers.DateTimeField(required=False, allow_null=True)
    standby_equipment = PublicIdField(queryset=Equipment.objects.none(), required=False, allow_null=True)
    signoff_name = serializers.CharField(max_length=200, required=False, allow_null=True)
    downtime_start = serializers.DateTimeField(required=False, allow_null=True)
    downtime_end = serializers.DateTimeField(required=False, allow_null=True)
    SCOPED = {"service_provider_vendor": Vendor, "standby_equipment": Equipment,
              "warranty_id": Warranty, "amc_contract_id": AmcContract}

    class Meta:
        model = WorkOrder
        fields = ["priority", "root_cause", "action_taken", "labour_cost", "vendor_cost", "coverage_source",
                  "warranty_id", "amc_contract_id",
                  "service_provider_vendor", "vendor_call_reference", "vendor_engineer_name", "vendor_visit_at",
                  "standby_equipment", "signoff_name", "downtime_start", "downtime_end"]

    def validate(self, a):
        inst = self.instance
        se = a.get("standby_equipment")
        if se is not None:
            if se.pk == inst.equipment_id:
                raise serializers.ValidationError({"standby_equipment": ["Standby must be a different equipment."]})
            if se.lifecycle_stage != "COMMISSIONED":
                raise serializers.ValidationError({"standby_equipment": ["Standby equipment must be commissioned."]})
        # coverage links: changing the source clears a link that no longer fits; a new link sets the source
        src_in = "coverage_source" in a
        src = a["coverage_source"] if src_in else inst.coverage_source
        if src_in and src != "WARRANTY" and "warranty" not in a:
            a["warranty"] = None
        if src_in and src != "AMC" and "amc_contract" not in a:
            a["amc_contract"] = None
        if a.get("warranty") is not None and "amc_contract" not in a:
            a["amc_contract"] = None
        if a.get("amc_contract") is not None and "warranty" not in a:
            a["warranty"] = None
        new_w, new_c = a.get("warranty"), a.get("amc_contract")
        if new_w is not None or new_c is not None:
            from apps.compliance.services import resolve_coverage_links
            src, _, _ = resolve_coverage_links(
                facility=_fac(self), equipment=inst.equipment, coverage_source=a.get("coverage_source") if src_in else None,
                warranty=new_w, amc_contract=new_c)
            a["coverage_source"] = src
        start = a["downtime_start"] if "downtime_start" in a else inst.downtime_start
        end = a["downtime_end"] if "downtime_end" in a else inst.downtime_end
        if start and end and end < start:
            raise serializers.ValidationError({"downtime_end": ["Cannot be before the downtime start."]})
        return a

    def to_representation(self, o):
        return WorkOrderDetailSerializer(o, context=self.context).data


class WorkOrderCreateSerializer(ScopedFieldsMixin, BlankToNullMixin, serializers.Serializer):
    work_order_type = serializers.ChoiceField(choices=["CORRECTIVE", "PREVENTIVE"])
    equipment = PublicIdField(queryset=Equipment.objects.none())
    priority = serializers.ChoiceField(choices=PRIORITIES, required=False, default="MEDIUM")
    coverage_source = serializers.ChoiceField(choices=COVERAGE, required=False, allow_null=True)
    due_date = serializers.DateField(required=False, allow_null=True)
    problem_description = serializers.CharField(max_length=4000, required=False, allow_null=True)
    parent_work_order = PublicIdField(queryset=WorkOrder.objects.none(), required=False, allow_null=True)
    checklist_template = PublicIdField(queryset=ChecklistTemplate.objects.none(), required=False, allow_null=True)
    assigned_to = UserField(required=False, allow_null=True)
    SCOPED = {"equipment": Equipment, "parent_work_order": WorkOrder, "checklist_template": ChecklistTemplate}

class BreakdownSerializer(ScopedFieldsMixin, BlankToNullMixin, serializers.Serializer):
    equipment = PublicIdField(queryset=Equipment.objects.none())
    problem_description = serializers.CharField(max_length=4000)
    priority = serializers.ChoiceField(choices=PRIORITIES, required=False, default="MEDIUM")
    coverage_source = serializers.ChoiceField(choices=COVERAGE, required=False, allow_null=True)
    reported_by_name = serializers.CharField(max_length=200, required=False, allow_null=True)
    reported_by_department = PublicIdField(queryset=Department.objects.none(), required=False, allow_null=True)
    reported_at = serializers.DateTimeField(required=False, allow_null=True)
    equipment_unusable = serializers.BooleanField(required=False, default=False)
    SCOPED = {"equipment": Equipment, "reported_by_department": Department}

class EmptySerializer(serializers.Serializer):
    pass


class AssignSerializer(BlankToNullMixin, serializers.Serializer):
    assigned_to = UserField()
    note = serializers.CharField(max_length=1000, required=False, allow_null=True)


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000)


class CompleteSerializer(BlankToNullMixin, serializers.Serializer):
    action_taken = serializers.CharField(max_length=4000, required=False, allow_null=True)
    root_cause = serializers.CharField(max_length=4000, required=False, allow_null=True)
    labour_cost = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False, allow_null=True)
    vendor_cost = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False, allow_null=True)
    downtime_end = serializers.DateTimeField(required=False, allow_null=True)


class CloseSerializer(serializers.Serializer):
    signoff_name = serializers.CharField(max_length=200)


class CancelSerializer(BlankToNullMixin, serializers.Serializer):
    reason = serializers.CharField(max_length=1000)
    next_due_date = serializers.DateField(required=False, allow_null=True)


class NoteSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=2000)


class ChecklistResultSerializer(BlankToNullMixin, serializers.Serializer):
    sequence = serializers.IntegerField(min_value=1)
    result = serializers.ChoiceField(choices=["PASS", "FAIL", "NA"], required=False, allow_null=True)
    measured_value = serializers.DecimalField(max_digits=14, decimal_places=4, required=False, allow_null=True)
    remarks = serializers.CharField(max_length=1000, required=False, allow_null=True)


class ChecklistSaveSerializer(serializers.Serializer):
    items = ChecklistResultSerializer(many=True, max_length=200)


class IssuePartSerializer(ScopedFieldsMixin, BlankToNullMixin, serializers.Serializer):
    spare_part = PublicIdField(queryset=SparePart.objects.none())
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"))
    unit_cost = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False, allow_null=True)
    SCOPED = {"spare_part": SparePart}


class ReturnPartSerializer(serializers.Serializer):
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"), required=False)


def entry_repr(x, names=None, returnable=None):
    out = {"public_id": str(x.public_id), "entry_type": x.entry_type, "quantity": x.quantity,
           "unit_cost": x.unit_cost, "reference_note": x.reference_note, "reason": x.reason,
           "created_at": x.created_at, "created_by": (names or {}).get(x.created_by),
           "spare_part": {"public_id": str(x.spare_part.public_id), "part_code": x.spare_part.part_code,
                          "name": x.spare_part.name, "unit": x.spare_part.unit}}
    if returnable is not None:
        out["returnable"] = returnable
    return out


# ================================================================== spare parts
class SparePartSerializer(BlankToNullMixin, serializers.ModelSerializer):
    part_code = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=200)
    description = serializers.CharField(max_length=2000, required=False, allow_null=True)
    unit = serializers.CharField(max_length=20, required=False)
    reorder_level = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=0, required=False)
    standard_unit_cost = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0,
                                                  required=False, allow_null=True)

    class Meta:
        model = SparePart
        fields = ["public_id", "part_code", "name", "description", "unit", "reorder_level", "standard_unit_cost",
                  "is_active", "row_version", "created_at", "updated_at"]
        read_only_fields = ["public_id", "is_active", "row_version", "created_at", "updated_at"]

    def validate_part_code(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("This field may not be blank.")
        fac = _fac(self)
        if fac is not None:
            qs = SparePart.objects.filter(facility_id=fac.id, is_active=True, part_code__iexact=value)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError("This part code is already in use.")
        return value

    def to_representation(self, o):
        from . import stock
        data = super().to_representation(o)
        on_hand = getattr(o, "on_hand_quantity", None)
        if on_hand is None:
            on_hand = stock.on_hand(o)
        data["on_hand_quantity"] = on_hand
        data["is_low_stock"] = on_hand <= o.reorder_level
        cats = SparePartCategory.objects.filter(spare_part_id=o.pk).select_related("category")
        data["categories"] = [ref(c.category, "code", "name") for c in cats]
        return data


class SparePartCategoriesSerializer(serializers.Serializer):
    categories = serializers.ListField(child=serializers.UUIDField(), max_length=200)


class StockSerializer(ScopedFieldsMixin, BlankToNullMixin, serializers.Serializer):
    entry_type = serializers.ChoiceField(choices=["RECEIPT", "ADJUSTMENT"])
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False, allow_null=True)
    supplier_vendor = PublicIdField(queryset=Vendor.objects.none(), required=False, allow_null=True)
    reference_note = serializers.CharField(max_length=500, required=False, allow_null=True)
    reason = serializers.CharField(max_length=500, required=False, allow_null=True)
    SCOPED = {"supplier_vendor": Vendor}

    def validate(self, a):
        if a["quantity"] == 0:
            raise serializers.ValidationError({"quantity": ["Must not be zero."]})
        if a["entry_type"] == "RECEIPT" and a["quantity"] < 0:
            raise serializers.ValidationError({"quantity": ["A receipt must be a positive quantity."]})
        if a["entry_type"] == "ADJUSTMENT" and not (a.get("reason") or "").strip():
            raise serializers.ValidationError({"reason": ["A reason is required for an adjustment."]})
        return a
