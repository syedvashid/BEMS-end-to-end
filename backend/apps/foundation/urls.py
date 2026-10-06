from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import AuditLogViewSet, FacilityViewSet, MeView, PermissionViewSet, RoleViewSet, UserViewSet

router = SimpleRouter()
router.register("facilities", FacilityViewSet, basename="facility")
router.register("users", UserViewSet, basename="user")
router.register("roles", RoleViewSet, basename="role")
router.register("permissions", PermissionViewSet, basename="permission")
router.register("audit-logs", AuditLogViewSet, basename="audit-log")

urlpatterns = [path("me/", MeView.as_view(), name="me")] + router.urls