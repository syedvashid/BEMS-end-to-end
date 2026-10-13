"""Condemnation and disposal: the end of an equipment's life.

Order of row locks everywhere: disposal -> condemnation request -> equipment. Business refusals raise Conflict
(409) with the details in `extra`; the view writes the refusal audit row in autocommit after the rollback.
"""
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.core import audit
from apps.core.errors import Conflict, StaleVersion
from apps.equipment import services as eq_services
from apps.maintenance import services as maint_services
from apps.maintenance.services import facility_tz, next_number, today_for

from . import depreciation as dep
from . import services as fin
from .models import CondemnationRequest, DepreciationEntry, Disposal

REQUEST_ENTITY, DISPOSAL_ENTITY = "CondemnationRequest", "Disposal"
LIVE_REQUEST = ("REQUESTED", "APPROVED")
OPEN_WO = ("OPEN", "ASSIGNED", "IN_PROGRESS", "WAITING_PARTS")
NEEDS_RECIPIENT = ("SOLD", "AUCTIONED", "DONATED", "TRADE_IN")


# ------------------------------------------------------------------ blockers
def _refs(qs, label, limit=10):
    return [{"public_id": str(pid), "label": lab} for pid, lab in qs.values_list("public_id", label)[:limit]]


def condemnation_blockers(equipment, *, ignore_request_pk=None, now=None):
    """[{code, message, refs}]: everything that stops this equipment from being condemned right now."""
    from apps.allocation.models import EquipmentAllocation, EquipmentReservation, EquipmentTransferRequest
    from apps.maintenance.models import WorkOrder
    from apps.safety.models import EquipmentIncident, PhysicalVerificationItem, RecallAffectedUnit

    fid, pk, now = equipment.facility_id, equipment.pk, now or timezone.now()
    out = []

    def add(code, message, qs, label):
        if qs.exists():
            out.append({"code": code, "message": message, "refs": _refs(qs, label)})

    if equipment.lifecycle_stage != "COMMISSIONED":
        out.append({"code": "NOT_COMMISSIONED", "refs": [],
                    "message": "Only commissioned equipment can be condemned."})
    live = CondemnationRequest.objects.filter(facility_id=fid, equipment_id=pk, is_active=True, status__in=LIVE_REQUEST)
    if ignore_request_pk is not None:
        live = live.exclude(pk=ignore_request_pk)
    add("EXISTING_REQUEST", "A condemnation request is already open for this equipment.", live, "request_number")
    add("ACTIVE_ALLOCATION", "The equipment is currently allocated. Release it first.",
        EquipmentAllocation.objects.filter(facility_id=fid, equipment_id=pk, is_active=True, released_at__isnull=True),
        "source_module")
    add("FUTURE_RESERVATION", "There are confirmed reservations in the future. Cancel them first.",
        EquipmentReservation.objects.filter(facility_id=fid, equipment_id=pk, is_active=True, status="CONFIRMED",
                                            end_at__gt=now), "purpose")
    add("PENDING_TRANSFER", "A transfer request is pending for this equipment.",
        EquipmentTransferRequest.objects.filter(facility_id=fid, equipment_id=pk, is_active=True, status="PENDING"),
        "reason")
    add("OPEN_INCIDENT", "An incident is still open. Close it first.",
        EquipmentIncident.objects.filter(facility_id=fid, equipment_id=pk, is_active=True).exclude(status="CLOSED"),
        "incident_number")
    add("PENDING_RECALL", "A recall notice still has a pending action for this equipment.",
        RecallAffectedUnit.objects.filter(facility_id=fid, equipment_id=pk, is_active=True, status="PENDING",
                                          recall_notice__status="OPEN", recall_notice__is_active=True),
        "recall_notice__notice_number")
    add("VERIFICATION_IN_PROGRESS", "A physical verification that includes this equipment is in progress.",
        PhysicalVerificationItem.objects.filter(facility_id=fid, equipment_id=pk, is_active=True,
                                                verification__status="IN_PROGRESS", verification__is_active=True),
        "verification__verification_number")
    add("OPEN_REPAIR_WORK_ORDER", "A breakdown or corrective work order is still open. Finish or cancel it first.",
        WorkOrder.objects.filter(facility_id=fid, equipment_id=pk, is_active=True,
                                 work_order_type__in=("BREAKDOWN", "CORRECTIVE"), status__in=OPEN_WO), "wo_number")
    return out


def _blocked(blockers):
    exc = Conflict("This equipment cannot be condemned yet. Resolve the listed items first.")
    exc.extra = {"blockers": blockers}
    return exc


