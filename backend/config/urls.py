from django.conf import settings
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

handler404 = "apps.core.errors.not_found"
handler500 = "apps.core.errors.server_error"

urlpatterns = [
    path("api/v1/", include("apps.core.urls")),
    path("api/v1/", include("apps.foundation.urls")),
    path("api/v1/", include("apps.masters.urls")),
]

if settings.DEBUG:  # API docs only in DEBUG
    urlpatterns += [
        path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
        path("api/v1/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
       
    ]