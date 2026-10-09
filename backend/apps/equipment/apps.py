from django.apps import AppConfig


class EquipmentConfig(AppConfig):
    name = "apps.equipment"
    label = "equipment"

    def ready(self):
        # Phase 3 attachable registry: documents can be attached to equipment.
        from apps.documents.registry import register_attachable

        from .models import Equipment

        register_attachable("equipment", Equipment, "equipment.view", "equipment.change", label_field="asset_tag")
