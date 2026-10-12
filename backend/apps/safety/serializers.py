from rest_framework import serializers

from apps.compliance.serializers import PublicRef, StrictSerializer
from apps.equipment.models import Equipment
from apps.equipment.serializers import ref
from apps.foundation.serializers import BlankToNullMixin
from apps.masters.models import Department, EquipmentModel, Location, Vendor

from . import services
from .models import IncidentEvent, RecallNoticeModel

INCIDENT_TYPES = ["MALFUNCTION", "USE_ERROR", "NEAR_MISS", "OTHER"]
SEVERITIES = ["NO_HARM", "MINOR", "MODERATE", "SEVERE", "DEATH"]
NOTICE_TYPES = ["RECALL", "FIELD_SAFETY_NOTICE", "SAFETY_ALERT", "ADVISORY"]
SOURCES = ["MANUFACTURER", "REGULATOR", "INTERNAL"]
URGENCIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
ACTION_TYPES = ["STOP_USE", "INSPECT", "UPDATE_SOFTWARE", "MODIFY", "RETURN", "INFORM_ONLY"]
SCOPE_TYPES = ["FACILITY", "DEPARTMENT", "LOCATION"]
REF_RE = r"^[A-Za-z0-9/_-]{1,40}$"


def _ctx(serializer):
    return getattr(serializer.context.get("request"), "bems", None)


def _opt(**kw):
    return {"required": False, "allow_null": True, **kw}


class _Strict(BlankToNullMixin, StrictSerializer):
    pass


class _Action(_Strict):
    row_version = serializers.IntegerField(required=False, min_value=1)


# ================================================================== incidents (write)
class IncidentCreateSerializer(_Strict):
    equipment = PublicRef(Equipment)
    incident_type = serializers.ChoiceField(choices=INCIDENT_TYPES)
    severity = serializers.ChoiceField(choices=SEVERITIES)
    occurred_at = serializers.DateTimeField()
    reported_by_name = serializers.CharField(max_length=200, **_opt())
    department = PublicRef(Department, required=False, allow_null=True)
    location = PublicRef(Location, required=False, allow_null=True)
    description = serializers.CharField(max_length=4000)
    immediate_action = serializers.CharField(max_length=4000, **_opt())
    patient_reference = serializers.RegexField(REF_RE, **_opt())
    encounter_reference = serializers.RegexField(REF_RE, **_opt())
    patient_affected = serializers.BooleanField(required=False, default=False)
    staff_affected = serializers.BooleanField(required=False, default=False)
    reportable_to_regulator = serializers.BooleanField(required=False, default=False)
    quarantine = serializers.BooleanField(required=False, default=False)


class IncidentUpdateSerializer(_Strict):
    row_version = serializers.IntegerField(required=False, min_value=1)
    incident_type = serializers.ChoiceField(choices=INCIDENT_TYPES, required=False)
    severity = serializers.ChoiceField(choices=SEVERITIES, required=False)
    patient_affected = serializers.BooleanField(required=False)
    staff_affected = serializers.BooleanField(required=False)
    department = PublicRef(Department, required=False, allow_null=True)
    location = PublicRef(Location, required=False, allow_null=True)
    root_cause = serializers.CharField(max_length=4000, **_opt())
    corrective_action = serializers.CharField(max_length=4000, **_opt())
    preventive_action = serializers.CharField(max_length=4000, **_opt())
    investigation_notes = serializers.CharField(max_length=4000, **_opt())
    reportable_to_regulator = serializers.BooleanField(required=False)


class EmptyActionSerializer(_Action):
    """Actions that take no fields (only the optional row_version)."""


class IncidentActionsTakenSerializer(_Action):
    corrective_action = serializers.CharField(max_length=4000, **_opt())


class IncidentCloseSerializer(_Action):
    closure_notes = serializers.CharField(max_length=4000)


class IncidentMarkReportedSerializer(_Action):
    reference = serializers.CharField(max_length=200)
    reported_on = serializers.DateField()


class IncidentReleaseSerializer(_Action):
    reason = serializers.CharField(max_length=1000)


class NoteSerializer(_Strict):
    text = serializers.CharField(max_length=2000)


# ================================================================== incidents (read)
class IncidentListSerializer(serializers.BaseSerializer):
    def to_representation(self, o):
        return {
            "public_id": str(o.public_id), "incident_number": o.incident_number,
            "equipment": {"public_id": str(o.equipment.public_id), "asset_tag": o.equipment.asset_tag,
                          "name": o.equipment.name},
            "incident_type": o.incident_type, "severity": o.severity, "occurred_at": o.occurred_at,
            "status": o.status, "department": ref(o.department, "code", "name"),
            "location": ref(o.location, "code", "name"), "patient_affected": o.patient_affected,
            "staff_affected": o.staff_affected, "reportable_to_regulator": o.reportable_to_regulator,
            "regulator_report_reference": o.regulator_report_reference,
            "has_work_order": o.work_order_id is not None, "created_at": o.created_at, "row_version": o.row_version,
        }


