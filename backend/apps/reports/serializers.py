"""Explicit output fields only (no model serializers, nothing is accepted from payloads here)."""
from . import registry
from .common import facility_today


def column_dict(c):
    return {"key": c.key, "label": c.label, "type": c.type}


def param_dict(p, today):
    default = p.default(today) if callable(p.default) else p.default
    if hasattr(default, "isoformat"):
        default = default.isoformat()
    return {"name": p.name, "label": p.label, "type": p.type, "required": p.required,
            "choices": list(p.choices), "entity": p.entity, "default": default, "min": p.min, "max": p.max}


def definition_summary(d):
    return {"code": d.code, "name": d.name, "category": d.category, "description": d.description}


def definition_detail(d, ctx):
    columns = [c for c in d.columns if not (c.finance and not ctx.has("finance.view"))]
    return {**definition_summary(d),
            "formats": list(registry.FORMATS) if registry.can_run(d, ctx, "report.export") else [],
            "parameters": [param_dict(p, facility_today(ctx.facility)) for p in d.params],
            "columns": [column_dict(c) for c in columns]}


def run_dict(run, usernames=None):
    return {"public_id": str(run.public_id), "report_code": run.report_code, "report_name": run.report_name,
            "parameters": run.parameters, "format": run.format, "status": run.status, "row_count": run.row_count,
            "file_size_bytes": run.file_size_bytes, "original_filename": run.original_filename,
            "requested_at": run.requested_at, "started_at": run.started_at, "finished_at": run.finished_at,
            "expires_at": run.expires_at, "error_message": run.error_message,
            "requested_by": (usernames or {}).get(run.created_by)}


def audit_row(a, detail=False):
    d = {"id": a.id, "occurred_at": a.occurred_at, "actor_username": a.actor_username, "action": a.action,
         "entity_type": a.entity_type, "entity_public_id": a.entity_public_id,
         "changed_fields": a.changed_fields or [], "request_id": a.request_id, "http_method": a.http_method,
         "request_path": a.request_path}
    if detail:
        d["previous_value"] = a.previous_value
        d["new_value"] = a.new_value
    return d
