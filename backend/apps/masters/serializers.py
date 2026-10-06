import re

from rest_framework import serializers

from apps.core import audit
from apps.core.errors import Conflict
from apps.foundation.serializers import PHONE_RE, PIN_RE, BlankToNullMixin, PublicIdField

from .models import Department, EquipmentCategory, EquipmentModel, FundingSource, Location, Vendor, VendorContact

CATEGORY_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")

DEPARTMENT_TYPES = ["CLINICAL", "DIAGNOSTIC", "SUPPORT", "ADMINISTRATIVE"]
LOCATION_TYPES = ["BUILDING", "FLOOR", "WARD", "ROOM", "BED", "STORE", "OTHER"]
ALLOWED_PARENT_TYPES = {
    "FLOOR": {"BUILDING"}, "WARD": {"FLOOR"}, "ROOM": {"FLOOR", "WARD"},
    "BED": {"ROOM", "WARD"}, "STORE": {"BUILDING", "FLOOR"},
}
RISK_CLASSES = ["LOW", "MEDIUM", "HIGH"]
CONTACT_TYPES = ["SALES", "SERVICE", "ESCALATION", "OTHER"]
SOURCE_TYPES = ["OWN_FUNDS", "GRANT", "DONATION", "CSR", "GOVERNMENT_SCHEME", "LEASE_LOAN", "OTHER"]

META = ["is_active", "row_version", "created_at", "updated_at"]
READ_ONLY = ["public_id", *META]


def opt(max_length):
    return serializers.CharField(max_length=max_length, required=False, allow_null=True)


def facility_of(serializer):
    bems = getattr(serializer.context.get("request"), "bems", None)
    return bems.facility if bems is not None else None


def ensure_unique(serializer, model, lookup, value, message, **extra):
    """Uniqueness among ACTIVE rows of the current facility (mirrors the partial unique indexes)."""
    fac = facility_of(serializer)
    qs = model.objects.filter(facility_id=fac.id, is_active=True, **{lookup: value}, **extra)
    if serializer.instance is not None:
        qs = qs.exclude(pk=serializer.instance.pk)
    if qs.exists():
        raise serializers.ValidationError(message)


class FacilityRef(PublicIdField):
    """Related record by public_id; only ACTIVE rows of the CURRENT facility are accepted."""
    def __init__(self, **kwargs):
        self.model = kwargs.pop("model")
        kwargs.setdefault("queryset", self.model.objects.none())
        super().__init__(**kwargs)

    def get_queryset(self):
        bems = getattr(self.context.get("request"), "bems", None)
        if bems is None or bems.facility is None:
            return self.model.objects.none()
        return self.model.objects.filter(facility_id=bems.facility.id, is_active=True)


# ---------------------------------------------------------------- departments
class DepartmentSerializer(BlankToNullMixin, serializers.ModelSerializer):
    code = serializers.CharField(max_length=30)
    name = serializers.CharField(max_length=200)
    department_type = serializers.ChoiceField(choices=DEPARTMENT_TYPES)
    description = opt(500)

    class Meta:
        model = Department
        fields = ["public_id", "code", "name", "department_type", "description", *META]
        read_only_fields = READ_ONLY

    def validate_code(self, value):
        ensure_unique(self, Department, "code__iexact", value, "This code is already in use.")
        return value

    def validate_name(self, value):
        ensure_unique(self, Department, "name__iexact", value, "This name is already in use.")
        return value


# ------------------------------------------------------------------ locations
def parent_allowed(location_type, parent_type):
    if location_type == "OTHER":
        return True
    if location_type == "BUILDING":
        return parent_type is None
    return parent_type is not None and parent_type in ALLOWED_PARENT_TYPES[location_type]


class LocationSerializer(BlankToNullMixin, serializers.ModelSerializer):
    parent_location = FacilityRef(model=Location, required=False, allow_null=True)
    location_type = serializers.ChoiceField(choices=LOCATION_TYPES)
    code = serializers.CharField(max_length=30)
    name = serializers.CharField(max_length=200)
    department = FacilityRef(model=Department, required=False, allow_null=True)
    description = opt(500)

    class Meta:
        model = Location
        fields = ["public_id", "parent_location", "location_type", "code", "name", "department",
                  "description", *META]
        read_only_fields = READ_ONLY

    def validate_code(self, value):
        ensure_unique(self, Location, "code__iexact", value, "This code is already in use.")
        return value

    def validate(self, attrs):
        inst = self.instance
        ltype = attrs.get("location_type", inst.location_type if inst else None)
        parent = attrs["parent_location"] if "parent_location" in attrs else (inst.parent_location if inst else None)
        ptype = parent.location_type if parent is not None else None

        if not parent_allowed(ltype, ptype):
            if ltype == "BUILDING":
                msg = "A building cannot have a parent location."
            else:
                msg = f"A {ltype.lower()} must be placed inside: {', '.join(sorted(ALLOWED_PARENT_TYPES[ltype]))}."
            raise serializers.ValidationError({"parent_location": [msg]})

        if inst is not None:
            node, depth = parent, 0
            while node is not None and depth < 50:
                if node.pk == inst.pk:
                    raise serializers.ValidationError(
                        {"parent_location": ["A location cannot be placed inside itself or its own descendants."]})
                node, depth = node.parent_location, depth + 1
            if ltype != inst.location_type:
                for child in inst.children.filter(is_active=True):
                    if not parent_allowed(child.location_type, ltype):
                        raise serializers.ValidationError({"location_type": [
                            f"Active child '{child.code}' ({child.location_type}) cannot be placed under a {ltype}."]})
        return attrs


