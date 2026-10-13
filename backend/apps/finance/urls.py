from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("depreciation-policies", views.DepreciationPolicyViewSet, basename="depreciation-policy")
router.register("depreciation/runs", views.DepreciationRunViewSet, basename="depreciation-run")
router.register("condemnation-requests", views.CondemnationRequestViewSet, basename="condemnation-request")
router.register("disposals", views.DisposalViewSet, basename="disposal")
router.register("replacement-plans", views.ReplacementPlanViewSet, basename="replacement-plan")

EQ = views.EquipmentFinanceViewSet

urlpatterns = [
    # /equipment/<id>/... routes are registered before the equipment detail route (see config/urls.py include order).
    path("equipment/<uuid:public_id>/finance/", EQ.as_view({"get": "finance"}), name="equipment-finance"),
    path("equipment/<uuid:public_id>/depreciation/", EQ.as_view({"get": "depreciation"}),
         name="equipment-depreciation"),
    path("equipment/<uuid:public_id>/tco/", EQ.as_view({"get": "tco"}), name="equipment-tco"),
    path("equipment/<uuid:public_id>/tco-snapshots/", EQ.as_view({"get": "tco_snapshots"}),
         name="equipment-tco-snapshots"),
    path("equipment/<uuid:public_id>/opening-book-value/", EQ.as_view({"post": "opening_book_value"}),
         name="equipment-opening-book-value"),
    path("equipment/<uuid:public_id>/condemnation-check/", EQ.as_view({"get": "condemnation_check"}),
         name="equipment-condemnation-check"),
    path("finance-settings/", views.FinanceSettingsViewSet.as_view(
        {"get": "retrieve_settings", "put": "upsert"}), name="finance-settings"),
    path("depreciation/run/", views.DepreciationRunActionViewSet.as_view({"post": "run"}), name="depreciation-run-now"),
    path("tco/generate/", views.TcoActionViewSet.as_view({"post": "generate"}), name="tco-generate"),
    path("finance/summary/", views.FinanceSummaryViewSet.as_view({"get": "summary"}), name="finance-summary"),
    path("replacement-candidates/", views.ReplacementCandidateViewSet.as_view({"get": "list"}),
         name="replacement-candidates"),
    *router.urls,
]
