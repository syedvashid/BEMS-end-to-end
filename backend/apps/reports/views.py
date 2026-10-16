"""Views are thin; logic lives in services, stats, dashboards, downtime and registry.

Permissions: every view here gates itself in initial() with an any-of list per action (the stock BemsPermission mapping
holds one code per action, which cannot express 'usage.view or allocation.view'). Facility context comes from the
existing resolve_context(); denials go through the existing deny() so the ACCESS_DENIED audit row is still written."""
import logging
import uuid
from datetime import datetime, timedelta

from django.core import signing
from django.db import connection
from django.http import FileResponse
from django.urls import reverse
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.exceptions import NotAuthenticated, NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import audit
from apps.documents import storage
from apps.equipment.models import Equipment
from apps.foundation.context import resolve_context
from apps.foundation.models import AuditLog, User
from apps.foundation.permissions import deny

from . import dashboards, registry, services, tokens
from .common import (day_start, equipment_filter, facility_today, facility_tz, get_scoped, paginate, parse_date,
                     page_number, parse_int, split_multi)
from .downtime import combine, compute_rows, equipment_kpi_rows, failure_stats, kpis, sums_from_rows
from .export import CONTENT_TYPES
from .models import ReportRun
from .serializers import audit_row, definition_detail, definition_summary, run_dict
from .stats import latest_stat_date, rebuild_daily_stats, stats_status

log = logging.getLogger(__name__)


class ReportsView(viewsets.ViewSet):
    permission_classes = []          # gating is done in initial()
    gate = {}                        # action -> tuple of codes (any-of); () = authenticated member only

    @property
    def ctx(self):
        return self.request.bems

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not getattr(request.user, "is_authenticated", False):
            raise NotAuthenticated()
        request.bems = resolve_context(request, True)       # 400 facility_required / 404 for non-members
        codes = self.gate.get(self.action)
        if codes is None:
            raise PermissionDenied()                          # an undeclared action is denied
        if codes and not any(request.bems.has(c) for c in codes):
            deny(request, self, self.action, tuple(codes), reason="missing_permission")
            raise PermissionDenied()

    def require(self, request, codes, reason="missing_permission"):
        if not any(self.ctx.has(c) for c in codes):
            deny(request, self, self.action, tuple(codes), reason=reason)
            raise PermissionDenied()

    def runnable(self, request, code, base):
        defn = registry.get((code or "").upper())
        if defn is None:
            raise NotFound()
        if not registry.can_run(defn, self.ctx, base):
            self.require(request, (base, *defn.permissions, *defn.any_of), reason="report_permission")
            raise PermissionDenied()
        return defn


def _strict_body(request, allowed):
    data = request.data
    if not isinstance(data, dict):
        raise ValidationError({"non_field_errors": ["Expected a JSON object."]})
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        raise ValidationError({k: ["Unknown field."] for k in unknown})
    return data


# ================================================================== dashboards
class DashboardView(ReportsView):
    gate = {"executive": ("equipment.view",), "operations": ("work_order.view",),
            "utilization": ("usage.view", "allocation.view"), "finance": ("finance.view",),
            "analytics": ("work_order.view",)}

    def _dash(self, request, name):
        widgets = dashboards.BUILDERS[name](self.ctx.facility, self.ctx, request.query_params)
        if not widgets:
            self.require(request, ("__none__",), reason="no_visible_widgets")
        return Response({"generated_at": timezone.now(), "data_up_to": latest_stat_date(self.ctx.facility),
                         "widgets": widgets})

    def executive(self, request):
        return self._dash(request, "executive")

    def operations(self, request):
        return self._dash(request, "operations")

    def utilization(self, request):
        return self._dash(request, "utilization")

    def finance(self, request):
        return self._dash(request, "finance")

    def analytics(self, request):
        return self._dash(request, "analytics")


# ================================================================== statistics
class StatsView(ReportsView):
    gate = {"rebuild": ("stats.run",),
            "status": ("stats.run", "equipment.view", "work_order.view", "usage.view", "allocation.view",
                       "finance.view")}

    def rebuild(self, request):
        data = _strict_body(request, {"from", "to"})
        facility = self.ctx.facility
        d_from, d_to = parse_date(data.get("from"), "from"), parse_date(data.get("to"), "to")
        if d_to > facility_today(facility):
            raise ValidationError({"to": ["Cannot be in the future."]})
        return Response(rebuild_daily_stats(facility, d_from, d_to, request=request))

    def status(self, request):
        s = stats_status(self.ctx.facility)
        return Response({"latest_date": s["latest_date"], "data_up_to": s["latest_date"],
                         "computed_at": s["computed_at"]})


