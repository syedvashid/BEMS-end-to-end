from django.apps import AppConfig


class ComplianceConfig(AppConfig):
    name = "apps.compliance"
    label = "compliance"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from apps.documents.registry import register_attachable
        from . import models as m
        register_attachable("calibration_record", m.CalibrationRecord, "calibration.view", "calibration.record",
                            "certificate_number")
        register_attachable("warranty", m.Warranty, "warranty.view", "warranty.change", "reference_number")
        register_attachable("amc_contract", m.AmcContract, "amc.view", "amc.change", "contract_number")
        register_attachable("equipment_licence", m.EquipmentLicence, "licence.view", "licence.change",
                            "licence_number")