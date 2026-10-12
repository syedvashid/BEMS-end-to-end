from rest_framework import serializers

from apps.compliance.serializers import PublicRef, StrictSerializer
from apps.equipment.models import Equipment
from apps.equipment.serializers import ref
from apps.masters.models import Department, Location

from .models import EquipmentAllocation

REF_RE = r"^[A-Za-z0-9/_-]{1,40}$"
SOURCES = ["IPD", "OT", "ICU", "ER", "RADIOLOGY", "LAB", "MANUAL"]
CONDITIONS = ["GOOD", "NEEDS_CLEANING", "DAMAGED"]


class NullBlank:
    """Blank strings become null before field validation (optional fields send null, not "")."""
    def to_internal_value(self, data):
        if isinstance(data, dict):
            data = {k: (None if isinstance(v, str) and not v.strip() else v) for k, v in data.items()}
        return super().to_internal_value(data)


def _ref_field():
    return serializers.RegexField(REF_RE, max_length=40, required=False, allow_null=True)


# ------------------------------------------------------------------ write serializers
class AllocationCreateSerializer(NullBlank, StrictSerializer):
    equipment = PublicRef(Equipment)
    department = PublicRef(Department, required=False, allow_null=True)
    location = PublicRef(Location, required=False, allow_null=True)
    source_module = serializers.ChoiceField(choices=SOURCES, required=False, default="MANUAL")
    patient_reference = _ref_field()
    encounter_reference = _ref_field()
    practitioner_name = serializers.CharField(max_length=200, required=False, allow_null=True)
    purpose = serializers.CharField(max_length=1000, required=False, allow_null=True)
    expected_release_at = serializers.DateTimeField(required=False, allow_null=True)
    override = serializers.BooleanField(required=False, default=False)
    override_reason = serializers.CharField(max_length=1000, required=False, allow_null=True)


class AllocationReleaseSerializer(NullBlank, StrictSerializer):
    condition_on_release = serializers.ChoiceField(choices=CONDITIONS)
    release_notes = serializers.CharField(max_length=1000, required=False, allow_null=True)
    return_to_previous_location = serializers.BooleanField(required=False, default=True)


class ReservationCreateSerializer(NullBlank, StrictSerializer):
    equipment = PublicRef(Equipment)
    department = PublicRef(Department)
    start_at = serializers.DateTimeField()
    end_at = serializers.DateTimeField()
    purpose = serializers.CharField(max_length=1000)
    procedure_reference = serializers.CharField(max_length=200, required=False, allow_null=True)


class ReasonSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=1000)


class UsageLogWriteSerializer(NullBlank, StrictSerializer):
    equipment = PublicRef(Equipment, required=False)
    allocation = PublicRef(EquipmentAllocation, required=False, allow_null=True)
    department = PublicRef(Department, required=False, allow_null=True)
    started_at = serializers.DateTimeField()
    ended_at = serializers.DateTimeField()
    operator_name = serializers.CharField(max_length=200, required=False, allow_null=True)
    patient_reference = _ref_field()
    encounter_reference = _ref_field()
    procedure_text = serializers.CharField(max_length=500, required=False, allow_null=True)
    notes = serializers.CharField(max_length=2000, required=False, allow_null=True)
    row_version = serializers.IntegerField(required=False, min_value=1)


class TransferCreateSerializer(NullBlank, StrictSerializer):
    equipment = PublicRef(Equipment)
    location = PublicRef(Location)
    department = PublicRef(Department, required=False, allow_null=True)
    reason = serializers.CharField(max_length=1000)


class ApproveSerializer(NullBlank, StrictSerializer):
    note = serializers.CharField(max_length=1000, required=False, allow_null=True)


class RejectSerializer(StrictSerializer):
    note = serializers.CharField(max_length=1000)


class UserDepartmentsInputSerializer(StrictSerializer):
    departments = serializers.ListField(child=serializers.UUIDField(), max_length=200)


# ------------------------------------------------------------------ read representations (plain dicts, no per-row queries
# beyond the select_related in the viewsets)
def _eq(e):
    return {"public_id": str(e.public_id), "asset_tag": e.asset_tag, "name": e.name}


def allocation_repr(a, names=None, uid=None):
    names = names or {}
    return {
        "public_id": str(a.public_id), "equipment": _eq(a.equipment),
        "department": ref(a.department, "code", "name") if a.department_id else None,
        "location": ref(a.location, "code", "name") if a.location_id else None,
        "previous_location": ref(a.previous_location, "code", "name") if a.previous_location_id else None,
        "source_module": a.source_module, "patient_reference": a.patient_reference,
        "encounter_reference": a.encounter_reference, "practitioner_name": a.practitioner_name,
        "purpose": a.purpose, "assigned_at": a.assigned_at, "expected_release_at": a.expected_release_at,
        "released_at": a.released_at, "released_by": names.get(a.released_by),
        "condition_on_release": a.condition_on_release, "release_notes": a.release_notes,
        "gate_override": a.gate_override, "override_reason": a.override_reason,
        "is_released": a.released_at is not None, "created_by": names.get(a.created_by),
        "created_at": a.created_at, "row_version": a.row_version,
    }


def reservation_repr(r, names=None, uid=None):
    names = names or {}
    return {
        "public_id": str(r.public_id), "equipment": _eq(r.equipment),
        "department": ref(r.department, "code", "name"), "start_at": r.start_at, "end_at": r.end_at,
        "purpose": r.purpose, "procedure_reference": r.procedure_reference, "status": r.status,
        "cancel_reason": r.cancel_reason, "created_by": names.get(r.created_by),
        "is_mine": uid is not None and r.created_by == uid, "created_at": r.created_at,
    }


def usage_repr(u, names=None, uid=None):
    names = names or {}
    return {
        "public_id": str(u.public_id), "equipment": _eq(u.equipment),
        "allocation": str(u.allocation.public_id) if u.allocation_id else None,
        "department": ref(u.department, "code", "name") if u.department_id else None,
        "started_at": u.started_at, "ended_at": u.ended_at, "duration_minutes": u.duration_minutes,
        "operator_name": u.operator_name, "patient_reference": u.patient_reference,
        "encounter_reference": u.encounter_reference, "procedure_text": u.procedure_text, "notes": u.notes,
        "is_active": u.is_active, "created_by": names.get(u.created_by), "created_at": u.created_at,
        "row_version": u.row_version,
    }


def transfer_repr(t, names=None, uid=None):
    names = names or {}
    return {
        "public_id": str(t.public_id), "equipment": _eq(t.equipment),
        "from_department": ref(t.from_department, "code", "name") if t.from_department_id else None,
        "from_location": ref(t.from_location, "code", "name") if t.from_location_id else None,
        "to_location": ref(t.to_location, "code", "name"),
        "to_department": ref(t.to_department, "code", "name") if t.to_department_id else None,
        "reason": t.reason, "status": t.status, "decided_by": names.get(t.decided_by),
        "decided_at": t.decided_at, "decision_note": t.decision_note,
        "created_by": names.get(t.created_by), "is_mine": uid is not None and t.created_by == uid,
        "created_at": t.created_at, "row_version": t.row_version,
    }