class IncidentDetailSerializer(IncidentListSerializer):
    def to_representation(self, o):
        out = super().to_representation(o)
        ctx = _ctx(self)
        events = list(IncidentEvent.objects.filter(incident_id=o.pk).order_by("created_at", "id"))
        names = services.usernames([o.investigated_by, o.closed_by, o.created_by] + [e.created_by for e in events])
        wo = None
        if o.work_order_id and ctx is not None and ctx.has("work_order.view"):
            wo = {"public_id": str(o.work_order.public_id), "wo_number": o.work_order.wo_number,
                  "status": o.work_order.status}
        hold = services.open_incident_hold(o)
        out.update({
            "reported_by_name": o.reported_by_name, "description": o.description,
            "immediate_action": o.immediate_action, "patient_reference": o.patient_reference,
            "encounter_reference": o.encounter_reference, "investigated_by": names.get(o.investigated_by),
            "root_cause": o.root_cause, "corrective_action": o.corrective_action,
            "preventive_action": o.preventive_action, "investigation_notes": o.investigation_notes,
            "regulator_reported_on": o.regulator_reported_on, "work_order": wo,
            "closure_notes": o.closure_notes, "closed_at": o.closed_at, "closed_by": names.get(o.closed_by),
            "quarantine_open": hold is not None, "created_by": names.get(o.created_by),
            "updated_at": o.updated_at,
            "events": [{"public_id": str(e.public_id), "event_type": e.event_type, "from_status": e.from_status,
                        "to_status": e.to_status, "note": e.note, "created_at": e.created_at,
                        "created_by": names.get(e.created_by)} for e in events],
        })
        return out


# ================================================================== recalls (write)
class _NoticeFields(_Strict):
    reference_number = serializers.CharField(max_length=200, **_opt())
    title = serializers.CharField(max_length=300)
    notice_type = serializers.ChoiceField(choices=NOTICE_TYPES)
    source = serializers.ChoiceField(choices=SOURCES)
    issued_by_vendor = PublicRef(Vendor, required=False, allow_null=True)
    issued_date = serializers.DateField(**_opt())
    received_date = serializers.DateField(**_opt())
    urgency = serializers.ChoiceField(choices=URGENCIES)
    action_type = serializers.ChoiceField(choices=ACTION_TYPES)
    stop_use = serializers.BooleanField(required=False, default=False)
    description = serializers.CharField(max_length=4000)
    required_action = serializers.CharField(max_length=4000, **_opt())
    affected_serials_note = serializers.CharField(max_length=4000, **_opt())
    models = serializers.ListField(child=PublicRef(EquipmentModel), min_length=1, max_length=100)


class RecallCreateSerializer(_NoticeFields):
    pass


class RecallUpdateSerializer(_NoticeFields):
    row_version = serializers.IntegerField(required=False, min_value=1)


class IdentifyUnitsSerializer(_Action):
    mode = serializers.ChoiceField(choices=["ALL_OF_MODELS", "SERIAL_LIST"])
    serial_numbers = serializers.ListField(child=serializers.CharField(max_length=100, allow_blank=True),
                                           required=False, max_length=500)

    def validate(self, attrs):
        if attrs["mode"] == "SERIAL_LIST" and not any((s or "").strip() for s in attrs.get("serial_numbers", [])):
            raise serializers.ValidationError({"serial_numbers": ["Give at least one serial number."]})
        return attrs


class AddUnitSerializer(_Strict):
    equipment = PublicRef(Equipment)


class ResolveUnitSerializer(_Strict):
    status = serializers.ChoiceField(choices=["ACTION_COMPLETED", "NOT_APPLICABLE"])
    notes = serializers.CharField(max_length=2000, **_opt())
    vendor_reference = serializers.CharField(max_length=200, **_opt())


class NoticeCloseSerializer(_Action):
    close_notes = serializers.CharField(max_length=2000)


class ReasonSerializer(_Action):
    reason = serializers.CharField(max_length=1000)


# ================================================================== recalls (read)
class RecallListSerializer(serializers.BaseSerializer):
    def _base(self, o, counts):
        return {
            "public_id": str(o.public_id), "notice_number": o.notice_number, "reference_number": o.reference_number,
            "title": o.title, "notice_type": o.notice_type, "source": o.source, "urgency": o.urgency,
            "action_type": o.action_type, "stop_use": o.stop_use, "status": o.status,
            "issued_by_vendor": ref(o.issued_by_vendor, "name"), "issued_date": o.issued_date,
            "received_date": o.received_date, "counts": counts, "created_at": o.created_at,
            "row_version": o.row_version,
        }

    def to_representation(self, o):
        return self._base(o, (self.context.get("counts") or {}).get(o.pk))


class RecallDetailSerializer(RecallListSerializer):
    def to_representation(self, o):
        out = self._base(o, services.notice_counts([o.pk])[o.pk])
        models = RecallNoticeModel.objects.filter(recall_notice_id=o.pk).select_related("equipment_model") \
            .order_by("equipment_model__model_name")
        names = services.usernames([o.closed_by, o.created_by])
        out.update({
            "description": o.description, "required_action": o.required_action,
            "affected_serials_note": o.affected_serials_note, "close_notes": o.close_notes,
            "cancel_reason": o.cancel_reason, "closed_at": o.closed_at, "closed_by": names.get(o.closed_by),
            "created_by": names.get(o.created_by), "updated_at": o.updated_at,
            "models": [{"public_id": str(m.equipment_model.public_id), "model_name": m.equipment_model.model_name,
                        "model_number": m.equipment_model.model_number} for m in models],
        })
        return out


