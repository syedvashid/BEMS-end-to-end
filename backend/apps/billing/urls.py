from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    AllocationChargePreviewView, ChargeCalculatorView, ChargeItemViewSet, ChargeMappingViewSet, ChargeRecordViewSet,
    ChargeSettingsView, EquipmentChargesView,
)

router = SimpleRouter()
router.register("charge-items", ChargeItemViewSet, basename="charge-item")
router.register("charge-mappings", ChargeMappingViewSet, basename="charge-mapping")
router.register("charge-records", ChargeRecordViewSet, basename="charge-record")

urlpatterns = [
    path("charge-settings/", ChargeSettingsView.as_view(), name="charge-settings"),
    path("charges/calculator/", ChargeCalculatorView.as_view(), name="charge-calculator"),
    path("allocations/<uuid:public_id>/charge-preview/", AllocationChargePreviewView.as_view(), name="allocation-charge-preview"),
    path("equipment/<uuid:public_id>/charges/", EquipmentChargesView.as_view(), name="equipment-charges"),
] + router.urls
