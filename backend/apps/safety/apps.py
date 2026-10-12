from django.apps import AppConfig


class SafetyConfig(AppConfig):
    name = "apps.safety"
    label = "safety"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # Phase 3 attachable registry: documents can be attached to incidents and recall notices.
        from apps.documents.registry import register_attachable

        from .models import EquipmentIncident, RecallNotice
        register_attachable("equipment_incident", EquipmentIncident, "incident.view", "incident.add",
                            label_field="incident_number")
        register_attachable("recall_notice", RecallNotice, "recall.view", "recall.add",
                            label_field="notice_number")
