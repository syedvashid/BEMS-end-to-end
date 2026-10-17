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
    from apps.finance.models import DepreciationPolicy   # Phase 9 (lazy)
    _block(DepreciationPolicy.objects.filter(
        facility_id=instance.facility_id, category_id=instance.pk, is_active=True).count(), "depreciation policies")
    from apps.billing.gates import category_mapping_count   # Phase 11 (lazy)
    _block(category_mapping_count(instance), "charge mappings")


def ensure_location_deletable(instance):
    _block(Location.objects.filter(
        facility_id=instance.facility_id, parent_location_id=instance.pk, is_active=True).count(), "child locations")
    from apps.allocation.support import location_blockers     # Phase 7 (lazy: avoids a cycle)
    for count, what in location_blockers(instance):
        _block(count, what)


# def ensure_department_deletable(instance):
#     _block(Location.objects.filter(
#         facility_id=instance.facility_id, department_id=instance.pk, is_active=True).count(), "locations")
#     from apps.allocation.support import department_blockers   # Phase 7
#     for count, what in department_blockers(instance):
#         _block(count, what)

from apps.compliance.gates import vendor_compliance_blockers
def ensure_vendor_deletable(instance):
    blockers = vendor_compliance_blockers(instance)
    if blockers:
        raise Conflict("Cannot delete: " + "; ".join(blockers) + " still use this vendor.")
    _block(VendorContact.objects.filter(
        facility_id=instance.facility_id, vendor_id=instance.pk, is_active=True).count(), "contacts")
    _block(EquipmentModel.objects.filter(
        facility_id=instance.facility_id, manufacturer_id=instance.pk, is_active=True).count(), "equipment models")
    from apps.safety.models import RecallNotice   # Phase 8 (lazy)
    _block(RecallNotice.objects.filter(
        facility_id=instance.facility_id, issued_by_vendor_id=instance.pk, status="OPEN", is_active=True).count(),
        "open recall notices")
    from apps.finance.models import Disposal   # Phase 9 (lazy)
    _block(Disposal.objects.filter(
        facility_id=instance.facility_id, recipient_vendor_id=instance.pk, status="IN_PROGRESS",
        is_active=True).count(), "disposals in progress")
    # Phase 4+: purchase and service records


def ensure_funding_source_deletable(instance):
    pass  # no dependents yet (Phase 4/9 will add them)



def ensure_equipment_model_deletable(instance):
    from apps.maintenance.models import ChecklistTemplate   # Phase 5
    _block(ChecklistTemplate.objects.filter(
        facility_id=instance.facility_id, equipment_model_id=instance.pk, is_active=True).count(), "checklist templates")
    from apps.safety.models import RecallNoticeModel   # Phase 8 (lazy)
    _block(RecallNoticeModel.objects.filter(
        facility_id=instance.facility_id, equipment_model_id=instance.pk, recall_notice__status="OPEN",
        recall_notice__is_active=True).count(), "open recall notices")





# def ensure_department_deletable(instance):
#     _block(Location.objects.filter(
#         facility_id=instance.facility_id, department_id=instance.pk, is_active=True).count(), "locations")
# # after
#     from apps.safety.models import PhysicalVerification   # Phase 8 (lazy)
#     _block(PhysicalVerification.objects.filter(
#         facility_id=instance.facility_id, location_id=instance.pk, is_active=True,
#         status__in=("PLANNED", "IN_PROGRESS")).count(), "open physical verifications")
    # Phase 4: active equipment placed here


def ensure_department_deletable(instance):
    _block(Location.objects.filter(
        facility_id=instance.facility_id, department_id=instance.pk, is_active=True).count(), "locations")
    from apps.safety.models import PhysicalVerification   # Phase 8 (lazy)
    _block(PhysicalVerification.objects.filter(
        facility_id=instance.facility_id, department_id=instance.pk, is_active=True,
        status__in=("PLANNED", "IN_PROGRESS")).count(), "open physical verifications")