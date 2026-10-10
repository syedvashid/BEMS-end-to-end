import uuid
from datetime import date

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from apps.equipment.models import Equipment
from apps.foundation.serializers import BlankToNullMixin
from apps.maintenance.models import WorkOrder
from apps.maintenance.services import add_interval, today_for
from apps.masters.models import EquipmentCategory, EquipmentModel, Vendor

from . import services
from .models import (
    AmcContract, AmcCoverage, CalibrationImpactReview, CalibrationRecord, CalibrationSchedule, EquipmentLicence,
    Warranty, WarrantyClaim,
)

FREQ = ["DAYS", "MONTHS"]
REASONS = ["SCHEDULED", "POST_REPAIR", "AFTER_FAILURE", "OTHER"]
PERFORMERS = ["IN_HOUSE", "VENDOR", "ACCREDITED_LAB"]
LICENCE_TYPES = ["AERB_LICENCE", "AERB_QA_CERTIFICATE", "PRESSURE_VESSEL_INSPECTION", "ELECTRICAL_SAFETY_TEST", "OTHER"]
READ_ONLY = ["public_id", "is_active", "row_version", "created_at", "updated_at"]


class PublicRef(serializers.Field):
    """Related record by public_id, scoped to the request facility (and active rows when the model has the flag)."""
    default_error_messages = {"unknown": "Unknown reference."}

    def __init__(self, model, **kw):
        self.model = model
        super().__init__(**kw)

    def to_internal_value(self, data):
        try:
            pid = uuid.UUID(str(data))
        except (ValueError, TypeError, AttributeError):
            self.fail("unknown")
        qs = self.model.objects.filter(public_id=pid, facility_id=self.context["request"].bems.facility.id)
        if any(f.name == "is_active" for f in self.model._meta.concrete_fields):
            qs = qs.filter(is_active=True)
        obj = qs.first()
        if obj is None:
            self.fail("unknown")
        return obj

    def to_representation(self, obj):
        return str(obj.public_id)


def _opt_pid(source):
    return serializers.UUIDField(source=f"{source}.public_id", read_only=True, allow_null=True)


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise ValidationError({k: ["Unknown field."] for k in sorted(unknown)})
        return super().to_internal_value(data)


def _facility(serializer):
    return serializer.context["request"].bems.facility


def _blank(v):
    v = (v or "").strip() if isinstance(v, str) or v is None else v
    return v or None


# ------------------------------------------------------------------ calibration
class CalibrationScheduleSerializer(BlankToNullMixin, serializers.ModelSerializer):
    public_id = serializers.UUIDField(read_only=True)
    equipment = PublicRef(Equipment)
    equipment_asset_tag = serializers.CharField(source="equipment.asset_tag", read_only=True)
    equipment_name = serializers.CharField(source="equipment.name", read_only=True)
    frequency_type = serializers.ChoiceField(choices=FREQ)
    frequency_value = serializers.IntegerField(min_value=1)
    lead_days = serializers.IntegerField(min_value=0, required=False)
    next_due_date = serializers.DateField(required=False)
    calibration_status = serializers.SerializerMethodField()
    has_unresolved_failure = serializers.SerializerMethodField()
    latest_record = serializers.SerializerMethodField()

    class Meta:
        model = CalibrationSchedule
        fields = ["public_id", "equipment", "equipment_asset_tag", "equipment_name", "frequency_type",
                  "frequency_value", "lead_days", "last_calibrated_date", "next_due_date", "on_fail_hold_equipment",
                  "on_fail_open_work_order", "notes", "calibration_status", "has_unresolved_failure",
                  "latest_record", "is_active", "row_version", "created_at", "updated_at"]
        read_only_fields = READ_ONLY

    def _status(self, obj):
        cache = self.__dict__.setdefault("_cache", {})
        if obj.pk not in cache:
            if "today" not in cache:
                cache["today"] = today_for(_facility(self))
            cache[obj.pk] = services.calibration_status(obj, cache["today"])
        return cache[obj.pk]

    def get_calibration_status(self, obj):
        return self._status(obj)["status"]

    def get_has_unresolved_failure(self, obj):
        return self._status(obj)["has_unresolved_failure"]

    def get_latest_record(self, obj):
        return services.record_summary(self._status(obj)["latest_record"])

    def validate(self, attrs):
        inst, fac = self.instance, _facility(self)
        today = today_for(fac)
        if inst is not None:
            if "equipment" in attrs and attrs["equipment"].pk != inst.equipment_id:
                raise ValidationError({"equipment": ["Cannot be changed."]})
        else:
            if CalibrationSchedule.objects.filter(facility_id=fac.id, equipment_id=attrs["equipment"].pk,
                                                  is_active=True).exists():
                raise ValidationError({"equipment": ["This equipment already has an active calibration schedule."]})
        last = attrs.get("last_calibrated_date")
        if last and last > today:
            raise ValidationError({"last_calibrated_date": ["Cannot be in the future."]})
        if inst is None and "next_due_date" not in attrs:
            attrs["next_due_date"] = add_interval(last or today, attrs["frequency_type"], attrs["frequency_value"])
        return attrs


