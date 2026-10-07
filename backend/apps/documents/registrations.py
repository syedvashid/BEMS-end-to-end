from apps.masters.models import EquipmentModel, Vendor

from .registry import register_attachable

register_attachable("vendor", Vendor, "vendor.view", "vendor.change", label_field="name")
register_attachable("equipment_model", EquipmentModel, "equipment_model.view", "equipment_model.change",
                    label_field="model_name")