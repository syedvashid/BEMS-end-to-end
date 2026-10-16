"""Routes. Include this app BEFORE foundation and equipment in config/urls.py: /audit-logs/ replaces the Phase 1
list/detail routes, and /equipment/<id>/performance|audit/ must be matched before the equipment detail route."""
from django.urls import path

from . import views

UUID = "<uuid:public_id>"

urlpatterns = [
    # dashboards
    path("dashboards/executive/", views.DashboardView.as_view({"get": "executive"})),
    path("dashboards/operations/", views.DashboardView.as_view({"get": "operations"})),
    path("dashboards/utilization/", views.DashboardView.as_view({"get": "utilization"})),
    path("dashboards/finance/", views.DashboardView.as_view({"get": "finance"})),
    path("dashboards/analytics/", views.DashboardView.as_view({"get": "analytics"})),
    # statistics
    path("stats/rebuild/", views.StatsView.as_view({"post": "rebuild"})),
    path("stats/status/", views.StatsView.as_view({"get": "status"})),
    # equipment extras (before the equipment detail route)
    path(f"equipment/{UUID}/performance/", views.EquipmentExtrasView.as_view({"get": "performance"})),
    path(f"equipment/{UUID}/audit/", views.EquipmentExtrasView.as_view({"get": "audit"})),
    # downtime and utilization tables
    path("downtime/", views.KpiTablesView.as_view({"get": "downtime"})),
    path("utilization/", views.KpiTablesView.as_view({"get": "utilization"})),
    # report center (download route first: it would otherwise match <code>)
    path("reports/download/<str:token>/", views.ReportDownloadView.as_view(), name="report-download"),
    path("reports/", views.ReportsEndpoints.as_view({"get": "list"})),
    path("reports/<str:code>/", views.ReportsEndpoints.as_view({"get": "retrieve"})),
    path("reports/<str:code>/data/", views.ReportsEndpoints.as_view({"get": "data"})),
    path("reports/<str:code>/export/", views.ReportsEndpoints.as_view({"post": "export"})),
    path("report-runs/", views.ReportRunsView.as_view({"get": "list"})),
    path(f"report-runs/{UUID}/", views.ReportRunsView.as_view({"get": "retrieve"})),
    path(f"report-runs/{UUID}/download-link/", views.ReportRunsView.as_view({"post": "download_link"})),
    # audit trail viewer
    path("audit-logs/", views.AuditLogsView.as_view({"get": "list"})),
    path("audit-logs/facets/", views.AuditLogsView.as_view({"get": "facets"})),
    path("audit-logs/verify-chain/", views.AuditLogsView.as_view({"post": "verify_chain"})),
    path("audit-logs/<int:pk>/", views.AuditLogsView.as_view({"get": "retrieve"})),
]