# ----------------------------------------------------------------- categories
class EquipmentCategorySerializer(BlankToNullMixin, serializers.ModelSerializer):
    parent_category = FacilityRef(model=EquipmentCategory, required=False, allow_null=True)
    code = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=200)
    description = opt(500)
    default_pm_interval_days = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    default_calibration_interval_days = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    risk_class = serializers.ChoiceField(choices=RISK_CLASSES, required=False)

    class Meta:
        model = EquipmentCategory
        fields = ["public_id", "parent_category", "code", "name", "description", "default_pm_interval_days",
                  "default_calibration_interval_days", "risk_class", *META]
        read_only_fields = READ_ONLY

    def validate_code(self, value):
        value = value.strip().upper()
        if not CATEGORY_CODE_RE.match(value):
            raise serializers.ValidationError("Use A-Z, 0-9 and '_'; must start with a letter.")
        ensure_unique(self, EquipmentCategory, "code__iexact", value, "This code is already in use.")
        return value

    def validate_name(self, value):
        ensure_unique(self, EquipmentCategory, "name__iexact", value, "This name is already in use.")
        return value

    def validate(self, attrs):
        inst = self.instance
        parent = attrs["parent_category"] if "parent_category" in attrs else (inst.parent_category if inst else None)
        if parent is not None:
            if inst is not None and parent.pk == inst.pk:
                raise serializers.ValidationError({"parent_category": ["A category cannot be its own parent."]})
            if parent.parent_category_id is not None:
                raise serializers.ValidationError(
                    {"parent_category": ["Categories have at most two levels: choose a top-level group as parent."]})
            if inst is not None and inst.children.filter(is_active=True).exists():
                raise serializers.ValidationError(
                    {"parent_category": ["This category has sub-categories, so it cannot be placed under another."]})
        return attrs


# -------------------------------------------------------------------- vendors
VENDOR_FLAGS = ("is_manufacturer", "is_supplier", "is_service_provider")


class VendorSerializer(BlankToNullMixin, serializers.ModelSerializer):
    name = serializers.CharField(max_length=200)
    is_manufacturer = serializers.BooleanField(required=False)
    is_supplier = serializers.BooleanField(required=False)
    is_service_provider = serializers.BooleanField(required=False)
    gstin = opt(15)
    pan = opt(10)
    address_line1 = opt(200)
    address_line2 = opt(200)
    city = opt(100)
    state = opt(100)
    pin_code = serializers.RegexField(PIN_RE, required=False, allow_null=True)
    phone = serializers.RegexField(PHONE_RE, required=False, allow_null=True)
    email = serializers.EmailField(max_length=254, required=False, allow_null=True)
    rating = serializers.IntegerField(min_value=1, max_value=5, required=False, allow_null=True)
    notes = opt(1000)

    class Meta:
        model = Vendor
        fields = ["public_id", "name", *VENDOR_FLAGS, "gstin", "pan", "address_line1", "address_line2",
                  "city", "state", "pin_code", "phone", "email", "rating", "notes", *META]
        read_only_fields = READ_ONLY

    def validate_name(self, value):
        ensure_unique(self, Vendor, "name__iexact", value, "This name is already in use.")
        return value

    def validate_gstin(self, value):
        if value is None:
            return value
        value = value.strip().upper()
        if not GSTIN_RE.match(value):
            raise serializers.ValidationError("Invalid GSTIN format.")
        return value

    def validate_pan(self, value):
        if value is None:
            return value
        value = value.strip().upper()
        if not PAN_RE.match(value):
            raise serializers.ValidationError("Invalid PAN format.")
        return value

    def validate(self, attrs):
        inst = self.instance
        flags = {f: attrs.get(f, getattr(inst, f, False) if inst else False) for f in VENDOR_FLAGS}
        if not any(flags.values()):
            raise serializers.ValidationError({"is_manufacturer": ["Select at least one vendor type."]})
        if inst is not None and inst.is_manufacturer and not flags["is_manufacturer"]:
            if EquipmentModel.objects.filter(
                    facility_id=inst.facility_id, manufacturer_id=inst.pk, is_active=True).exists():
                raise Conflict("This vendor is the manufacturer of active equipment models, "
                               "so it must remain a manufacturer.")
        return attrs


