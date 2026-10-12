from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    AllocationViewSet, MyDepartmentsView, ReservationViewSet, TransferRequestViewSet, UsageLogViewSet,
    UserDepartmentsView,
)

router = SimpleRouter()
router.register("allocations", AllocationViewSet, basename="allocation")
router.register("reservations", ReservationViewSet, basename="reservation")
router.register("usage-logs", UsageLogViewSet, basename="usage-log")
router.register("transfer-requests", TransferRequestViewSet, basename="transfer-request")

urlpatterns = [
    path("users/<uuid:public_id>/departments/", UserDepartmentsView.as_view(), name="user-departments"),
    path("my-departments/", MyDepartmentsView.as_view(), name="my-departments"),
] + router.urls