# ================================================================== equipment performance and audit
class EquipmentExtrasView(ReportsView):
    gate = {"performance": ("equipment.view",), "audit": ("audit.view",)}

    def _equipment(self, public_id):
        e = Equipment.objects.filter(facility_id=self.ctx.facility.id, public_id=public_id, is_active=True).first()
        if e is None:
            raise NotFound()
        return e

    def performance(self, request, public_id=None):
        facility, eq = self.ctx.facility, self._equipment(public_id)
        today = facility_today(facility)
        d_to = parse_date(request.query_params["to"], "to") if request.query_params.get("to") else today
        d_from = parse_date(request.query_params["from"], "from") if request.query_params.get("from") \
            else d_to - timedelta(days=89)
        if d_from > d_to or (d_to - d_from).days > 365:
            raise ValidationError({"from": ["Invalid range (at most 366 days)."]})
        rows = compute_rows(facility, [eq.pk], d_from, d_to)      # live for one equipment, so today is included
        sums = sums_from_rows(rows) if rows else combine([])
        f = failure_stats(facility, Equipment.objects.filter(pk=eq.pk), d_from, d_to).get(eq.pk, [0, 0.0, 0])
        return Response({
            "from": d_from, "to": d_to, "has_service_window": bool(rows), **kpis(sums, f[0], f[1], f[2]),
            "in_service_hours": round(sums["in_service"] / 60, 2), "used_hours": round(sums["used"] / 60, 2),
            "series": [{"date": r["stat_date"], "used_minutes": r["used_minutes"],
                        "available_minutes": r["available_minutes"],
                        "downtime_minutes": r["downtime_planned_minutes"] + r["downtime_unplanned_minutes"],
                        "planned_minutes": r["downtime_planned_minutes"],
                        "unplanned_minutes": r["downtime_unplanned_minutes"]} for r in rows]})

    def audit(self, request, public_id=None):
        eq = self._equipment(public_id)
        qs = AuditLog.objects.filter(facility_id=self.ctx.facility.id, entity_public_id=eq.public_id) \
            .order_by("-occurred_at", "-id")
        page = paginate(request, qs)
        page["results"] = [audit_row(a) for a in page["results"]]
        if page_number(request) == 1:
            audit.record(request=request, action="AUDIT_LOG_VIEWED", facility_id=self.ctx.facility.id,
                         entity_type="AuditLog", new={"equipment": str(eq.public_id), "page": 1})
        return Response(page)


# ================================================================== downtime and utilization tables
KPI_ORDER = {"availability_percent", "uptime_percent", "utilization_percent", "occupancy_percent", "failures",
             "mtbf_hours", "mttr_hours", "in_service_hours", "planned_downtime_hours", "unplanned_downtime_hours",
             "available_hours", "used_hours", "allocated_hours", "sessions", "asset_tag", "name"}


class KpiTablesView(ReportsView):
    gate = {"downtime": ("work_order.view", "equipment.view"), "utilization": ("usage.view", "allocation.view")}

    def _table(self, request, default_order):
        q, facility = request.query_params, self.ctx.facility
        today = facility_today(facility)
        d_to = parse_date(q["to"], "to") if q.get("to") else today - timedelta(days=1)
        d_from = parse_date(q["from"], "from") if q.get("from") else d_to - timedelta(days=29)
        if d_from > d_to or (d_to - d_from).days > 365:
            raise ValidationError({"from": ["Invalid range (at most 366 days)."]})
        ref = lambda name, model_name: get_scoped(registry._entity_model(model_name), facility, q[name], name) \
            if q.get(name) else None
        eq_qs = equipment_filter(facility, category=ref("category", "category"), department=ref("department", "department"),
                                 location=ref("location", "location"), equipment=ref("equipment", "equipment"))
        rows = equipment_kpi_rows(facility, eq_qs, d_from, d_to)
        order = q.get("ordering") or default_order
        key, desc = order.lstrip("-"), order.startswith("-")
        if key not in KPI_ORDER:
            raise ValidationError({"ordering": ["Unknown ordering."]})
        present = [r for r in rows if r[key] is not None]
        present.sort(key=lambda r: r[key], reverse=desc)
        rows = present + [r for r in rows if r[key] is None]
        for r in rows:
            r.pop("equipment_id", None)
        page = paginate(request, rows)
        page.update({"from": d_from, "to": d_to, "data_up_to": latest_stat_date(facility)})
        return Response(page)

    def downtime(self, request):
        return self._table(request, "-unplanned_downtime_hours")

    def utilization(self, request):
        return self._table(request, "utilization_percent")


