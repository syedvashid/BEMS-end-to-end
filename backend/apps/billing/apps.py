from django.apps import AppConfig


class BillingConfig(AppConfig):
    name = "apps.billing"
    label = "billing"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import reports  # noqa: F401  (registers BILLING_EVENTS and CHARGE_RECONCILIATION in the Phase 10 registry)
