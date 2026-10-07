from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    name = "apps.documents"
    label = "documents"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import registrations  # noqa: F401  (registers attachable entities)