from django.apps import AppConfig


class MaintenanceConfig(AppConfig):
    name = "apps.maintenance"
    label = "maintenance"

    def ready(self):
        # Phase 3 attachable registry: documents (service reports, photos) can be attached to work orders.
        from apps.documents.registry import register_attachable

        from .models import WorkOrder

        register_attachable("work_order", WorkOrder, "work_order.view", "work_order.change", label_field="wo_number")
