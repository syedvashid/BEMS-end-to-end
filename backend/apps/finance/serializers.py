import re
from datetime import date

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from apps.compliance.serializers import PublicRef, StrictSerializer
from apps.equipment.models import Equipment
from apps.foundation.serializers import BlankToNullMixin
from apps.masters.models import EquipmentCategory, Vendor
from apps.safety.models import PhysicalVerificationItem

from . import lifecycle
from . import services as fin
from .models import DepreciationPolicy, DepreciationRun, Disposal, ReplacementPlan

READ_ONLY = ["public_id", "is_active", "row_version", "created_at", "updated_at"]
REASONS = ["UNECONOMICAL_TO_REPAIR", "BEYOND_ECONOMIC_LIFE", "OBSOLETE", "UNSAFE", "DAMAGED_BEYOND_REPAIR",
           "LOST_MISSING", "OTHER"]
METHODS = ["SOLD", "SCRAPPED_E_WASTE", "DONATED", "RETURNED_TO_VENDOR", "TRADE_IN", "AUCTIONED", "LOST_MISSING"]
OPEN_PLAN = ("CANDIDATE", "APPROVED_FOR_BUDGET", "DEFERRED")


def _fac(s):
    return s.context["request"].bems.facility


class MonthField(serializers.Field):
    """'YYYY-MM' -> first day of that month."""
    default_error_messages = {"invalid": "Use the format YYYY-MM."}

    def to_internal_value(self, data):
        m = re.fullmatch(r"(\d{4})-(0[1-9]|1[0-2])", str(data or ""))
        if not m:
            self.fail("invalid")
        return date(int(m.group(1)), int(m.group(2)), 1)

    def to_representation(self, value):
        return value.strftime("%Y-%m")


# ------------------------------------------------------------------ settings and policies
class FinanceSettingsSerializer(StrictSerializer):
    maintenance_cost_threshold_percent = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=0.01,
                                                                  required=False)
    committee_required_above_book_value = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0,
                                                                   required=False, allow_null=True)
    row_version = serializers.IntegerField(min_value=1, required=False)


def settings_repr(s):
    return {"maintenance_cost_threshold_percent": s.maintenance_cost_threshold_percent,
            "committee_required_above_book_value": s.committee_required_above_book_value,
            "row_version": s.row_version, "is_default": s.public_id is None}


class DepreciationPolicySerializer(BlankToNullMixin, serializers.ModelSerializer):
    public_id = serializers.UUIDField(read_only=True)
    category = PublicRef(EquipmentCategory, required=False, allow_null=True)
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    equipment = PublicRef(Equipment, required=False, allow_null=True)
    equipment_asset_tag = serializers.CharField(source="equipment.asset_tag", read_only=True, default=None)
    scope = serializers.SerializerMethodField()
    method = serializers.ChoiceField(choices=["STRAIGHT_LINE", "WRITTEN_DOWN_VALUE"])
    useful_life_years = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0.01, required=False,
                                                 allow_null=True)
    rate_percent = serializers.DecimalField(max_digits=6, decimal_places=3, min_value=0.001, max_value=100,
                                            required=False, allow_null=True)
    salvage_percent = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100,
                                               required=False)
    start_rule = serializers.ChoiceField(choices=["COMMISSIONING_DATE", "INVOICE_DATE"], required=False)

    class Meta:
        model = DepreciationPolicy
        fields = ["public_id", "scope", "category", "category_name", "equipment", "equipment_asset_tag", "method",
                  "useful_life_years", "rate_percent", "salvage_percent", "start_rule", "notes", "is_active",
                  "row_version", "created_at", "updated_at"]
        read_only_fields = READ_ONLY

    def get_scope(self, o):
        return "EQUIPMENT" if o.equipment_id else "CATEGORY"

    def validate(self, attrs):
        inst, fac = self.instance, _fac(self)
        if inst is not None:
            for k in ("category", "equipment"):
                if k in attrs and (attrs[k].pk if attrs[k] else None) != getattr(inst, f"{k}_id"):
                    raise ValidationError({k: ["Cannot be changed."]})
            category, equipment = inst.category, inst.equipment
        else:
            category, equipment = attrs.get("category"), attrs.get("equipment")
            if (category is None) == (equipment is None):
                raise ValidationError({"category": ["Give exactly one of category or equipment."]})

        def eff(name):
            return attrs[name] if name in attrs else getattr(inst, name, None)

        method = eff("method")
        if method == "STRAIGHT_LINE":
            if eff("useful_life_years") is None:
                raise ValidationError({"useful_life_years": ["Required for the straight-line method."]})
            attrs["rate_percent"] = None
        else:
            if eff("rate_percent") is None:
                raise ValidationError({"rate_percent": ["Required for the written-down-value method."]})
            attrs["useful_life_years"] = None
        qs = DepreciationPolicy.objects.filter(facility_id=fac.id, is_active=True)
        if inst is not None:
            qs = qs.exclude(pk=inst.pk)
        if category is not None and qs.filter(category_id=category.pk).exists():
            raise ValidationError({"category": ["This category already has a depreciation policy."]})
        if equipment is not None and qs.filter(equipment_id=equipment.pk).exists():
            raise ValidationError({"equipment": ["This equipment already has a depreciation policy."]})
        return attrs


