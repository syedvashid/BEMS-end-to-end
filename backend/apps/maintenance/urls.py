from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("checklist-templates", views.ChecklistTemplateViewSet, basename="checklist-template")
router.register("maintenance-plans", views.MaintenancePlanViewSet, basename="maintenance-plan")
router.register("work-orders", views.WorkOrderViewSet, basename="work-order")
router.register("spare-parts", views.SparePartViewSet, basename="spare-part")

urlpatterns = router.urls