# ================================================================== report center
class ReportsEndpoints(ReportsView):
    gate = {"list": ("report.view",), "retrieve": ("report.view",), "data": ("report.view",),
            "export": ("report.export",)}

    def list(self, request):
        groups = {}
        for d in registry.visible(self.ctx):
            groups.setdefault(d.category, []).append(definition_summary(d))
        return Response({"groups": [{"category": c, "reports": r} for c, r in sorted(groups.items())]})

    def retrieve(self, request, code=None):
        return Response(definition_detail(self.runnable(request, code, "report.view"), self.ctx))

    def data(self, request, code=None):
        defn = self.runnable(request, code, "report.view")
        columns, table, summary, norm = services.run_for_screen(defn, self.ctx, request.query_params.dict())
        keys = [c.key for c in columns]
        page = paginate(request, [dict(zip(keys, r)) for r in table])
        page.update({"columns": [{"key": c.key, "label": c.label, "type": c.type} for c in columns],
                     "summary": summary, "parameters": norm})
        return Response(page)

    def export(self, request, code=None):
        defn = self.runnable(request, code, "report.export")
        data = _strict_body(request, {"format", "parameters"})
        params = data.get("parameters") or {}
        if not isinstance(params, dict):
            raise ValidationError({"parameters": ["Expected an object."]})
        run = services.create_export(request, defn, data.get("format"), params)
        return Response(run_dict(run), status=201)


class ReportRunsView(ReportsView):
    gate = {"list": ("report.export",), "retrieve": ("report.export",), "download_link": ("report.export",)}

    def _usernames(self, runs):
        ids = {r.created_by for r in runs if r.created_by}
        return dict(User.objects.filter(pk__in=ids).values_list("pk", "username"))

    def list(self, request):
        qs = services.runs_for(self.ctx, request.user)
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"].upper())
        if request.query_params.get("report_code"):
            qs = qs.filter(report_code=request.query_params["report_code"].upper())
        page = paginate(request, qs)
        names = self._usernames(page["results"])
        page["results"] = [run_dict(r, names) for r in page["results"]]
        return Response(page)

    def _run(self, public_id):
        run = services.runs_for(self.ctx, self.request.user).filter(public_id=public_id).first()
        if run is None:
            raise NotFound()
        return run

    def retrieve(self, request, public_id=None):
        run = self._run(public_id)
        return Response(run_dict(run, self._usernames([run])))

    def download_link(self, request, public_id=None):
        run = self._run(public_id)
        if not services.download_allowed(run, self.ctx, request.user):
            raise NotFound()
        token, expires = tokens.issue(run.public_id, self.ctx.facility.public_id, request.user.public_id)
        return Response({"url": reverse("report-download", kwargs={"token": token}),
                         "expires_at": expires.isoformat()})


class ReportDownloadView(APIView):
    """Header-less. The token is the credential; every failure is the same generic 404."""
    authentication_classes = []
    permission_classes = []

    def perform_content_negotiation(self, request, force=False):
        return super().perform_content_negotiation(request, force=True)

    def get(self, request, token):
        try:
            data = tokens.read(token)
            run_id, fac_id, user_id = (uuid.UUID(data[k]) for k in ("r", "f", "u"))
        except (signing.BadSignature, KeyError, TypeError, ValueError):
            raise NotFound()
        run = ReportRun.objects.select_related("facility").filter(
            public_id=run_id, facility__public_id=fac_id, is_active=True).first()
        user = User.objects.filter(public_id=user_id, is_active=True).first()
        if run is None or user is None:
            raise NotFound()
        try:
            ctx = services.build_context(user, fac_id)
        except Exception:
            raise NotFound()
        if not services.download_allowed(run, ctx, user):
            raise NotFound()
        try:
            fh = storage.open_for_read(run.storage_key)
        except (FileNotFoundError, OSError):
            log.error("report file missing for run %s", run.public_id)
            raise NotFound()
        try:
            audit.record(request=request, actor=user, action="REPORT_DOWNLOADED", facility_id=ctx.facility.id,
                         entity_type="ReportRun", entity_public_id=run.public_id,
                         new={"report": run.report_code, "format": run.format, "file": run.original_filename})
        except BaseException:
            fh.close()
            raise
        resp = FileResponse(fh, as_attachment=True, filename=run.original_filename,
                            content_type=CONTENT_TYPES[run.format])
        resp["X-Content-Type-Options"] = "nosniff"
        resp["Cache-Control"] = "no-store"
        return resp