# ------------------------------------------------------------------ helpers
def _lock_request(cr, expected_version=None):
    row = CondemnationRequest.objects.select_for_update().filter(
        pk=cr.pk, facility_id=cr.facility_id, is_active=True).first()
    if row is None:
        raise NotFound()
    if expected_version is not None and row.row_version != expected_version:
        raise StaleVersion(current_row_version=row.row_version)
    return row


def _lock_disposal(d, expected_version=None):
    row = Disposal.objects.select_for_update().filter(pk=d.pk, facility_id=d.facility_id, is_active=True).first()
    if row is None:
        raise NotFound()
    if expected_version is not None and row.row_version != expected_version:
        raise StaleVersion(current_row_version=row.row_version)
    return row


def _save(obj, request, **fields):
    for k, v in fields.items():
        setattr(obj, k, v)
    obj.updated_by = fin.uid_of(request)
    obj.save(update_fields=[*fields, "updated_by"])
    obj.refresh_from_db(fields=["updated_at", "row_version"])


def _audit(request, action, obj, entity, previous=None, new=None):
    audit.record(request=request, action=action, facility_id=obj.facility_id, entity_type=entity,
                 entity_public_id=obj.public_id, previous=previous, new=new,
                 changed_fields=audit.diff(previous, new) if previous is not None else None)


def _is_approver(request):
    return request.bems.has("condemnation.approve")


def _requester_or_approver(request, cr):
    if cr.created_by != request.user.id and not _is_approver(request):
        raise PermissionDenied()


def _blank(v):
    return not (v or "").strip()


# ------------------------------------------------------------------ condemnation
def request_condemnation(*, request, facility, equipment, data):
    with transaction.atomic():
        eq = eq_services._lock(equipment)
        blockers = condemnation_blockers(eq)
        if blockers:
            raise _blocked(blockers)
        reason, item = data["reason_category"], data.get("source_verification_item")
        if item is not None:
            if (item.equipment_id != eq.pk or item.resolution != "CONFIRMED_MISSING"
                    or item.verification.status != "COMPLETED"):
                raise ValidationError({"source_verification_item": [
                    "Must be a confirmed-missing item of a completed verification of this equipment."]})
            if reason != "LOST_MISSING":
                raise ValidationError({"reason_category": ["Must be Lost / missing when a verification item is linked."]})
        year, n = next_number(facility, "CND")
        uid = request.user.id
        cr = CondemnationRequest.objects.create(
            facility_id=eq.facility_id, request_number=f"CND-{year}-{n:06d}", equipment_id=eq.pk,
            reason_category=reason, justification=data["justification"].strip(),
            technical_assessment=data.get("technical_assessment"),
            technical_assessment_by_name=data.get("technical_assessment_by_name"),
            book_value_at_request=fin.current_book_value(eq),
            source_verification_item_id=item.pk if item is not None else None,
            status="REQUESTED", created_by=uid, updated_by=uid)
        _audit(request, "CONDEMNATION_REQUESTED", cr, REQUEST_ENTITY, new={
            "request_number": cr.request_number, "equipment": str(eq.public_id), "asset_tag": eq.asset_tag,
            "reason_category": reason,
            "book_value_at_request": str(cr.book_value_at_request) if cr.book_value_at_request is not None else None})
    return cr


def update_request(*, request, cr, expected_version, fields):
    with transaction.atomic():
        row = _lock_request(cr, expected_version)
        _requester_or_approver(request, row)
        if row.status != "REQUESTED":
            raise Conflict("Only a requested condemnation can be edited.")
        if "justification" in fields and _blank(fields["justification"]):
            raise ValidationError({"justification": ["This field may not be blank."]})
        before = audit.snapshot(row)
        _save(row, request, **fields)
        _audit(request, "UPDATE", row, REQUEST_ENTITY, previous=before, new=audit.snapshot(row))
    return row


