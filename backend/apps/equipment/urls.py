from rest_framework.routers import SimpleRouter

from .views import EquipmentViewSet

router = SimpleRouter()
router.register("equipment", EquipmentViewSet, basename="equipment")

urlpatterns = router.urls
