"""Report running and exporting (B7). Views stay thin; everything that changes data is here."""
import logging
import re
from datetime import timedelta
from itertools import islice

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.core import audit
from apps.documents import storage
from apps.foundation.context import resolve_context
from apps.foundation.models import Facility, User

from . import export, registry
from .models import ReportRun

log = logging.getLogger(__name__)
GENERIC_FAILURE = "The report could not be generated."


class ContextShim:
    """Lets resolve_context() build a RequestContext for a user and facility outside a request."""
    def __init__(self, user, facility_public_id):
        self.user = user
        self.headers = {"X-Facility-Id": str(facility_public_id)}


def build_context(user, facility_public_id):
    return resolve_context(ContextShim(user, facility_public_id), True)


def retention_days():
    return int(getattr(settings, "BEMS_REPORT_RETENTION_DAYS", 14))


def _defn_or_404(code):
    defn = registry.get(code)
    if defn is None:
        raise NotFound()
    return defn


def get_runnable(code, ctx, base="report.view"):
    """Definition if the user may run it, else 404 (existence is not revealed)."""
    defn = _defn_or_404((code or "").upper())
    if not registry.can_run(defn, ctx, base):
        raise NotFound()
    return defn


# ------------------------------------------------------------------ on-screen
def run_for_screen(defn, ctx, raw_params):
    facility = ctx.facility
    clean, norm = registry.validate_params(defn, facility, raw_params)
    columns = registry.visible_columns(defn, clean, ctx)
    rc = registry.RunContext(facility, ctx, clean)
    rows, summary = defn.run(rc)
    cap = registry.max_rows()
    table = registry.tabulate(rows, columns, rc.tz, cap)
    return columns, table, registry.resolve_summary(summary, rc.tz), norm


# ------------------------------------------------------------------ export
def _params_text(norm):
    return "; ".join(f"{k}: {v}" for k, v in norm.items())


def _complete(run, defn, columns, table, summary, ctx, username):
    """Write the file, store it, mark the run COMPLETED."""
    facility = ctx.facility
    tmp = storage.temp_path()
    try:
        title = run.report_name
        if run.format == "CSV":
            export.write_csv(tmp, columns, table)
        elif run.format == "XLSX":
            export.write_xlsx(tmp, title, columns, table, summary)
        else:
            export.write_pdf(tmp, title=title, facility_name=facility.name, params_text=_params_text(run.parameters),
                             generated_by=username, generated_at=timezone.now().astimezone(
                                 registry.facility_tz(facility)).strftime("%Y-%m-%d %H:%M"),
                             columns=columns, rows=table, summary=summary)
        stored = storage.store_generated_file(tmp, facility.public_id, export.CONTENT_TYPES[run.format])
    finally:
        tmp.unlink(missing_ok=True)
    now = timezone.now()
    run.status = "COMPLETED"
    run.row_count = len(table)
    run.original_filename = f"{run.report_code.lower()}_{now:%Y%m%d_%H%M}.{export.EXTENSIONS[run.format]}"
    run.storage_key, run.file_size_bytes, run.sha256 = stored.key, stored.size, stored.sha256
    run.finished_at, run.expires_at, run.error_message = now, now + timedelta(days=retention_days()), None
    run.save(update_fields=["status", "row_count", "original_filename", "storage_key", "file_size_bytes", "sha256",
                            "finished_at", "expires_at", "error_message"])


def _fail(run, message):
    run.status, run.finished_at, run.error_message = "FAILED", timezone.now(), (message or GENERIC_FAILURE)[:300]
    run.save(update_fields=["status", "finished_at", "error_message"])


def _first_message(exc):
    detail = exc.detail
    while isinstance(detail, dict):
        detail = next(iter(detail.values()), "")
    while isinstance(detail, list):
        detail = detail[0] if detail else ""
    return str(detail)


def create_export(request, defn, fmt, raw_params):
    ctx = request.bems
    facility, user = ctx.facility, request.user
    fmt = (fmt or "").upper()
    if fmt not in registry.FORMATS:
        raise ValidationError({"format": ["Must be CSV, XLSX or PDF."]})
    clean, norm = registry.validate_params(defn, facility, raw_params)
    columns = registry.visible_columns(defn, clean, ctx)
    rc = registry.RunContext(facility, ctx, clean)
    rows, summary = defn.run(rc)
    inline = registry.inline_rows()
    quick = list(islice(rows, inline + 1))
    if fmt == "PDF" and len(quick) > registry.pdf_max_rows():
        raise ValidationError({"format": [
            f"PDF exports are limited to {registry.pdf_max_rows()} rows. Use Excel or CSV for larger reports."]})
    small = len(quick) <= inline
    with transaction.atomic():
        run = ReportRun.objects.create(
            facility=facility, report_code=defn.code, report_name=defn.name, parameters=norm, format=fmt,
            status="RUNNING" if small else "QUEUED", started_at=timezone.now() if small else None,
            created_by=user.id, updated_by=user.id)
        audit.record(request=request, action="REPORT_EXPORTED", facility_id=facility.id, entity_type="ReportRun",
                     entity_public_id=run.public_id, new={"report": defn.code, "format": fmt, "parameters": norm})
    if small:
        try:
            table = registry.tabulate(quick, columns, rc.tz, registry.max_rows())
            _complete(run, defn, columns, table, registry.resolve_summary(summary, rc.tz), ctx, user.username)
        except ValidationError as exc:
            _fail(run, _first_message(exc))
        except Exception:
            log.exception("inline report generation failed (run %s)", run.public_id)
            _fail(run, GENERIC_FAILURE)
    return run