def approve(*, request, cr, committee_reference=None, committee_decision_date=None, note=None, expected_version=None):
    from apps.compliance.models import CalibrationSchedule
    from apps.maintenance.models import MaintenancePlan, WorkOrder

    uid = request.user.id
    with transaction.atomic():
        row = _lock_request(cr, expected_version)
        if row.status != "REQUESTED":
            raise Conflict("Only a requested condemnation can be approved.")
        if row.created_by == uid:
            raise PermissionDenied()   # the approver may not be the requester
        eq = eq_services._lock(row.equipment)
        facility = request.bems.facility
        blockers = condemnation_blockers(eq, ignore_request_pk=row.pk)
        if blockers:
            raise _blocked(blockers)
        today = today_for(facility)
        if committee_decision_date is not None and committee_decision_date > today:
            raise ValidationError({"committee_decision_date": ["Cannot be in the future."]})
        threshold = fin.get_settings(facility).committee_required_above_book_value
        book = fin.current_book_value(eq)
        if book is None:
            book = row.book_value_at_request
        if threshold is not None and book is not None and book > threshold and _blank(committee_reference):
            raise ValidationError({"committee_reference": [
                f"Required when the book value is above {threshold}."]})

        # open preventive work orders are cancelled through the Phase 5 service, then plans and schedule go inactive
        for wo in WorkOrder.objects.select_for_update().filter(
                facility_id=eq.facility_id, equipment_id=eq.pk, is_active=True, work_order_type="PREVENTIVE",
                status__in=OPEN_WO):
            plan = MaintenancePlan.objects.filter(pk=wo.maintenance_plan_id).first() if wo.maintenance_plan_id else None
            due = max((plan.next_due_date if plan and plan.next_due_date else today), today)
            maint_services.cancel(request=request, wo=wo, reason="Equipment condemned", next_due_date=due)
        for model, entity in ((MaintenancePlan, "MaintenancePlan"), (CalibrationSchedule, "CalibrationSchedule")):
            for obj in model.objects.select_for_update().filter(facility_id=eq.facility_id, equipment_id=eq.pk,
                                                                is_active=True):
                before = audit.snapshot(obj)
                obj.is_active, obj.updated_by = False, uid
                obj.save(update_fields=["is_active", "updated_by"])
                obj.refresh_from_db(fields=["updated_at", "row_version"])
                after = audit.snapshot(obj)
                audit.record(request=request, action="SOFT_DELETE", facility_id=eq.facility_id, entity_type=entity,
                             entity_public_id=obj.public_id, previous=before, new=after,
                             changed_fields=audit.diff(before, after))

        eq_services.condemn_equipment(request=request, equipment=eq,
                                      reason=f"Condemnation {row.request_number} approved")
        before = audit.snapshot(row)
        _save(row, request, status="APPROVED", decided_by=uid, decided_at=timezone.now(),
              committee_reference=(committee_reference or "").strip() or None,
              committee_decision_date=committee_decision_date, decision_note=(note or "").strip() or None)
        _audit(request, "CONDEMNATION_APPROVED", row, REQUEST_ENTITY, previous=before, new=audit.snapshot(row))
    return row


def reject(*, request, cr, note, expected_version=None):
    if _blank(note):
        raise ValidationError({"note": ["This field is required."]})
    with transaction.atomic():
        row = _lock_request(cr, expected_version)
        if row.status != "REQUESTED":
            raise Conflict("Only a requested condemnation can be rejected.")
        before = audit.snapshot(row)
        _save(row, request, status="REJECTED", decided_by=request.user.id, decided_at=timezone.now(),
              decision_note=note.strip())
        _audit(request, "CONDEMNATION_REJECTED", row, REQUEST_ENTITY, previous=before, new=audit.snapshot(row))
    return row


def cancel_request(*, request, cr, reason, expected_version=None):
    if _blank(reason):
        raise ValidationError({"reason": ["This field is required."]})
    with transaction.atomic():
        row = _lock_request(cr, expected_version)
        _requester_or_approver(request, row)
        if row.status != "REQUESTED":
            raise Conflict("Only a requested condemnation can be cancelled.")
        before = audit.snapshot(row)
        _save(row, request, status="CANCELLED", cancel_reason=reason.strip())
        _audit(request, "CONDEMNATION_CANCELLED", row, REQUEST_ENTITY, previous=before, new=audit.snapshot(row))
    return row


def revoke(*, request, cr, reason, expected_version=None):
    if _blank(reason):
        raise ValidationError({"reason": ["This field is required."]})
    with transaction.atomic():
        row = _lock_request(cr, expected_version)
        if row.status != "APPROVED":
            raise Conflict("Only an approved condemnation can be revoked.")
        eq = eq_services._lock(row.equipment)
        if Disposal.objects.filter(facility_id=row.facility_id, condemnation_request_id=row.pk, is_active=True,
                                   status__in=("IN_PROGRESS", "COMPLETED")).exists():
            raise Conflict("A disposal exists for this condemnation. Cancel the disposal first.")
        eq_services.revoke_condemnation(request=request, equipment=eq,
                                        reason=f"Condemnation {row.request_number} revoked: {reason.strip()}")
        before = audit.snapshot(row)
        _save(row, request, status="CANCELLED", revoked=True, cancel_reason=reason.strip())
        _audit(request, "CONDEMNATION_REVOKED", row, REQUEST_ENTITY, previous=before, new=audit.snapshot(row))
    return row


