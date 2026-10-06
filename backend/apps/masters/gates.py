from apps.core.errors import Conflict

from .models import EquipmentCategory, EquipmentModel, Location, VendorContact


def _block(count, what):
    if count:
        raise Conflict(f"Cannot delete: {count} active {what} still depend on this record.")


def ensure_category_deletable(instance):
    _block(EquipmentCategory.objects.filter(
        facility_id=instance.facility_id, parent_category_id=instance.pk, is_active=True).count(), "sub-categories")
    _block(EquipmentModel.objects.filter(
        facility_id=instance.facility_id, category_id=instance.pk, is_active=True).count(), "equipment models")
    # Phase 4: active equipment records


def ensure_location_deletable(instance):
    _block(Location.objects.filter(
        facility_id=instance.facility_id, parent_location_id=instance.pk, is_active=True).count(), "child locations")
    # Phase 4: active equipment placed here


def ensure_department_deletable(instance):
    _block(Location.objects.filter(
        facility_id=instance.facility_id, department_id=instance.pk, is_active=True).count(), "locations")
    # Phase 4: active equipment owned by this department


def ensure_vendor_deletable(instance):
    _block(VendorContact.objects.filter(
        facility_id=instance.facility_id, vendor_id=instance.pk, is_active=True).count(), "contacts")
    _block(EquipmentModel.objects.filter(
        facility_id=instance.facility_id, manufacturer_id=instance.pk, is_active=True).count(), "equipment models")
    # Phase 4+: purchase and service records


def ensure_funding_source_deletable(instance):
    pass  # no dependents yet (Phase 4/9 will add them)