class DepreciationRunSerializer(serializers.ModelSerializer):
    public_id = serializers.UUIDField(read_only=True)
    run_period = serializers.SerializerMethodField()

    class Meta:
        model = DepreciationRun
        fields = ["public_id", "run_period", "status", "started_at", "finished_at", "assets_processed",
                  "entries_created", "skipped_no_policy", "skipped_no_cost", "skipped_no_start_date",
                  "total_charge", "triggered_by_system", "error_message", "created_at"]
        read_only_fields = fields

    def get_run_period(self, o):
        return o.run_period.strftime("%Y-%m")


class RunSerializer(StrictSerializer):
    month = MonthField(required=False, allow_null=True)


class TcoGenerateSerializer(StrictSerializer):
    as_of = serializers.DateField(required=False, allow_null=True)


class OpeningBookValueSerializer(StrictSerializer):
    as_of_month = MonthField()
    book_value = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)


# ------------------------------------------------------------------ replacement plans
class ReplacementPlanSerializer(BlankToNullMixin, serializers.ModelSerializer):
    public_id = serializers.UUIDField(read_only=True)
    equipment = PublicRef(Equipment)
    equipment_asset_tag = serializers.CharField(source="equipment.asset_tag", read_only=True)
    equipment_name = serializers.CharField(source="equipment.name", read_only=True)
    replaced_by_equipment = PublicRef(Equipment, required=False, allow_null=True)
    replaced_by_asset_tag = serializers.CharField(source="replaced_by_equipment.asset_tag", read_only=True,
                                                  default=None)
    planned_year = serializers.IntegerField(min_value=2000, max_value=2200)
    estimated_cost = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False,
                                              allow_null=True)
    priority = serializers.ChoiceField(choices=["LOW", "MEDIUM", "HIGH", "CRITICAL"], required=False)
    status = serializers.ChoiceField(
        choices=["CANDIDATE", "APPROVED_FOR_BUDGET", "DEFERRED", "COMPLETED", "CANCELLED"], required=False)

    class Meta:
        model = ReplacementPlan
        fields = ["public_id", "equipment", "equipment_asset_tag", "equipment_name", "planned_year",
                  "estimated_cost", "priority", "status", "justification", "replaced_by_equipment",
                  "replaced_by_asset_tag", "notes", "is_active", "row_version", "created_at", "updated_at"]
        read_only_fields = READ_ONLY

    def validate(self, attrs):
        inst, fac = self.instance, _fac(self)
        if inst is not None:
            if "equipment" in attrs and attrs["equipment"].pk != inst.equipment_id:
                raise ValidationError({"equipment": ["Cannot be changed."]})
            equipment = inst.equipment
        else:
            equipment = attrs["equipment"]
            if equipment.lifecycle_stage == "DISPOSED":
                raise ValidationError({"equipment": ["Disposed equipment cannot be planned for replacement."]})
        status = attrs.get("status", inst.status if inst else "CANDIDATE")
        repl = attrs.get("replaced_by_equipment", inst.replaced_by_equipment if inst else None)
        if repl is not None and repl.pk == equipment.pk:
            raise ValidationError({"replaced_by_equipment": ["Cannot be the same equipment."]})
        if status in OPEN_PLAN:
            qs = ReplacementPlan.objects.filter(facility_id=fac.id, equipment_id=equipment.pk, is_active=True,
                                                status__in=OPEN_PLAN)
            if inst is not None:
                qs = qs.exclude(pk=inst.pk)
            if qs.exists():
                raise ValidationError({"equipment": ["This equipment already has an open replacement plan."]})
        return attrs