# ------------------------------------------------------------------ queue worker
def claim_next():
    """Flip one QUEUED run to RUNNING (SKIP LOCKED) and return its id; None when the queue is empty."""
    with transaction.atomic():
        run = (ReportRun.objects.select_for_update(skip_locked=True, of=("self",))
               .filter(status="QUEUED", is_active=True).order_by("requested_at", "id").first())
        if run is None:
            return None
        run.status, run.started_at = "RUNNING", timezone.now()
        run.save(update_fields=["status", "started_at"])
        return run.pk


def process_run(run_id):
    """Generate one claimed run. Returns True on success."""
    run = ReportRun.objects.select_related("facility").get(pk=run_id)
    try:
        user = User.objects.filter(pk=run.created_by, is_active=True).first()
        if user is None:
            raise NotFound()
        ctx = build_context(user, run.facility.public_id)            # same rules as at request time
        defn = registry.get(run.report_code)
        if defn is None or not registry.can_run(defn, ctx, "report.export"):
            raise NotFound()
        clean, _ = registry.validate_params(defn, ctx.facility, run.parameters)
        columns = registry.visible_columns(defn, clean, ctx)
        rc = registry.RunContext(ctx.facility, ctx, clean)
        rows, summary = defn.run(rc)
        table = registry.tabulate(rows, columns, rc.tz, registry.max_rows())
        if run.format == "PDF" and len(table) > registry.pdf_max_rows():
            raise ValidationError({"format": [f"PDF exports are limited to {registry.pdf_max_rows()} rows."]})
        _complete(run, defn, columns, table, registry.resolve_summary(summary, rc.tz), ctx, user.username)
        return True
    except ValidationError as exc:
        _fail(run, _first_message(exc))
    except Exception:
        log.exception("report run %s failed", run.public_id)
        _fail(run, GENERIC_FAILURE)
    return False


def fail_stuck(minutes=30):
    cutoff = timezone.now() - timedelta(minutes=minutes)
    n = 0
    for run in ReportRun.objects.filter(status="RUNNING", started_at__lt=cutoff):
        _fail(run, "The report timed out.")
        n += 1
    return n


# ------------------------------------------------------------------ purge
def purge_expired(days=None):
    days = retention_days() if days is None else days
    now = timezone.now()
    cutoff = now - timedelta(days=days)
    from django.db.models import Q
    runs = list(ReportRun.objects.filter(status="COMPLETED", storage_key__isnull=False).filter(
        Q(expires_at__lt=now) | Q(finished_at__lt=cutoff)))
    per_facility = {}
    for run in runs:
        storage.delete_stored(run.storage_key)
        run.status, run.storage_key = "EXPIRED", None
        run.save(update_fields=["status", "storage_key"])
        per_facility[run.facility_id] = per_facility.get(run.facility_id, 0) + 1
    for fid, n in per_facility.items():
        with transaction.atomic():
            audit.record(action="REPORT_FILES_PURGED", facility_id=fid, entity_type="ReportRun",
                         new={"files_deleted": n, "retention_days": days})
    return len(runs)


# ------------------------------------------------------------------ run listing and downloads
def runs_for(ctx, user):
    qs = ReportRun.objects.filter(facility_id=ctx.facility.id, is_active=True)
    if not (ctx.has("report.export") and ({"SYSTEM_ADMIN", "BIOMED_ADMIN"} & set(ctx.role_codes))):
        qs = qs.filter(created_by=user.id)
    return qs.order_by("-requested_at", "-id")


def download_allowed(run, ctx, user):
    """Shared by link creation and the token endpoint: all failures mean one generic 404."""
    defn = registry.get(run.report_code)
    return bool(
        defn is not None and run.status == "COMPLETED" and run.storage_key
        and run.expires_at is not None and run.expires_at > timezone.now()
        and run.facility_id == ctx.facility.id and run.created_by == user.id
        and ctx.has("report.export") and registry.can_run(defn, ctx, "report.export"))
