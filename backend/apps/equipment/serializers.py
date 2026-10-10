import math
import re

from rest_framework import serializers

from apps.foundation.models import User
from apps.foundation.serializers import BlankToNullMixin, PublicIdField
from apps.masters.models import Department, EquipmentModel, FundingSource, Location, Vendor

from .models import Equipment, EquipmentCommissioning

LIFECYCLE_STAGES = ["RECEIVED", "INSTALLED", "COMMISSIONED", "REJECTED", "CONDEMNED", "DISPOSED"]
OPERATIONAL_STATES = ["IN_SERVICE", "UNDER_MAINTENANCE", "OUT_OF_SERVICE"]
CRITICALITY = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
OWNERSHIP_TYPES = ["OWNED", "LEASED", "RENTAL", "LOAN_DEMO", "VENDOR_PLACED"]
ATTR_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_ ]{0,39}$")

COMMON_FIELDS = [
    "name", "serial_number", "legacy_asset_id", "criticality", "ownership_type", "owner_vendor",
    "ownership_end_date", "funding_source", "supplier_vendor", "purchase_order_number", "purchase_order_date",
    "grn_number", "grn_date", "invoice_number", "invoice_date", "purchase_cost", "installation_cost",
    "expected_life_years", "custom_attributes", "notes",
]


def validate_custom_attributes(value):
    if not isinstance(value, dict):
        raise serializers.ValidationError("Must be an object.")
    if len(value) > 30:
        raise serializers.ValidationError("At most 30 attributes are allowed.")
    for key, val in value.items():
        if not isinstance(key, str) or not ATTR_KEY_RE.match(key):
            raise serializers.ValidationError("Invalid attribute name.")
        if isinstance(val, bool):
            continue
        if isinstance(val, (int, float)):
            if isinstance(val, float) and not math.isfinite(val):
                raise serializers.ValidationError("Invalid attribute value.")
        elif isinstance(val, str):
            if len(val) > 200:
                raise serializers.ValidationError("Attribute values are limited to 200 characters.")
        else:
            raise serializers.ValidationError("Attribute values must be text, number or boolean.")
    return value


def ref(obj, *fields):
    if obj is None:
        return None
    return {"public_id": str(obj.public_id), **{f: getattr(obj, f) for f in fields}}


def _facility(serializer):
    ctx = getattr(serializer.context.get("request"), "bems", None)
    return getattr(ctx, "facility", None)


class ScopedFieldsMixin:
    """Related-object lookups are limited to the current facility and active rows."""
    SCOPED = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        fac = _facility(self)
        for name, model in self.SCOPED.items():
            field = self.fields.get(name)
            if field is not None:
                field.queryset = (model.objects.filter(facility_id=fac.id, is_active=True)
                                  if fac is not None else model.objects.none())


# ---------------------------------------------------------------- read shapes
class EquipmentListSerializer(serializers.BaseSerializer):
    def _compliance(self, o):
        empty = {"calibration_status": None, "next_calibration_due": None, "has_unresolved_failure": None,
                 "current_warranty": None, "current_amc": None}
        ctx = getattr(self.context.get("request"), "bems", None)
        if ctx is None:
            return empty
        from apps.compliance.services import equipment_compliance_summary
        from apps.maintenance.services import today_for
        full = equipment_compliance_summary(o, today_for(ctx.facility))
        out = dict(empty)
        if ctx.has("calibration.view"):
            for k in ("calibration_status", "next_calibration_due", "has_unresolved_failure"):
                out[k] = full[k]
        if ctx.has("warranty.view"):
            out["current_warranty"] = full["current_warranty"]
        if ctx.has("amc.view"):
            out["current_amc"] = full["current_amc"]
        return out
    def to_representation(self, o):
        m = o.equipment_model
        return {
            "public_id": str(o.public_id), "asset_tag": o.asset_tag, "qr_code_value": o.qr_code_value,
            "legacy_asset_id": o.legacy_asset_id, "name": o.name, "serial_number": o.serial_number,
            "equipment_model": {"public_id": str(m.public_id), "model_name": m.model_name,
                                "model_number": m.model_number},
            "manufacturer": ref(m.manufacturer, "name"),
            "category": ref(m.category, "code", "name"),
            "lifecycle_stage": o.lifecycle_stage, "operational_state": o.operational_state,
            "criticality": o.criticality, "ownership_type": o.ownership_type,
            "owning_department": ref(o.owning_department, "code", "name"),
            "current_location": ref(o.current_location, "code", "name"),
            "is_legacy_entry": o.is_legacy_entry, "is_active": o.is_active,
            "row_version": o.row_version, "created_at": o.created_at,
        }