# ------------------------------------------------------------------ condemnation (inputs)
class _In(BlankToNullMixin, StrictSerializer):
    row_version = serializers.IntegerField(min_value=1, required=False)


class CondemnationCreateSerializer(_In):
    equipment = PublicRef(Equipment)
    reason_category = serializers.ChoiceField(choices=REASONS)
    justification = serializers.CharField(max_length=4000)
    technical_assessment = serializers.CharField(max_length=4000, required=False, allow_null=True)
    technical_assessment_by_name = serializers.CharField(max_length=200, required=False, allow_null=True)
    source_verification_item = PublicRef(PhysicalVerificationItem, required=False, allow_null=True)


class CondemnationUpdateSerializer(_In):
    justification = serializers.CharField(max_length=4000, required=False)
    technical_assessment = serializers.CharField(max_length=4000, required=False, allow_null=True)
    technical_assessment_by_name = serializers.CharField(max_length=200, required=False, allow_null=True)


class ApproveSerializer(_In):
    committee_reference = serializers.CharField(max_length=200, required=False, allow_null=True)
    committee_decision_date = serializers.DateField(required=False, allow_null=True)
    note = serializers.CharField(max_length=2000, required=False, allow_null=True)


class NoteRequiredSerializer(_In):
    note = serializers.CharField(max_length=2000)


class ReasonSerializer(_In):
    reason = serializers.CharField(max_length=2000)


# ------------------------------------------------------------------ disposal (inputs)
class _DisposalFields(_In):
    disposal_method = serializers.ChoiceField(choices=METHODS)
    disposal_date = serializers.DateField(required=False, allow_null=True)
    recipient_name = serializers.CharField(max_length=300, required=False, allow_null=True)
    recipient_vendor = PublicRef(Vendor, required=False, allow_null=True)
    proceeds_amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False)
    decontamination_done = serializers.BooleanField(required=False)
    decontamination_notes = serializers.CharField(max_length=2000, required=False, allow_null=True)
    data_wipe_required = serializers.BooleanField(required=False)
    data_wipe_done = serializers.BooleanField(required=False)
    recycler_name = serializers.CharField(max_length=300, required=False, allow_null=True)
    ewaste_certificate_number = serializers.CharField(max_length=200, required=False, allow_null=True)
    notes = serializers.CharField(max_length=2000, required=False, allow_null=True)


class DisposalCreateSerializer(_DisposalFields):
    pass


class DisposalUpdateSerializer(_DisposalFields):
    row_version = serializers.IntegerField(min_value=1)


# ------------------------------------------------------------------ representations
def _eq(o):
    return {"public_id": str(o.public_id), "asset_tag": o.asset_tag, "name": o.name,
            "lifecycle_stage": o.lifecycle_stage, "ownership_type": o.ownership_type}


def _plain_disposal(d):
    return {"public_id": str(d.public_id), "disposal_number": d.disposal_number, "status": d.status,
            "disposal_method": d.disposal_method}


