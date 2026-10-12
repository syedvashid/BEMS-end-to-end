from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("incidents", views.IncidentViewSet, basename="incident")
router.register("recall-notices", views.RecallNoticeViewSet, basename="recall-notice")
router.register("verifications", views.VerificationViewSet, basename="verification")

urlpatterns = [
    # Registered before the equipment detail route (see config/urls.py include order).
    path("equipment/<uuid:public_id>/safety/", views.EquipmentSafetyViewSet.as_view({"get": "safety"}),
         name="equipment-safety"),
    *router.urls,
]