# ================================================================== audit trail viewer
def _dt(raw, tz, name, end):
    """-> (aware datetime, exclusive?) ; a bare date covers the whole facility-timezone day."""
    s = str(raw).strip()
    if "T" in s or " " in s:
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            raise ValidationError({name: ["Enter a valid date or date-time."]})
        return (dt if dt.tzinfo else dt.replace(tzinfo=tz)), False
    d = parse_date(s, name)
    return (day_start(d + timedelta(days=1), tz), True) if end else (day_start(d, tz), False)


def verify_chain():
    with connection.cursor() as cur:
        cur.execute("select * from verify_audit_chain()")
        rows, cols = cur.fetchall(), [c.name for c in cur.description]
    if not rows:
        return {"ok": True, "first_broken_id": None}
    row = rows[0]
    if len(cols) >= 2:
        d = dict(zip(cols, row))
        ok = d["ok"] if "ok" in d else row[0]
        broken = d.get("first_broken_id", row[1])
        return {"ok": bool(ok), "first_broken_id": None if ok else broken}
    v = row[0]
    if isinstance(v, bool):
        return {"ok": v, "first_broken_id": None}
    return {"ok": v is None, "first_broken_id": v}


class AuditLogsView(ReportsView):
    gate = {"list": ("audit.view",), "retrieve": ("audit.view",), "facets": ("audit.view",),
            "verify_chain": ("audit.verify",)}

    def _scoped(self):
        return AuditLog.objects.filter(facility_id=self.ctx.facility.id)

    def list(self, request):
        q, tz = request.query_params, facility_tz(self.ctx.facility)
        qs, filters = self._scoped(), {}
        types, actions = split_multi(request, "entity_type"), split_multi(request, "action")
        if types:
            qs, filters["entity_type"] = qs.filter(entity_type__in=types), types
        if actions:
            qs, filters["action"] = qs.filter(action__in=actions), actions
        if q.get("actor"):
            qs, filters["actor"] = qs.filter(actor_username__icontains=q["actor"].strip()), q["actor"].strip()
        if q.get("request_id"):
            qs, filters["request_id"] = qs.filter(request_id=q["request_id"].strip()), q["request_id"].strip()
        if q.get("entity_public_id"):
            try:
                eid = uuid.UUID(q["entity_public_id"])
            except ValueError:
                raise ValidationError({"entity_public_id": ["Enter a valid id."]})
            qs, filters["entity_public_id"] = qs.filter(entity_public_id=eid), str(eid)
        if q.get("occurred_from"):
            dt, _ = _dt(q["occurred_from"], tz, "occurred_from", False)
            qs, filters["occurred_from"] = qs.filter(occurred_at__gte=dt), q["occurred_from"]
        if q.get("occurred_to"):
            dt, exclusive = _dt(q["occurred_to"], tz, "occurred_to", True)
            qs = qs.filter(occurred_at__lt=dt) if exclusive else qs.filter(occurred_at__lte=dt)
            filters["occurred_to"] = q["occurred_to"]
        order = q.get("ordering") or "-occurred_at"
        if order not in ("occurred_at", "-occurred_at"):
            raise ValidationError({"ordering": ["Must be occurred_at or -occurred_at."]})
        qs = qs.order_by(order, order.replace("occurred_at", "id"))
        page = paginate(request, qs)
        page["results"] = [audit_row(a) for a in page["results"]]
        if page_number(request) == 1:      # later pages of the same listing are not audited again
            audit.record(request=request, action="AUDIT_LOG_VIEWED", facility_id=self.ctx.facility.id,
                         entity_type="AuditLog", new={"filters": filters, "page": 1})
        return Response(page)

    def retrieve(self, request, pk=None):
        a = self._scoped().filter(pk=pk).first()
        if a is None:
            raise NotFound()
        audit.record(request=request, action="AUDIT_LOG_VIEWED", facility_id=self.ctx.facility.id,
                     entity_type="AuditLog", new={"audit_log_id": a.id})
        return Response(audit_row(a, detail=True))

    def facets(self, request):
        qs = self._scoped()
        return Response({
            "entity_types": list(qs.exclude(entity_type__isnull=True).values_list("entity_type", flat=True)
                                 .distinct().order_by("entity_type")),
            "actions": list(qs.values_list("action", flat=True).distinct().order_by("action"))})

    def verify_chain(self, request):
        result = verify_chain()
        audit.record(request=request, action="AUDIT_CHAIN_VERIFIED", facility_id=self.ctx.facility.id,
                     entity_type="AuditLog", new=result)
        return Response(result)