# ------------------------------------------------------------------ disposal
_DISPOSAL_FIELDS = ("disposal_method", "disposal_date", "recipient_name", "recipient_vendor", "proceeds_amount",
                    "decontamination_done", "decontamination_notes", "data_wipe_required", "data_wipe_done",
                    "recycler_name", "ewaste_certificate_number", "notes")


def _disposal_values(data):
    out = {}
    for k in _DISPOSAL_FIELDS:
        if k in data:
            out["recipient_vendor_id" if k == "recipient_vendor" else k] = (
                data[k].pk if k == "recipient_vendor" and data[k] is not None else
                None if k == "recipient_vendor" else data[k])
    return out


def create_disposal(*, request, cr, data):
    with transaction.atomic():
        row = _lock_request(cr)
        eq = eq_services._lock(row.equipment)
        if row.status != "APPROVED":
            raise Conflict("A disposal needs an approved condemnation.")
        if eq.lifecycle_stage != "CONDEMNED":
            raise Conflict("The equipment is not condemned.")
        if Disposal.objects.filter(facility_id=row.facility_id, equipment_id=eq.pk, is_active=True,
                                   status__in=("IN_PROGRESS", "COMPLETED")).exists():
            raise Conflict("This equipment already has a disposal.")
        year, n = next_number(request.bems.facility, "DSP")
        uid = request.user.id
        d = Disposal.objects.create(
            facility_id=row.facility_id, disposal_number=f"DSP-{year}-{n:06d}", equipment_id=eq.pk,
            condemnation_request_id=row.pk, status="IN_PROGRESS", created_by=uid, updated_by=uid,
            **_disposal_values(data))
        _audit(request, "CREATE", d, DISPOSAL_ENTITY, new=audit.snapshot(d))
    return d


def update_disposal(*, request, disposal, expected_version, fields):
    with transaction.atomic():
        d = _lock_disposal(disposal, expected_version)
        if d.status != "IN_PROGRESS":
            raise Conflict("Only a disposal in progress can be edited.")
        before = audit.snapshot(d)
        _save(d, request, **_disposal_values(fields))
        _audit(request, "UPDATE", d, DISPOSAL_ENTITY, previous=before, new=audit.snapshot(d))
    return d


def cancel_disposal(*, request, disposal, reason, expected_version=None):
    if _blank(reason):
        raise ValidationError({"reason": ["This field is required."]})
    with transaction.atomic():
        d = _lock_disposal(disposal, expected_version)
        if d.status != "IN_PROGRESS":
            raise Conflict("Only a disposal in progress can be cancelled.")
        before = audit.snapshot(d)
        _save(d, request, status="CANCELLED", cancel_reason=reason.strip())
        _audit(request, "DISPOSAL_CANCELLED", d, DISPOSAL_ENTITY, previous=before, new=audit.snapshot(d))
    return d


def _finalise_depreciation(eq, disposal_date, uid):
    """Catch up to the month before the disposal month, then a prorated stub for the disposal month.
    Returns the book value at disposal (None when the equipment has no depreciation basis)."""
    policy = fin.resolve_policy(eq)
    comm = fin.commissioning_dates([eq.pk]).get(eq.pk)
    reason, basis = fin.basis_for_equipment(eq, policy, comm)
    last = fin.latest_entries([eq.pk]).get(eq.pk)
    if reason != "OK":
        return last.closing_value if last is not None else None
    dm = dep.month_start(disposal_date)
    if last is None:
        opening, last_month = basis.cost, None
    else:
        opening, last_month = last.closing_value, last.period_month
    if last_month == dm:
        return opening   # a full entry for the disposal month already exists: used as is
    prev = dep.add_months(dm, -1)
    from_month = dep.month_start(basis.start) if last_month is None else dep.add_months(last_month, 1)
    if from_month <= prev:
        calcs = dep.generate_entries(
            method=basis.method, cost=basis.cost, salvage=basis.salvage, start_date=basis.start,
            opening_value=opening, from_month=from_month, to_month=prev, useful_life_years=basis.life,
            rate_percent=basis.rate)
        if calcs:
            DepreciationEntry.objects.bulk_create(
                [fin._entry_row(eq, c, "REGULAR", basis, policy, None, uid) for c in calcs])
            opening = calcs[-1].closing_value
    stub = dep.stub_entry(
        method=basis.method, cost=basis.cost, salvage=basis.salvage, start_date=basis.start, opening_value=opening,
        disposal_date=disposal_date, useful_life_years=basis.life, rate_percent=basis.rate)
    if stub is None:
        return opening
    DepreciationEntry.objects.bulk_create([fin._entry_row(eq, stub, "DISPOSAL_STUB", basis, policy, None, uid)])
    return stub.closing_value


