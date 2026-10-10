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
    from apps.maintenance.models import ChecklistTemplate, SparePartCategory   # Phase 5 (lazy: avoids a cycle)
    _block(ChecklistTemplate.objects.filter(
        facility_id=instance.facility_id, category_id=instance.pk, is_active=True).count(), "checklist templates")
    _block(SparePartCategory.objects.filter(
        facility_id=instance.facility_id, category_id=instance.pk, spare_part__is_active=True).count(),
        "spare parts listing this category as compatible")


def ensure_location_deletable(instance):
    _block(Location.objects.filter(
        facility_id=instance.facility_id, parent_location_id=instance.pk, is_active=True).count(), "child locations")
    # Phase 4: active equipment placed here


def ensure_department_deletable(instance):
    _block(Location.objects.filter(
        facility_id=instance.facility_id, department_id=instance.pk, is_active=True).count(), "locations")
    # Phase 4: active equipment owned by this department

from apps.compliance.gates import vendor_compliance_blockers
def ensure_vendor_deletable(instance):
    blockers = vendor_compliance_blockers(instance)
    if blockers:
        raise Conflict("Cannot delete: " + "; ".join(blockers) + " still use this vendor.")
    _block(VendorContact.objects.filter(
        facility_id=instance.facility_id, vendor_id=instance.pk, is_active=True).count(), "contacts")
    _block(EquipmentModel.objects.filter(
        facility_id=instance.facility_id, manufacturer_id=instance.pk, is_active=True).count(), "equipment models")
    # Phase 4+: purchase and service records


def ensure_funding_source_deletable(instance):
    pass  # no dependents yet (Phase 4/9 will add them)



def ensure_equipment_model_deletable(instance):
    from apps.maintenance.models import ChecklistTemplate   # Phase 5
    _block(ChecklistTemplate.objects.filter(
        facility_id=instance.facility_id, equipment_model_id=instance.pk, is_active=True).count(), "checklist templates")