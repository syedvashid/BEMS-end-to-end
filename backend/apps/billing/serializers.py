from datetime import timedelta

from django.db.models import Q
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from apps.compliance.serializers import PublicRef, StrictSerializer
from apps.core.errors import Conflict
from apps.equipment.models import Equipment
from apps.foundation.serializers import BlankToNullMixin
from apps.masters.models import EquipmentCategory

from . import engine
from .models import ChargeItem, ChargeMapping

READ_ONLY = ["public_id", "is_active", "row_version", "created_at", "updated_at"]
MONEY = dict(max_digits=14, decimal_places=2)

# Which mapping fields matter for which rule; the others are reset to their defaults so stored data stays tidy.
RELEVANT = {
    "HOURLY": {"rate_override", "minimum_billable_minutes", "grace_minutes", "rounding", "daily_cap_amount"},
    "DAILY": {"rate_override", "grace_minutes", "day_block_mode"},
    "PER_USE": {"rate_override"}, "PER_SESSION": {"rate_override"}, "PER_ADMISSION": {"rate_override"},
    "BUNDLED": {"bundle_reference"}, "DISABLED": set(),
}
DEFAULTS = {"rate_override": None, "minimum_billable_minutes": 0, "grace_minutes": 0, "rounding": "UP",
            "daily_cap_amount": None, "day_block_mode": "CALENDAR_DAY", "bundle_reference": None}


# ================================================================== charge items
class ChargeItemSerializer(BlankToNullMixin, serializers.ModelSerializer):
    item_code = serializers.RegexField(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,49}$", max_length=50)
    name = serializers.CharField(max_length=200)
    unit_label = serializers.CharField(max_length=30)
    default_rate = serializers.DecimalField(min_value=0, **MONEY)
    description = serializers.CharField(max_length=500, required=False, allow_null=True)

    class Meta:
        model = ChargeItem
        fields = ["public_id", "item_code", "name", "unit_label", "default_rate", "description",
                  "is_active", "row_version", "created_at", "updated_at"]
        read_only_fields = READ_ONLY

    def validate_item_code(self, value):
        qs = ChargeItem.objects.filter(facility_id=self.context["request"].bems.facility.id, is_active=True,
                                       item_code__iexact=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This code is already in use.")
        return value


# ================================================================== charge mappings
class ChargeMappingSerializer(BlankToNullMixin, serializers.ModelSerializer):
    equipment = PublicRef(Equipment, required=False, allow_null=True)
    category = PublicRef(EquipmentCategory, required=False, allow_null=True)
    charge_item = PublicRef(ChargeItem)
    billing_rule = serializers.ChoiceField(choices=engine.RULES)
    basis = serializers.ChoiceField(choices=engine.BASES, required=False)
    rate_override = serializers.DecimalField(min_value=0, required=False, allow_null=True, **MONEY)
    minimum_billable_minutes = serializers.IntegerField(min_value=0, max_value=100000, required=False)
    grace_minutes = serializers.IntegerField(min_value=0, max_value=100000, required=False)
    rounding = serializers.ChoiceField(choices=engine.ROUNDINGS, required=False)
    daily_cap_amount = serializers.DecimalField(min_value=0.01, required=False, allow_null=True, **MONEY)
    day_block_mode = serializers.ChoiceField(choices=engine.DAY_MODES, required=False)
    bundle_reference = serializers.CharField(max_length=100, required=False, allow_null=True)
    effective_from = serializers.DateField()
    effective_to = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(max_length=500, required=False, allow_null=True)
    equipment_label = serializers.SerializerMethodField()
    category_name = serializers.CharField(source="category.name", read_only=True, allow_null=True)
    charge_item_code = serializers.CharField(source="charge_item.item_code", read_only=True)
    charge_item_name = serializers.CharField(source="charge_item.name", read_only=True)
    charge_item_rate = serializers.DecimalField(source="charge_item.default_rate", read_only=True, **MONEY)
    charge_item_unit = serializers.CharField(source="charge_item.unit_label", read_only=True)

    class Meta:
        model = ChargeMapping
        fields = ["public_id", "equipment", "category", "charge_item", "billing_rule", "basis", "rate_override",
                  "minimum_billable_minutes", "grace_minutes", "rounding", "daily_cap_amount", "day_block_mode",
                  "bundle_reference", "effective_from", "effective_to", "notes", "equipment_label", "category_name",
                  "charge_item_code", "charge_item_name", "charge_item_rate", "charge_item_unit",
                  "is_active", "row_version", "created_at", "updated_at"]
        read_only_fields = READ_ONLY

    def get_equipment_label(self, obj):
        return f"{obj.equipment.asset_tag} - {obj.equipment.name}" if obj.equipment_id else None

    def _val(self, attrs, name, default=None):
        if name in attrs:
            return attrs[name]
        return getattr(self.instance, name) if self.instance is not None else default

    def validate(self, attrs):
        # scope: exactly one of equipment / category (a changed scope clears the other one on update)
        if attrs.get("equipment") is not None and "category" not in attrs:
            attrs["category"] = None
        if attrs.get("category") is not None and "equipment" not in attrs:
            attrs["equipment"] = None
        equipment, category = self._val(attrs, "equipment"), self._val(attrs, "category")
        if (equipment is None) == (category is None):
            raise ValidationError({"non_field_errors": ["Choose either one piece of equipment or one equipment category."]})
        rule = self._val(attrs, "billing_rule")
        basis = attrs.get("basis") or (self.instance.basis if self.instance is not None else engine.ALLOWED_BASES[rule][0])
        if "billing_rule" in attrs and "basis" not in attrs and basis not in engine.ALLOWED_BASES[rule]:
            basis = engine.ALLOWED_BASES[rule][0]
        if basis not in engine.ALLOWED_BASES[rule]:
            raise ValidationError({"basis": [f"{rule} can be charged from: {', '.join(engine.ALLOWED_BASES[rule])}."]})
        attrs["basis"] = basis
        for field, default in DEFAULTS.items():
            if field not in RELEVANT[rule]:
                attrs[field] = default
        if rule == "BUNDLED" and not (self._val(attrs, "bundle_reference") or "").strip():
            raise ValidationError({"bundle_reference": ["A package reference is required for a bundled mapping."]})
        frm, to = self._val(attrs, "effective_from"), self._val(attrs, "effective_to")
        if to is not None and to < frm:
            raise ValidationError({"effective_to": ["Must not be before the start date."]})
        self._check_overlap(equipment, category, frm, to)
        return attrs

    def _check_overlap(self, equipment, category, frm, to):
        qs = ChargeMapping.objects.filter(facility_id=self.context["request"].bems.facility.id,
                                          is_active=True).select_related("charge_item")
        qs = qs.filter(equipment_id=equipment.pk) if equipment is not None else qs.filter(category_id=category.pk)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if to is not None:
            qs = qs.filter(effective_from__lte=to)
        other = qs.filter(Q(effective_to__isnull=True) | Q(effective_to__gte=frm)).order_by("effective_from").first()
        if other is not None:
            what = "equipment" if equipment is not None else "category"
            raise Conflict(
                f"These dates overlap another mapping of the same {what} ({other.charge_item.item_code}, "
                f"{other.billing_rule}, from {other.effective_from.isoformat()} to "
                f"{other.effective_to.isoformat() if other.effective_to else 'no end date'}).")


# ================================================================== charge records (read side)
def _ref(o, *fields):
    return None if o is None else {"public_id": str(o.public_id), **{f: getattr(o, f) for f in fields}}


def record_repr(r, names, detail=False):
    out = {
        "public_id": str(r.public_id), "record_number": r.record_number, "record_type": r.record_type,
        "status": r.status, "source_type": r.source_type,
        "allocation": str(r.allocation.public_id) if r.allocation_id else None,
        "usage_log": str(r.usage_log.public_id) if r.usage_log_id else None,
        "equipment": _ref(r.equipment, "asset_tag", "name"),
        "charge_item": _ref(r.charge_item, "item_code", "name"),
        "charge_mapping": str(r.charge_mapping.public_id),
        "billing_rule": r.billing_rule, "basis": r.basis, "unit_label": r.unit_label, "unit_rate": r.unit_rate,
        "quantity": r.quantity, "amount": r.amount, "period_key": r.period_key,
        "period_start": r.period_start, "period_end": r.period_end, "charge_date": r.charge_date,
        "patient_reference": r.patient_reference, "encounter_reference": r.encounter_reference,
        "department": _ref(r.department, "name"),
        "approved_by": names.get(r.approved_by) or ("system" if r.approved_at else None),
        "approved_at": r.approved_at, "cancelled_by": names.get(r.cancelled_by), "cancelled_at": r.cancelled_at,
        "cancel_reason": r.cancel_reason, "reversal_reason": r.reversal_reason,
        "reverses_record": _ref(r.reverses_record, "record_number"),
        "corrects_record": _ref(r.corrects_record, "record_number"),
        "exported_at": r.exported_at, "exported_by": names.get(r.exported_by), "export_reference": r.export_reference,
        "created_at": r.created_at, "created_by": names.get(r.created_by),
    }
    if detail:
        out["calculation"] = r.calculation
    return out


# ================================================================== action bodies
class ReasonSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=500)