def condemnation_repr(o, names, detail=False, request=None):
    out = {
        "public_id": str(o.public_id), "request_number": o.request_number, "equipment": _eq(o.equipment),
        "reason_category": o.reason_category, "status": o.status, "book_value_at_request": o.book_value_at_request,
        "requested_by": names.get(o.created_by), "created_at": o.created_at, "decided_at": o.decided_at,
        "committee_reference": o.committee_reference, "row_version": o.row_version, "revoked": o.revoked,
    }
    if not detail:
        return out
    blockers = lifecycle.condemnation_blockers(o.equipment, ignore_request_pk=o.pk) if o.status == "REQUESTED" else []
    disposal = Disposal.objects.filter(facility_id=o.facility_id, condemnation_request_id=o.pk, is_active=True) \
        .order_by("-id").first()
    timeline = [{"event": "REQUESTED", "at": o.created_at, "by": names.get(o.created_by)}]
    if o.decided_at:
        timeline.append({"event": "APPROVED" if o.status in ("APPROVED", "COMPLETED") or o.revoked else "REJECTED",
                         "at": o.decided_at, "by": names.get(o.decided_by), "note": o.decision_note})
    if o.status == "CANCELLED":
        timeline.append({"event": "REVOKED" if o.revoked else "CANCELLED", "at": o.updated_at, "note": o.cancel_reason})
    if o.completed_at:
        timeline.append({"event": "COMPLETED", "at": o.completed_at})
    out.update({
        "justification": o.justification, "technical_assessment": o.technical_assessment,
        "technical_assessment_by_name": o.technical_assessment_by_name,
        "committee_decision_date": o.committee_decision_date, "decision_note": o.decision_note,
        "decided_by": names.get(o.decided_by), "cancel_reason": o.cancel_reason, "completed_at": o.completed_at,
        "source_verification_item": (str(o.source_verification_item.public_id)
                                     if o.source_verification_item_id else None),
        "current_book_value": fin.current_book_value(o.equipment), "blockers": blockers, "timeline": timeline,
        "disposal": _plain_disposal(disposal) if disposal else None,
        "can_approve": bool(request and o.status == "REQUESTED" and o.created_by != request.user.id
                            and request.bems.has("condemnation.approve")),
    })
    return out


def disposal_repr(d, names, request_number=None):
    return {
        "public_id": str(d.public_id), "disposal_number": d.disposal_number, "status": d.status,
        "equipment": _eq(d.equipment), "condemnation_request": str(d.condemnation_request.public_id),
        "request_number": request_number or d.condemnation_request.request_number,
        "disposal_method": d.disposal_method, "disposal_date": d.disposal_date, "recipient_name": d.recipient_name,
        "recipient_vendor": str(d.recipient_vendor.public_id) if d.recipient_vendor_id else None,
        "recipient_vendor_name": d.recipient_vendor.name if d.recipient_vendor_id else None,
        "proceeds_amount": d.proceeds_amount, "decontamination_done": d.decontamination_done,
        "decontamination_notes": d.decontamination_notes, "data_wipe_required": d.data_wipe_required,
        "data_wipe_done": d.data_wipe_done, "recycler_name": d.recycler_name,
        "ewaste_certificate_number": d.ewaste_certificate_number,
        "book_value_at_disposal": d.book_value_at_disposal, "gain_loss": d.gain_loss,
        "completed_at": d.completed_at, "completed_by": names.get(d.completed_by), "cancel_reason": d.cancel_reason,
        "notes": d.notes, "created_at": d.created_at, "row_version": d.row_version,
    }


def snapshot_repr(s):
    return {"public_id": str(s.public_id), "as_of_date": s.as_of_date, "acquisition_cost": s.acquisition_cost,
            "installation_cost": s.installation_cost, "labour_cost": s.labour_cost, "vendor_cost": s.vendor_cost,
            "parts_cost": s.parts_cost, "amc_cost": s.amc_cost, "salvage_value": s.salvage_value,
            "total_cost_of_ownership": s.total_cost_of_ownership, "maintenance_cost": s.maintenance_cost,
            "maintenance_cost_ratio_percent": s.maintenance_cost_ratio_percent, "age_years": s.age_years,
            "expected_life_years": s.expected_life_years, "usage_hours": s.usage_hours,
            "session_count": s.session_count, "cost_per_hour": s.cost_per_hour, "cost_per_use": s.cost_per_use,
            "threshold_percent": s.threshold_percent, "replacement_indicator": s.replacement_indicator}


def entry_repr(e):
    return {"public_id": str(e.public_id), "period_month": e.period_month.strftime("%Y-%m"),
            "entry_type": e.entry_type, "opening_value": e.opening_value, "charge": e.charge,
            "closing_value": e.closing_value, "method": e.method, "days_charged": e.days_charged}
