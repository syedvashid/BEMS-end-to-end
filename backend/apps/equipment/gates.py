"""Delete gates for Phase 2 masters: block soft delete while active equipment references the record."""
from .errors import Conflict
from .models import Equipment, EquipmentCommissioning

_CHECKS = {
    "equipment_model": [(Equipment, "equipment_model_id")],
    "location": [(Equipment, "current_location_id")],
    "department": [(Equipment, "owning_department_id")],
    "vendor": [(Equipment, "supplier_vendor_id"), (Equipment, "owner_vendor_id"),
               (EquipmentCommissioning, "installation_vendor_id")],
    "funding_source": [(Equipment, "funding_source_id")],
}


def ensure_unused(kind, instance):
    for model, field in _CHECKS[kind]:
        if model.objects.filter(facility_id=instance.facility_id, is_active=True, **{field: instance.pk}).exists():
            raise Conflict("This record is in use by active equipment.")