class CalibrationRecordSerializer(serializers.ModelSerializer):
    public_id = serializers.UUIDField(read_only=True)
    equipment = PublicRef(Equipment, read_only=True)
    equipment_asset_tag = serializers.CharField(source="equipment.asset_tag", read_only=True)
    equipment_name = serializers.CharField(source="equipment.name", read_only=True)
    performer_vendor = _opt_pid("performer_vendor")
    impact_review_required = serializers.SerializerMethodField()
    impact_review = serializers.SerializerMethodField()
    corrective_work_order = serializers.SerializerMethodField()

    class Meta:
        model = CalibrationRecord
        fields = ["public_id", "equipment", "equipment_asset_tag", "equipment_name", "performed_date",
                  "calibration_reason", "performed_by_type", "performer_vendor", "performer_name",
                  "reference_standard_details", "certificate_number", "result", "readings", "deviation_summary",
                  "next_due_date", "notes", "impact_review_required", "impact_review", "corrective_work_order",
                  "created_at"]
        read_only_fields = fields

    def _review(self, obj):
        return CalibrationImpactReview.objects.filter(calibration_record_id=obj.pk).first()

    def get_impact_review_required(self, obj):
        if obj.result != "FAIL":
            return False
        has = getattr(obj, "has_impact_review", None)
        return (not has) if has is not None else self._review(obj) is None

    def get_impact_review(self, obj):
        if obj.result != "FAIL":
            return None
        r = self._review(obj)
        return None if r is None else {"public_id": str(r.public_id), "review_notes": r.review_notes,
                                       "patient_impact_found": r.patient_impact_found, "created_at": r.created_at}

    def get_corrective_work_order(self, obj):
        if obj.result != "FAIL":
            return None
        wo = WorkOrder.objects.filter(facility_id=obj.facility_id, source_calibration_record_id=obj.pk).first()
        return None if wo is None else {"public_id": str(wo.public_id), "wo_number": wo.wo_number, "status": wo.status}


class CalibrationRecordCreateSerializer(StrictSerializer):
    equipment = PublicRef(Equipment)
    performed_date = serializers.DateField()
    calibration_reason = serializers.ChoiceField(choices=REASONS, default="SCHEDULED")
    performed_by_type = serializers.ChoiceField(choices=PERFORMERS)
    performer_vendor = PublicRef(Vendor, required=False, allow_null=True)
    performer_name = serializers.CharField(max_length=200, required=False, allow_null=True, allow_blank=True)
    reference_standard_details = serializers.CharField(max_length=2000, required=False, allow_null=True, allow_blank=True)
    certificate_number = serializers.CharField(max_length=100, required=False, allow_null=True, allow_blank=True)
    result = serializers.ChoiceField(choices=["PASS", "FAIL"])
    readings = serializers.JSONField(required=False, allow_null=True)
    deviation_summary = serializers.CharField(max_length=4000, required=False, allow_null=True, allow_blank=True)
    next_due_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(max_length=4000, required=False, allow_null=True, allow_blank=True)

    def validate(self, attrs):
        for k in ("performer_name", "reference_standard_details", "certificate_number", "deviation_summary", "notes"):
            if k in attrs:
                attrs[k] = _blank(attrs[k])
        if attrs.get("performer_vendor") is None and not attrs.get("performer_name"):
            raise ValidationError({"performer_name": ["Give the performer's name or select a vendor."]})
        return attrs