class EquipmentSummarySerializer(serializers.BaseSerializer):
    def to_representation(self, o):
        return {
            "public_id": str(o.public_id), "asset_tag": o.asset_tag, "name": o.name,
            "category": {"code": o.equipment_model.category.code, "name": o.equipment_model.category.name},
            "lifecycle_stage": o.lifecycle_stage, "operational_state": o.operational_state,
            "current_location": ref(o.current_location, "code", "name"),
            "qr_code_value": o.qr_code_value,
        }


class EquipmentDetailSerializer(serializers.BaseSerializer):
    @staticmethod
    def _commissioning(o):
        rec = (EquipmentCommissioning.objects.filter(equipment_id=o.pk, is_active=True)
               .select_related("installation_vendor", "handed_over_department").first())
        if rec is None:
            return None
        accepted_by = None
        if rec.accepted_by is not None:
            accepted_by = User.objects.filter(id=rec.accepted_by).values_list("username", flat=True).first()
        return {
            "installation_date": rec.installation_date,
            "installation_engineer_name": rec.installation_engineer_name,
            "installation_vendor": ref(rec.installation_vendor, "name"),
            "installation_notes": rec.installation_notes,
            "acceptance_test_result": rec.acceptance_test_result,
            "acceptance_test_notes": rec.acceptance_test_notes,
            "acceptance_date": rec.acceptance_date,
            "accepted_by": accepted_by,
            "handed_over_department": ref(rec.handed_over_department, "code", "name"),
            "handover_received_by_name": rec.handover_received_by_name,
            "training_conducted": rec.training_conducted, "training_notes": rec.training_notes,
            "commissioning_date": rec.commissioning_date,
        }

    def to_representation(self, o):
        m = o.equipment_model
        c = m.category
        pick = lambda a, b: a if a is not None else b   # noqa: E731
        return {
            "public_id": str(o.public_id), "asset_tag": o.asset_tag, "qr_code_value": o.qr_code_value,
            "legacy_asset_id": o.legacy_asset_id, "name": o.name, "serial_number": o.serial_number,
            "equipment_model": {
                "public_id": str(m.public_id), "model_name": m.model_name, "model_number": m.model_number,
                "manufacturer": ref(m.manufacturer, "name"), "category": ref(c, "code", "name"),
            },
            "lifecycle_stage": o.lifecycle_stage, "operational_state": o.operational_state,
            "owning_department": ref(o.owning_department, "code", "name"),
            "current_location": ref(o.current_location, "code", "name", "location_type"),
            "criticality": o.criticality, "ownership_type": o.ownership_type,
            "owner_vendor": ref(o.owner_vendor, "name"), "ownership_end_date": o.ownership_end_date,
            "funding_source": ref(o.funding_source, "code", "name"),
            "supplier_vendor": ref(o.supplier_vendor, "name"),
            "purchase_order_number": o.purchase_order_number, "purchase_order_date": o.purchase_order_date,
            "grn_number": o.grn_number, "grn_date": o.grn_date,
            "invoice_number": o.invoice_number, "invoice_date": o.invoice_date,
            "purchase_cost": o.purchase_cost, "installation_cost": o.installation_cost,
            "expected_life_years": o.expected_life_years, "custom_attributes": o.custom_attributes,
            "notes": o.notes, "is_legacy_entry": o.is_legacy_entry,
            "commissioning": self._commissioning(o),
            "effective_pm_interval_days": pick(m.default_pm_interval_days, c.default_pm_interval_days),
            "effective_calibration_interval_days": pick(m.default_calibration_interval_days,
                                                        c.default_calibration_interval_days),
            "effective_risk_class": m.risk_class or c.risk_class,
            "effective_expected_life_years": pick(o.expected_life_years, m.expected_life_years),
            **self._compliance(o),
            "is_active": o.is_active, "row_version": o.row_version,
            "created_at": o.created_at, "updated_at": o.updated_at,
        }