def complete_disposal(*, request, disposal, expected_version=None):
    uid = request.user.id
    with transaction.atomic():
        d = _lock_disposal(disposal, expected_version)
        if d.status != "IN_PROGRESS":
            raise Conflict("Only a disposal in progress can be completed.")
        cr = _lock_request(d.condemnation_request)
        eq = eq_services._lock(d.equipment)
        facility = request.bems.facility
        today, tz = today_for(facility), facility_tz(facility)
        errors = {}
        dd = d.disposal_date
        if dd is None:
            errors["disposal_date"] = ["This field is required to complete the disposal."]
        else:
            if dd > today:
                errors["disposal_date"] = ["Cannot be in the future."]
            decision = cr.committee_decision_date or (cr.decided_at.astimezone(tz).date() if cr.decided_at else None)
            if decision is not None and dd < decision:
                errors["disposal_date"] = ["Cannot be before the condemnation decision date."]
            if eq.ownership_type == "OWNED" and "disposal_date" not in errors:
                last = fin.latest_entries([eq.pk]).get(eq.pk)
                if last is not None and dep.month_start(dd) < last.period_month:
                    errors["disposal_date"] = [
                        "Cannot be earlier than the last depreciated month (%s)." % last.period_month.strftime("%b %Y")]
        method = d.disposal_method
        if method != "LOST_MISSING" and not d.decontamination_done:
            errors["decontamination_done"] = ["Decontamination must be done before the disposal is completed."]
        if d.data_wipe_required and not d.data_wipe_done:
            errors["data_wipe_done"] = ["The data wipe must be done before the disposal is completed."]
        if method == "SCRAPPED_E_WASTE":
            if _blank(d.recycler_name):
                errors["recycler_name"] = ["Required for e-waste scrapping."]
            if _blank(d.ewaste_certificate_number):
                errors["ewaste_certificate_number"] = ["Required for e-waste scrapping."]
        if method in NEEDS_RECIPIENT and _blank(d.recipient_name):
            errors["recipient_name"] = ["Required for this disposal method."]
        if errors:
            raise ValidationError(errors)

        book = gain = None
        if eq.ownership_type == "OWNED":
            book = _finalise_depreciation(eq, dd, uid)
            if book is not None:
                gain = dep.q2(d.proceeds_amount - book)
        eq_services.dispose_equipment(request=request, equipment=eq,
                                      reason=f"Disposal {d.disposal_number} completed ({method})")
        now = timezone.now()
        before = audit.snapshot(d)
        _save(d, request, status="COMPLETED", completed_at=now, completed_by=uid, book_value_at_disposal=book,
              gain_loss=gain)
        _save(cr, request, status="COMPLETED", completed_at=now)
        _audit(request, "DISPOSAL_COMPLETED", d, DISPOSAL_ENTITY, previous=before, new={
            **audit.snapshot(d), "request_number": cr.request_number, "asset_tag": eq.asset_tag,
            "gain_loss": str(gain) if gain is not None else None})
    return d


# ------------------------------------------------------------------ small read helpers
def lifecycle_end_brief(eq):
    """Block on the equipment detail: the live (or latest completed) condemnation request and the disposal."""
    reqs = CondemnationRequest.objects.filter(facility_id=eq.facility_id, equipment_id=eq.pk, is_active=True,
                                              status__in=("REQUESTED", "APPROVED", "COMPLETED")).order_by("-id")
    cr = reqs.first()
    d = Disposal.objects.filter(facility_id=eq.facility_id, equipment_id=eq.pk, is_active=True,
                                status__in=("IN_PROGRESS", "COMPLETED")).order_by("-id").first()
    return {
        "condemnation_request": ({"public_id": str(cr.public_id), "request_number": cr.request_number,
                                  "status": cr.status} if cr else None),
        "disposal": ({"public_id": str(d.public_id), "disposal_number": d.disposal_number,
                      "status": d.status} if d else None),
    }
