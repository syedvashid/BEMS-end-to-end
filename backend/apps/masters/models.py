from django.db import models

from apps.core.models import FacilityScopedModel


class Department(FacilityScopedModel):
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=200)
    department_type = models.CharField(max_length=20)
    description = models.CharField(max_length=500, null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "departments"


class Location(FacilityScopedModel):
    parent_location = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.DO_NOTHING, db_constraint=False, related_name="children"
    )
    location_type = models.CharField(max_length=20)
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=200)
    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.DO_NOTHING, db_constraint=False, related_name="locations"
    )
    description = models.CharField(max_length=500, null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "locations"


class EquipmentCategory(FacilityScopedModel):
    parent_category = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.DO_NOTHING, db_constraint=False, related_name="children"
    )
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=200)
    description = models.CharField(max_length=500, null=True, blank=True)
    default_pm_interval_days = models.IntegerField(null=True, blank=True)
    default_calibration_interval_days = models.IntegerField(null=True, blank=True)
    risk_class = models.CharField(max_length=10, default="MEDIUM")

    class Meta(FacilityScopedModel.Meta):
        db_table = "equipment_categories"


class Vendor(FacilityScopedModel):
    name = models.CharField(max_length=200)
    is_manufacturer = models.BooleanField(default=False)
    is_supplier = models.BooleanField(default=False)
    is_service_provider = models.BooleanField(default=False)
    gstin = models.CharField(max_length=15, null=True, blank=True)
    pan = models.CharField(max_length=10, null=True, blank=True)
    address_line1 = models.CharField(max_length=200, null=True, blank=True)
    address_line2 = models.CharField(max_length=200, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    state = models.CharField(max_length=100, null=True, blank=True)
    pin_code = models.CharField(max_length=6, null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    email = models.CharField(max_length=254, null=True, blank=True)
    rating = models.SmallIntegerField(null=True, blank=True)
    notes = models.CharField(max_length=1000, null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "vendors"


class VendorContact(FacilityScopedModel):
    vendor = models.ForeignKey(
        Vendor, on_delete=models.DO_NOTHING, db_constraint=False, related_name="contacts"
    )
    name = models.CharField(max_length=200)
    designation = models.CharField(max_length=100, null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    email = models.CharField(max_length=254, null=True, blank=True)
    contact_type = models.CharField(max_length=20, default="OTHER")
    is_primary = models.BooleanField(default=False)

    class Meta(FacilityScopedModel.Meta):
        db_table = "vendor_contacts"


class FundingSource(FacilityScopedModel):
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=200)
    source_type = models.CharField(max_length=20)
    description = models.CharField(max_length=500, null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "funding_sources"


class EquipmentModel(FacilityScopedModel):
    category = models.ForeignKey(
        EquipmentCategory, on_delete=models.DO_NOTHING, db_constraint=False, related_name="equipment_models"
    )
    manufacturer = models.ForeignKey(
        Vendor, on_delete=models.DO_NOTHING, db_constraint=False, related_name="manufactured_models"
    )
    model_name = models.CharField(max_length=200)
    model_number = models.CharField(max_length=100)
    description = models.CharField(max_length=500, null=True, blank=True)
    risk_class = models.CharField(max_length=10, null=True, blank=True)
    default_pm_interval_days = models.IntegerField(null=True, blank=True)
    default_calibration_interval_days = models.IntegerField(null=True, blank=True)
    expected_life_years = models.IntegerField(null=True, blank=True)
    cdsco_registration_number = models.CharField(max_length=100, null=True, blank=True)

    class Meta(FacilityScopedModel.Meta):
        db_table = "equipment_models"