# ---------------------------------------------------------------- write shapes
class EquipmentBaseSerializer(ScopedFieldsMixin, BlankToNullMixin, serializers.ModelSerializer):
    criticality = serializers.ChoiceField(choices=CRITICALITY, required=False)
    ownership_type = serializers.ChoiceField(choices=OWNERSHIP_TYPES, required=False)
    owner_vendor = PublicIdField(queryset=Vendor.objects.none(), required=False, allow_null=True)
    funding_source = PublicIdField(queryset=FundingSource.objects.none(), required=False, allow_null=True)
    supplier_vendor = PublicIdField(queryset=Vendor.objects.none(), required=False, allow_null=True)
    custom_attributes = serializers.JSONField(required=False, validators=[validate_custom_attributes])

    SCOPED = {"owner_vendor": Vendor, "funding_source": FundingSource, "supplier_vendor": Vendor}

    class Meta:
        model = Equipment
        fields = COMMON_FIELDS
        extra_kwargs = {
            "name": {"required": False},
            "expected_life_years": {"min_value": 1, "max_value": 100},
            "purchase_cost": {"min_value": 0},
            "installation_cost": {"min_value": 0},
        }

    def to_representation(self, instance):
        return EquipmentDetailSerializer(instance, context=self.context).data

    def _check_unique(self, fac, model, attrs):
        base = Equipment.objects.filter(facility_id=fac.id, is_active=True)
        if self.instance is not None:
            base = base.exclude(pk=self.instance.pk)
        errors = {}
        serial = attrs.get("serial_number")
        if "serial_number" in attrs and serial and model is not None \
                and base.filter(equipment_model=model, serial_number__iexact=serial).exists():
            errors["serial_number"] = ["This serial number already exists for this model."]
        legacy = attrs.get("legacy_asset_id")
        if "legacy_asset_id" in attrs and legacy and base.filter(legacy_asset_id__iexact=legacy).exists():
            errors["legacy_asset_id"] = ["This legacy asset ID is already in use."]
        if errors:
            raise serializers.ValidationError(errors)

    def validate(self, attrs):
        inst = self.instance
        ownership = attrs.get("ownership_type", inst.ownership_type if inst else "OWNED")
        owner = attrs["owner_vendor"] if "owner_vendor" in attrs else (inst.owner_vendor_id if inst else None)
        if ownership != "OWNED" and not owner:
            raise serializers.ValidationError({"owner_vendor": ["Required when ownership is not Owned."]})
        fac = _facility(self)
        if fac is not None:
            model = attrs.get("equipment_model") or (inst.equipment_model if inst else None)
            self._check_unique(fac, model, attrs)
        return attrs


class EquipmentCreateSerializer(EquipmentBaseSerializer):
    equipment_model = PublicIdField(queryset=EquipmentModel.objects.none())
    owning_department = PublicIdField(queryset=Department.objects.none(), required=False, allow_null=True)
    current_location = PublicIdField(queryset=Location.objects.none(), required=False, allow_null=True)

    SCOPED = {**EquipmentBaseSerializer.SCOPED, "equipment_model": EquipmentModel,
              "owning_department": Department, "current_location": Location}

    class Meta(EquipmentBaseSerializer.Meta):
        fields = ["equipment_model", "owning_department", "current_location"] + COMMON_FIELDS

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs.get("owning_department") is not None and attrs.get("current_location") is None:
            raise serializers.ValidationError({"current_location": ["Required when a department is given."]})
        return attrs