class BulkIdsSerializer(StrictSerializer):
    ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False, max_length=200)


class MarkExportedSerializer(StrictSerializer):
    ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False, max_length=5000, required=False)
    filters = serializers.DictField(child=serializers.CharField(allow_blank=True, max_length=100), required=False)
    export_reference = serializers.CharField(max_length=100)

    def validate(self, attrs):
        if ("ids" in attrs) == ("filters" in attrs):
            raise ValidationError({"non_field_errors": ["Send either ids or filters."]})
        return attrs


class SettingsSerializer(StrictSerializer):
    auto_approve = serializers.BooleanField()


class CalculatorSerializer(StrictSerializer):
    billing_rule = serializers.ChoiceField(choices=engine.RULES)
    unit_rate = serializers.DecimalField(min_value=0, **MONEY)
    unit_label = serializers.CharField(max_length=30, required=False)
    grace_minutes = serializers.IntegerField(min_value=0, max_value=100000, default=0)
    minimum_billable_minutes = serializers.IntegerField(min_value=0, max_value=100000, default=0)
    rounding = serializers.ChoiceField(choices=engine.ROUNDINGS, default="UP")
    daily_cap_amount = serializers.DecimalField(min_value=0.01, required=False, allow_null=True, **MONEY)
    day_block_mode = serializers.ChoiceField(choices=engine.DAY_MODES, default="CALENDAR_DAY")
    bundle_reference = serializers.CharField(max_length=100, required=False, allow_null=True)
    start = serializers.DateTimeField(required=False, allow_null=True)
    end = serializers.DateTimeField(required=False, allow_null=True)
    duration_minutes = serializers.IntegerField(min_value=0, max_value=525600, required=False, allow_null=True)

    def validate(self, attrs):
        start, end, dur = attrs.get("start"), attrs.get("end"), attrs.get("duration_minutes")
        if start and end:
            if end < start:
                raise ValidationError({"end": ["Must not be before the start."]})
            if end - start > timedelta(days=366):
                raise ValidationError({"end": ["At most one year."]})
        elif dur is None:
            raise ValidationError({"non_field_errors": ["Enter a start and end, or a duration in minutes."]})
        return attrs