def unit_repr(u, names=None):
    names = names or {}
    e = u.equipment
    return {
        "public_id": str(u.public_id), "status": u.status, "identified_by": u.identified_by,
        "equipment": {"public_id": str(e.public_id), "asset_tag": e.asset_tag, "name": e.name,
                      "serial_number": e.serial_number, "lifecycle_stage": e.lifecycle_stage,
                      "operational_state": e.operational_state,
                      "current_location": ref(e.current_location, "code", "name")},
        "resolved_at": u.resolved_at, "resolved_by": names.get(u.resolved_by),
        "resolution_notes": u.resolution_notes, "vendor_reference": u.vendor_reference,
        "work_order": ({"public_id": str(u.work_order.public_id), "wo_number": u.work_order.wo_number}
                       if u.work_order_id else None),
        "created_at": u.created_at,
    }


# ================================================================== verification
class VerificationCreateSerializer(_Strict):
    title = serializers.CharField(max_length=300)
    scope_type = serializers.ChoiceField(choices=SCOPE_TYPES)
    department = PublicRef(Department, required=False, allow_null=True)
    location = PublicRef(Location, required=False, allow_null=True)
    planned_date = serializers.DateField(**_opt())
    conducted_by_name = serializers.CharField(max_length=200, **_opt())
    notes = serializers.CharField(max_length=4000, **_opt())


class VerificationUpdateSerializer(_Strict):
    row_version = serializers.IntegerField(required=False, min_value=1)
    title = serializers.CharField(max_length=300, required=False)
    scope_type = serializers.ChoiceField(choices=SCOPE_TYPES, required=False)
    department = PublicRef(Department, required=False, allow_null=True)
    location = PublicRef(Location, required=False, allow_null=True)
    planned_date = serializers.DateField(**_opt())
    conducted_by_name = serializers.CharField(max_length=200, **_opt())
    notes = serializers.CharField(max_length=4000, **_opt())


class ScanSerializer(_Strict):
    code = serializers.CharField(max_length=100)
    found_location = PublicRef(Location, required=False, allow_null=True)


class ItemUpdateSerializer(_Strict):
    row_version = serializers.IntegerField(required=False, min_value=1)
    tag_status = serializers.ChoiceField(choices=["OK", "DAMAGED", "UNREADABLE"], required=False)
    notes = serializers.CharField(max_length=2000, **_opt())


class ItemResolveSerializer(_Strict):
    resolution = serializers.ChoiceField(choices=["LOCATION_UPDATED", "CONFIRMED_MISSING", "FOUND_LATER", "IGNORED"])
    notes = serializers.CharField(max_length=2000, **_opt())


class VerificationListSerializer(serializers.BaseSerializer):
    def to_representation(self, o):
        return {
            "public_id": str(o.public_id), "verification_number": o.verification_number, "title": o.title,
            "scope_type": o.scope_type, "department": ref(o.department, "code", "name"),
            "location": ref(o.location, "code", "name"), "planned_date": o.planned_date, "status": o.status,
            "started_at": o.started_at, "completed_at": o.completed_at, "conducted_by_name": o.conducted_by_name,
            "expected_count": o.expected_count, "found_count": o.found_count, "elsewhere_count": o.elsewhere_count,
            "missing_count": o.missing_count, "unexpected_count": o.unexpected_count,
            "created_at": o.created_at, "row_version": o.row_version,
        }


class VerificationDetailSerializer(VerificationListSerializer):
    def to_representation(self, o):
        out = super().to_representation(o)
        out.update({"notes": o.notes, "cancel_reason": o.cancel_reason, "updated_at": o.updated_at,
                    "counters": services.verification_counters(o.pk)})
        return out


def item_repr(i, names=None):
    names = names or {}
    e = i.equipment
    return {
        "public_id": str(i.public_id),
        "equipment": {"public_id": str(e.public_id), "asset_tag": e.asset_tag, "name": e.name,
                      "serial_number": e.serial_number},
        "expected_location": ref(i.expected_location, "code", "name"),
        "expected_department": ref(i.expected_department, "code", "name"),
        "result": i.result, "found_location": ref(i.found_location, "code", "name"),
        "scanned_at": i.scanned_at, "scanned_by": names.get(i.scanned_by), "tag_status": i.tag_status,
        "notes": i.notes, "resolution": i.resolution, "resolution_notes": i.resolution_notes,
        "resolved_at": i.resolved_at, "resolved_by": names.get(i.resolved_by), "row_version": i.row_version,
    }


def equipment_brief(e):
    return {"public_id": str(e.public_id), "asset_tag": e.asset_tag, "name": e.name,
            "serial_number": e.serial_number, "lifecycle_stage": e.lifecycle_stage,
            "operational_state": e.operational_state, "current_location": ref(e.current_location, "code", "name")}