class ImpactReviewSerializer(StrictSerializer):
    review_notes = serializers.CharField(max_length=4000)
    patient_impact_found = serializers.BooleanField()


class GenerateSchedulesSerializer(StrictSerializer):
    equipment_model = PublicRef(EquipmentModel, required=False)
    category = PublicRef(EquipmentCategory, required=False)
    frequency_type = serializers.ChoiceField(choices=FREQ, required=False)
    frequency_value = serializers.IntegerField(min_value=1, required=False)
    last_calibrated_date = serializers.DateField(required=False, allow_null=True)
    lead_days = serializers.IntegerField(min_value=0, required=False)
    on_fail_hold_equipment = serializers.BooleanField(required=False)
    on_fail_open_work_order = serializers.BooleanField(required=False)

    def validate(self, attrs):
        if ("equipment_model" in attrs) == ("category" in attrs):
            raise ValidationError({"scope": ["Give either equipment_model or category."]})
        if ("frequency_type" in attrs) != ("frequency_value" in attrs):
            raise ValidationError({"frequency_value": ["Give frequency_type and frequency_value together."]})
        return attrs


# ------------------------------------------------------------------ warranty
class WarrantySerializer(BlankToNullMixin, serializers.ModelSerializer):
    public_id = serializers.UUIDField(read_only=True)
    equipment = PublicRef(Equipment)
    equipment_asset_tag = serializers.CharField(source="equipment.asset_tag", read_only=True)
    equipment_name = serializers.CharField(source="equipment.name", read_only=True)
    vendor = PublicRef(Vendor, required=False, allow_null=True)
    vendor_name = serializers.CharField(source="vendor.name", read_only=True, allow_null=True)
    warranty_type = serializers.ChoiceField(choices=["STANDARD", "EXTENDED"])

    class Meta:
        model = Warranty
        fields = ["public_id", "equipment", "equipment_asset_tag", "equipment_name", "vendor", "vendor_name",
                  "warranty_type", "start_date", "end_date", "reference_number", "coverage_terms", "covered_parts",
                  "exclusions", "notes", "is_active", "row_version", "created_at", "updated_at"]
        read_only_fields = READ_ONLY

    def validate(self, attrs):
        inst = self.instance
        if inst is not None and "equipment" in attrs and attrs["equipment"].pk != inst.equipment_id:
            raise ValidationError({"equipment": ["Cannot be changed."]})
        start = attrs.get("start_date", inst.start_date if inst else None)
        end = attrs.get("end_date", inst.end_date if inst else None)
        if start and end and end < start:
            raise ValidationError({"end_date": ["Must not be before the start date."]})
        return attrs


class BulkWarrantySerializer(StrictSerializer):
    equipment = serializers.ListField(child=serializers.UUIDField(), allow_empty=False, max_length=200)
    vendor = PublicRef(Vendor, required=False, allow_null=True)
    warranty_type = serializers.ChoiceField(choices=["STANDARD", "EXTENDED"])
    start_date = serializers.DateField(required=False, allow_null=True)
    end_date = serializers.DateField(required=False, allow_null=True)
    duration_months = serializers.IntegerField(min_value=1, max_value=240, required=False, allow_null=True)
    reference_number = serializers.CharField(max_length=100, required=False, allow_null=True, allow_blank=True)
    coverage_terms = serializers.CharField(max_length=4000, required=False, allow_null=True, allow_blank=True)
    covered_parts = serializers.CharField(max_length=4000, required=False, allow_null=True, allow_blank=True)
    exclusions = serializers.CharField(max_length=4000, required=False, allow_null=True, allow_blank=True)
    notes = serializers.CharField(max_length=4000, required=False, allow_null=True, allow_blank=True)

    def validate(self, attrs):
        if bool(attrs.get("end_date")) == bool(attrs.get("duration_months")):
            raise ValidationError({"end_date": ["Give either end_date or duration_months."]})
        ids = attrs["equipment"]
        if len(set(ids)) != len(ids):
            raise ValidationError({"equipment": ["The same equipment is listed twice."]})
        found = list(Equipment.objects.filter(facility_id=_facility(self).id, is_active=True, public_id__in=ids))
        if len(found) != len(ids):
            raise ValidationError({"equipment": ["Unknown reference."]})
        attrs["equipment_list"] = found
        for k in ("reference_number", "coverage_terms", "covered_parts", "exclusions", "notes"):
            attrs[k] = _blank(attrs.get(k))
        return attrs