class EquipmentUpdateSerializer(EquipmentBaseSerializer):
    """Editable fields only. Stage, state, location, department, tag, QR and model are not here."""


class EquipmentBulkCreateSerializer(EquipmentCreateSerializer):
    quantity = serializers.IntegerField(min_value=1, max_value=200)
    serial_numbers = serializers.ListField(
        child=serializers.CharField(max_length=100, allow_blank=True), required=False, max_length=200)
    names = serializers.ListField(
        child=serializers.CharField(max_length=200, allow_blank=True), required=False, max_length=200)

    class Meta(EquipmentCreateSerializer.Meta):
        fields = [f for f in EquipmentCreateSerializer.Meta.fields
                  if f not in ("name", "serial_number", "legacy_asset_id")] + ["quantity", "serial_numbers", "names"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        qty = attrs["quantity"]
        for key in ("serial_numbers", "names"):
            if key in attrs:
                if len(attrs[key]) != qty:
                    raise serializers.ValidationError({key: ["The list length must equal the quantity."]})
                attrs[key] = [(s.strip() or None) for s in attrs[key]]
        serials = [s for s in attrs.get("serial_numbers", []) if s]
        lowered = [s.lower() for s in serials]
        if len(set(lowered)) != len(lowered):
            raise serializers.ValidationError({"serial_numbers": ["Duplicate serial numbers in the list."]})
        fac = _facility(self)
        if serials and fac is not None:
            clash = Equipment.objects.filter(
                facility_id=fac.id, is_active=True, equipment_model=attrs["equipment_model"]
            ).extra(where=["lower(serial_number) = any(%s)"], params=[lowered]).exists()
            if clash:
                raise serializers.ValidationError(
                    {"serial_numbers": ["One or more serial numbers already exist for this model."]})
        return attrs


# ---------------------------------------------------------------- action inputs
class InstallSerializer(ScopedFieldsMixin, BlankToNullMixin, serializers.Serializer):
    installation_date = serializers.DateField()
    installation_engineer_name = serializers.CharField(max_length=200, required=False, allow_null=True)
    installation_vendor = PublicIdField(queryset=Vendor.objects.none(), required=False, allow_null=True)
    installation_notes = serializers.CharField(max_length=2000, required=False, allow_null=True)
    SCOPED = {"installation_vendor": Vendor}


class CommissionSerializer(ScopedFieldsMixin, BlankToNullMixin, serializers.Serializer):
    acceptance_test_result = serializers.ChoiceField(choices=["PASS", "CONDITIONAL", "FAIL"])
    acceptance_test_notes = serializers.CharField(max_length=2000, required=False, allow_null=True)
    acceptance_date = serializers.DateField()
    department = PublicIdField(queryset=Department.objects.none())
    location = PublicIdField(queryset=Location.objects.none())
    handover_received_by_name = serializers.CharField(max_length=200)
    training_conducted = serializers.BooleanField(required=False, default=False)
    training_notes = serializers.CharField(max_length=2000, required=False, allow_null=True)
    SCOPED = {"department": Department, "location": Location}

    def validate_acceptance_test_result(self, value):
        if value == "FAIL":
            raise serializers.ValidationError(
                "Acceptance failed. Reject the equipment, or fix the issue and retest before commissioning.")
        return value


class RejectSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000)

class OperationalStateSerializer(serializers.Serializer):
    operational_state = serializers.ChoiceField(choices=["IN_SERVICE", "OUT_OF_SERVICE"])
    reason = serializers.CharField(max_length=1000)
    
class MoveSerializer(ScopedFieldsMixin, BlankToNullMixin, serializers.Serializer):
    location = PublicIdField(queryset=Location.objects.none())
    department = PublicIdField(queryset=Department.objects.none(), required=False, allow_null=True)
    reason = serializers.CharField(max_length=1000)
    SCOPED = {"location": Location, "department": Department}


class LabelsSerializer(serializers.Serializer):
    equipment = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=100)
