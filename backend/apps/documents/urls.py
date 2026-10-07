from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("documents", views.DocumentViewSet, basename="document")

urlpatterns = [
    path("documents/download/<str:token>/", views.DocumentDownloadView.as_view(), name="document-download"),
] + router.urls