class WarrantyClaimSerializer(BlankToNullMixin, serializers.ModelSerializer):
    public_id = serializers.UUIDField(read_only=True)
    warranty = PublicRef(Warranty)
    equipment = PublicRef(Equipment, read_only=True)
    equipment_asset_tag = serializers.CharField(source="equipment.asset_tag", read_only=True)
    work_order = PublicRef(WorkOrder, required=False, allow_null=True)
    status = serializers.ChoiceField(choices=["RAISED", "ACCEPTED", "REJECTED", "RESOLVED"], required=False)
    claim_amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False,
                                            allow_null=True)

    class Meta:
        model = WarrantyClaim
        fields = ["public_id", "warranty", "equipment", "equipment_asset_tag", "work_order", "claim_number",
                  "claim_date", "description", "status", "claim_amount", "resolved_date", "resolution_notes",
                  "is_active", "row_version", "created_at", "updated_at"]
        read_only_fields = READ_ONLY

    def validate(self, attrs):
        inst = self.instance
        if inst is not None and "warranty" in attrs and attrs["warranty"].pk != inst.warranty_id:
            raise ValidationError({"warranty": ["Cannot be changed."]})
        warranty = attrs.get("warranty") or (None if inst is None else Warranty.objects.get(pk=inst.warranty_id))
        wo = attrs.get("work_order")
        if wo is not None and wo.equipment_id != warranty.equipment_id:
            raise ValidationError({"work_order": ["This work order is for different equipment."]})
        claim_date = attrs.get("claim_date", inst.claim_date if inst else None)
        resolved = attrs.get("resolved_date", inst.resolved_date if inst else None)
        if claim_date and resolved and resolved < claim_date:
            raise ValidationError({"resolved_date": ["Must not be before the claim date."]})
        if "description" in attrs and not (attrs["description"] or "").strip():
            raise ValidationError({"description": ["This field is required."]})
        return attrs

    def create(self, validated_data):
        validated_data["equipment_id"] = validated_data["warranty"].equipment_id
        return super().create(validated_data)


# ------------------------------------------------------------------ AMC
class AmcContractSerializer(BlankToNullMixin, serializers.ModelSerializer):
    public_id = serializers.UUIDField(read_only=True)
    vendor = PublicRef(Vendor)
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)
    contract_type = serializers.ChoiceField(choices=["COMPREHENSIVE", "NON_COMPREHENSIVE"])
    contract_cost = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False)
    visit_frequency_per_year = serializers.IntegerField(min_value=0, max_value=366, required=False)
    response_sla_hours = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    uptime_guarantee_percent = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100,
                                                        required=False, allow_null=True)
    renewed_from_contract = _opt_pid("renewed_from_contract")
    equipment_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = AmcContract
        fields = ["public_id", "contract_number", "vendor", "vendor_name", "contract_type", "start_date", "end_date",
                  "contract_cost", "covered_scope", "exclusions", "visit_frequency_per_year", "response_sla_hours",
                  "uptime_guarantee_percent", "penalty_terms", "renewed_from_contract", "notes", "equipment_count",
                  "is_active", "row_version", "created_at", "updated_at"]
        read_only_fields = READ_ONLY

    def validate(self, attrs):
        inst, fac = self.instance, _facility(self)
        start = attrs.get("start_date", inst.start_date if inst else None)
        end = attrs.get("end_date", inst.end_date if inst else None)
        if start and end and end < start:
            raise ValidationError({"end_date": ["Must not be before the start date."]})
        if "contract_number" in attrs:
            num = (attrs["contract_number"] or "").strip()
            if not num:
                raise ValidationError({"contract_number": ["This field is required."]})
            attrs["contract_number"] = num
            dup = AmcContract.objects.filter(facility_id=fac.id, is_active=True, contract_number__iexact=num)
            if inst is not None:
                dup = dup.exclude(pk=inst.pk)
            if dup.exists():
                raise ValidationError({"contract_number": ["This contract number is already in use."]})
        if inst is not None and ("start_date" in attrs or "end_date" in attrs):
            services.check_contract_dates_vs_coverage(inst, start, end)
        return attrs


