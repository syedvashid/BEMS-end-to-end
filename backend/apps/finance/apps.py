from django.apps import AppConfig


class FinanceConfig(AppConfig):
    name = "apps.finance"
    label = "finance"

    def ready(self):
        # Phase 3 attachable registry: documents (approval letters, certificates) on requests and disposals.
        from apps.documents.registry import register_attachable

        from .models import CondemnationRequest, Disposal

        register_attachable("condemnation_request", CondemnationRequest, "condemnation.view", "condemnation.add",
                            label_field="request_number")
        register_attachable("disposal", Disposal, "disposal.view", "disposal.manage", label_field="disposal_number")
