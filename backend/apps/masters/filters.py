import django_filters as df
from django.db.models import Q

from .models import Department, EquipmentCategory, EquipmentModel, FundingSource, Location, Vendor, VendorContact


def search_filter(*fields):
    def method(qs, name, value):
        if not value:
            return qs
        q = Q()
        for f in fields:
            q |= Q(**{f"{f}__icontains": value})
        return qs.filter(q)
    return df.CharFilter(method=method)


class DepartmentFilter(df.FilterSet):
    search = search_filter("code", "name")

    class Meta:
        model = Department
        fields = ["department_type"]


class LocationFilter(df.FilterSet):
    parent = df.UUIDFilter(field_name="parent_location__public_id")
    department = df.UUIDFilter(field_name="department__public_id")
    search = search_filter("code", "name")

    class Meta:
        model = Location
        fields = ["location_type"]


class EquipmentCategoryFilter(df.FilterSet):
    parent = df.UUIDFilter(field_name="parent_category__public_id")
    search = search_filter("code", "name")

    class Meta:
        model = EquipmentCategory
        fields = ["risk_class"]


class VendorFilter(df.FilterSet):
    is_manufacturer = df.BooleanFilter()
    is_supplier = df.BooleanFilter()
    is_service_provider = df.BooleanFilter()
    search = search_filter("name")

    class Meta:
        model = Vendor
        fields = []


class VendorContactFilter(df.FilterSet):
    vendor = df.UUIDFilter(field_name="vendor__public_id")

    class Meta:
        model = VendorContact
        fields = ["contact_type"]


class FundingSourceFilter(df.FilterSet):
    search = search_filter("code", "name")

    class Meta:
        model = FundingSource
        fields = ["source_type"]


class EquipmentModelFilter(df.FilterSet):
    category = df.UUIDFilter(field_name="category__public_id")
    manufacturer = df.UUIDFilter(field_name="manufacturer__public_id")
    search = search_filter("model_name", "model_number")

    class Meta:
        model = EquipmentModel
        fields = []