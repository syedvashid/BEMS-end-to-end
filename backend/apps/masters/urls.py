from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("departments", views.DepartmentViewSet, basename="department")
router.register("locations", views.LocationViewSet, basename="location")
router.register("equipment-categories", views.EquipmentCategoryViewSet, basename="equipment-category")
router.register("vendors", views.VendorViewSet, basename="vendor")
router.register("vendor-contacts", views.VendorContactViewSet, basename="vendor-contact")
router.register("funding-sources", views.FundingSourceViewSet, basename="funding-source")
router.register("equipment-models", views.EquipmentModelViewSet, basename="equipment-model")

urlpatterns = router.urls