from dataclasses import dataclass

from rest_framework.exceptions import NotFound


@dataclass(frozen=True)
class Attachable:
    entity_type: str
    model: type
    view_permission: str
    attach_permission: str
    label_field: str | None = None   # optional: column used to show a readable name


_REGISTRY: dict[str, Attachable] = {}


def register_attachable(entity_type, model, view_permission, attach_permission, label_field=None):
    _REGISTRY[entity_type] = Attachable(entity_type, model, view_permission, attach_permission, label_field)


def get_attachable(entity_type):
    return _REGISTRY.get(entity_type)


def all_attachables():
    return dict(_REGISTRY)


def resolve_target(att, public_id, facility):
    """Target must exist, be active and belong to the current facility, else 404."""
    qs = att.model.objects.filter(public_id=public_id, facility_id=facility.id)
    if any(f.name == "is_active" for f in att.model._meta.concrete_fields):
        qs = qs.filter(is_active=True)
    obj = qs.first()
    if obj is None:
        raise NotFound()
    return obj


def labels_for(docs, facility_id):
    """{str(entity_public_id): label} for a batch of documents (one query per entity type)."""
    out, by_type = {}, {}
    for d in docs:
        by_type.setdefault(d.entity_type, set()).add(d.entity_public_id)
    for etype, ids in by_type.items():
        att = _REGISTRY.get(etype)
        if att is None or not att.label_field or facility_id is None:
            continue
        rows = att.model.objects.filter(facility_id=facility_id, public_id__in=ids).values_list(
            "public_id", att.label_field)
        out.update({str(pid): label for pid, label in rows})
    return out