class AmcContractDetailSerializer(AmcContractSerializer):
    coverage = serializers.SerializerMethodField()

    class Meta(AmcContractSerializer.Meta):
        fields = AmcContractSerializer.Meta.fields + ["coverage"]
        read_only_fields = AmcContractSerializer.Meta.read_only_fields

    def get_coverage(self, obj):
        rows = AmcCoverage.objects.filter(facility_id=obj.facility_id, amc_contract_id=obj.pk) \
            .select_related("equipment").order_by("equipment__asset_tag")
        return [{"equipment": {"public_id": str(r.equipment.public_id), "asset_tag": r.equipment.asset_tag,
                               "name": r.equipment.name}, "allocated_cost": r.allocated_cost} for r in rows]


class CoverageItemSerializer(StrictSerializer):
    equipment = PublicRef(Equipment)
    allocated_cost = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False,
                                              allow_null=True)


class CoverageSetSerializer(StrictSerializer):
    items = serializers.ListField(child=CoverageItemSerializer(), allow_empty=True, max_length=500)


class AmcRenewSerializer(StrictSerializer):
    contract_number = serializers.CharField(max_length=100, required=False, allow_null=True, allow_blank=True)
    start_date = serializers.DateField(required=False, allow_null=True)
    end_date = serializers.DateField(required=False, allow_null=True)
    contract_cost = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False,
                                             allow_null=True)


# ------------------------------------------------------------------ licences
class EquipmentLicenceSerializer(BlankToNullMixin, serializers.ModelSerializer):
    public_id = serializers.UUIDField(read_only=True)
    equipment = PublicRef(Equipment)
    equipment_asset_tag = serializers.CharField(source="equipment.asset_tag", read_only=True)
    equipment_name = serializers.CharField(source="equipment.name", read_only=True)
    licence_type = serializers.ChoiceField(choices=LICENCE_TYPES)
    renewed_from_licence = _opt_pid("renewed_from_licence")

    class Meta:
        model = EquipmentLicence
        fields = ["public_id", "equipment", "equipment_asset_tag", "equipment_name", "licence_type", "licence_number",
                  "issuing_authority", "issue_date", "expiry_date", "renewed_from_licence", "notes", "is_active",
                  "row_version", "created_at", "updated_at"]
        read_only_fields = READ_ONLY

    def validate(self, attrs):
        inst = self.instance
        if inst is not None and "equipment" in attrs and attrs["equipment"].pk != inst.equipment_id:
            raise ValidationError({"equipment": ["Cannot be changed."]})
        issue = attrs.get("issue_date", inst.issue_date if inst else None)
        expiry = attrs.get("expiry_date", inst.expiry_date if inst else None)
        if issue and expiry and expiry < issue:
            raise ValidationError({"expiry_date": ["Must not be before the issue date."]})
        return attrs


class LicenceRenewSerializer(StrictSerializer):
    issue_date = serializers.DateField()
    expiry_date = serializers.DateField()
    licence_number = serializers.CharField(max_length=100, required=False, allow_null=True, allow_blank=True)
    issuing_authority = serializers.CharField(max_length=200, required=False, allow_null=True, allow_blank=True)
    notes = serializers.CharField(max_length=4000, required=False, allow_null=True, allow_blank=True)