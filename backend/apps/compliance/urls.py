from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("calibration-schedules", views.CalibrationScheduleViewSet, basename="calibration-schedule")
router.register("calibration-records", views.CalibrationRecordViewSet, basename="calibration-record")
router.register("warranties", views.WarrantyViewSet, basename="warranty")
router.register("warranty-claims", views.WarrantyClaimViewSet, basename="warranty-claim")
router.register("amc-contracts", views.AmcContractViewSet, basename="amc-contract")
router.register("equipment-licences", views.EquipmentLicenceViewSet, basename="equipment-licence")

urlpatterns = [
    path("equipment/<uuid:public_id>/coverage/", views.EquipmentCoverageViewSet.as_view({"get": "coverage"}),
         name="equipment-coverage"),
    path("compliance/due/", views.ComplianceDueViewSet.as_view({"get": "list"}), name="compliance-due"),
    *router.urls,
]