class VendorContactSerializer(BlankToNullMixin, serializers.ModelSerializer):
    vendor = FacilityRef(model=Vendor)
    name = serializers.CharField(max_length=200)
    designation = opt(100)
    phone = serializers.RegexField(PHONE_RE, required=False, allow_null=True)
    email = serializers.EmailField(max_length=254, required=False, allow_null=True)
    contact_type = serializers.ChoiceField(choices=CONTACT_TYPES, required=False)
    is_primary = serializers.BooleanField(required=False)

    class Meta:
        model = VendorContact
        fields = ["public_id", "vendor", "name", "designation", "phone", "email", "contact_type",
                  "is_primary", *META]
        read_only_fields = READ_ONLY

    def validate_vendor(self, value):
        if self.instance is not None and value.pk != self.instance.vendor_id:
            raise serializers.ValidationError("The vendor of a contact cannot be changed.")
        return value

    def _demote_other_primaries(self, vendor, exclude_pk=None):
        """Runs inside the viewset's atomic block: the new primary replaces the old one."""
        request = self.context["request"]
        fac = facility_of(self)
        qs = VendorContact.objects.filter(facility_id=fac.id, vendor_id=vendor.pk, is_active=True, is_primary=True)
        if exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
        for other in list(qs):
            other.is_primary = False
            other.updated_by = request.user.id
            other.save(update_fields=["is_primary", "updated_by"])
            audit.record(
                request=request, action="UPDATE", facility_id=fac.id, entity_type="VendorContact",
                entity_public_id=other.public_id, previous={"is_primary": True}, new={"is_primary": False},
                changed_fields=["is_primary"],
            )

    def create(self, validated_data):
        if validated_data.get("is_primary"):
            self._demote_other_primaries(validated_data["vendor"])
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if validated_data.get("is_primary"):
            self._demote_other_primaries(instance.vendor, exclude_pk=instance.pk)
        return super().update(instance, validated_data)


# ------------------------------------------------------------ funding sources
class FundingSourceSerializer(BlankToNullMixin, serializers.ModelSerializer):
    code = serializers.CharField(max_length=30)
    name = serializers.CharField(max_length=200)
    source_type = serializers.ChoiceField(choices=SOURCE_TYPES)
    description = opt(500)

    class Meta:
        model = FundingSource
        fields = ["public_id", "code", "name", "source_type", "description", *META]
        read_only_fields = READ_ONLY

    def validate_code(self, value):
        ensure_unique(self, FundingSource, "code__iexact", value, "This code is already in use.")
        return value


# ------------------------------------------------------------ equipment models
class EquipmentModelSerializer(BlankToNullMixin, serializers.ModelSerializer):
    category = FacilityRef(model=EquipmentCategory)
    manufacturer = FacilityRef(model=Vendor)
    model_name = serializers.CharField(max_length=200)
    model_number = serializers.CharField(max_length=100)
    description = opt(500)
    risk_class = serializers.ChoiceField(choices=RISK_CLASSES, required=False, allow_null=True)
    default_pm_interval_days = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    default_calibration_interval_days = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    expected_life_years = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    cdsco_registration_number = opt(100)
    effective_pm_interval_days = serializers.SerializerMethodField()
    effective_calibration_interval_days = serializers.SerializerMethodField()
    effective_risk_class = serializers.SerializerMethodField()

    class Meta:
        model = EquipmentModel
        fields = ["public_id", "category", "manufacturer", "model_name", "model_number", "description",
                  "risk_class", "default_pm_interval_days", "default_calibration_interval_days",
                  "expected_life_years", "cdsco_registration_number",
                  "effective_pm_interval_days", "effective_calibration_interval_days", "effective_risk_class",
                  *META]
        read_only_fields = READ_ONLY + ["effective_pm_interval_days", "effective_calibration_interval_days",
                                        "effective_risk_class"]

    def get_effective_pm_interval_days(self, obj):
        v = obj.default_pm_interval_days
        return v if v is not None else obj.category.default_pm_interval_days

    def get_effective_calibration_interval_days(self, obj):
        v = obj.default_calibration_interval_days
        return v if v is not None else obj.category.default_calibration_interval_days

    def get_effective_risk_class(self, obj):
        return obj.risk_class or obj.category.risk_class

    def validate_category(self, value):
        if EquipmentCategory.objects.filter(parent_category_id=value.pk, is_active=True).exists():
            raise serializers.ValidationError("Choose a category without sub-categories (not a group).")
        return value

    def validate_manufacturer(self, value):
        if not value.is_manufacturer:
            raise serializers.ValidationError("The selected vendor is not marked as a manufacturer.")
        return value

    def validate(self, attrs):
        inst = self.instance
        manufacturer = attrs.get("manufacturer", inst.manufacturer if inst else None)
        number = attrs.get("model_number", inst.model_number if inst else None)
        fac = facility_of(self)
        qs = EquipmentModel.objects.filter(
            facility_id=fac.id, is_active=True, manufacturer_id=manufacturer.pk, model_number__iexact=number)
        if inst is not None:
            qs = qs.exclude(pk=inst.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {"model_number": ["This manufacturer already has a model with this number."]})
        return attrs