"""Compliance business rules (calibration, warranty, AMC, licences, due view). Views stay thin."""
import math
from datetime import date, timedelta

from django.apps import apps as django_apps
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef
from rest_framework.exceptions import NotFound, ValidationError

from apps.core import audit
from apps.core.errors import Conflict
from apps.equipment.models import Equipment
from apps.foundation.models import Facility
from apps.maintenance import holds
from apps.maintenance import services as mx
from apps.maintenance.services import add_interval, add_months, today_for

from .models import (
    AmcContract, AmcCoverage, CalibrationImpactReview, CalibrationRecord, CalibrationSchedule,
    EquipmentLicence, Warranty,
)

CAP = 500                     # rows per type in the due view
OVERDUE_LOOKBACK_DAYS = 90    # expiry-type items (not calibration) stay "overdue" this long after expiry
# ASSUMPTIONS about Phase 4 names; adjust here if they differ:
EQUIPMENT_DEPARTMENT_FIELD = "owning_department"
COMMISSIONING_MODEL = ("equipment", "EquipmentCommissioning")

TYPE_PERMS = {"CALIBRATION": "calibration.view", "WARRANTY": "warranty.view", "AMC": "amc.view",
              "LICENCE": "licence.view", "DOCUMENT": "document.view"}


# ------------------------------------------------------------------ calibration status
def status_code(next_due, lead_days, today):
    if next_due < today:
        return "OVERDUE"
    if today >= next_due - timedelta(days=lead_days):
        return "DUE_SOON"
    return "OK"


def record_summary(rec):
    if rec is None:
        return None
    return {"public_id": str(rec.public_id), "performed_date": rec.performed_date, "result": rec.result,
            "next_due_date": rec.next_due_date, "certificate_number": rec.certificate_number}


def calibration_status(target, today=None):
    """Plain importable function (Phase 7 will use it). target: Equipment or CalibrationSchedule."""
    if isinstance(target, CalibrationSchedule):
        schedule = target if target.is_active else None
        eq_pk, fid = target.equipment_id, target.facility_id
    else:
        eq_pk, fid = target.pk, target.facility_id
        schedule = CalibrationSchedule.objects.filter(facility_id=fid, equipment_id=eq_pk, is_active=True).first()
    if today is None:
        today = today_for(Facility.objects.get(pk=fid))
    last = CalibrationRecord.objects.filter(facility_id=fid, equipment_id=eq_pk).order_by(
        "-performed_date", "-id").first()
    return {
        "status": "NOT_REQUIRED" if schedule is None else status_code(schedule.next_due_date, schedule.lead_days, today),
        "next_due_date": schedule.next_due_date if schedule else None,
        "has_unresolved_failure": bool(last and last.result == "FAIL"),
        "schedule_public_id": str(schedule.public_id) if schedule else None,
        "latest_record": last,
    }


# ------------------------------------------------------------------ readings
_TEXT_LIMITS = {"parameter": 100, "unit": 30, "tolerance": 50}
_NUM_OR_TEXT = ("nominal", "measured")


def validate_readings(readings):
    if readings in (None, ""):
        return []

    def bad(msg):
        raise ValidationError({"readings": [msg]})

    if not isinstance(readings, list):
        bad("Must be a list.")
    if len(readings) > 50:
        bad("At most 50 readings are allowed.")
    out = []
    for i, r in enumerate(readings, 1):
        if not isinstance(r, dict):
            bad(f"Reading {i}: must be an object.")
        unknown = set(r) - set(_TEXT_LIMITS) - set(_NUM_OR_TEXT)
        if unknown:
            bad(f"Reading {i}: unknown field {sorted(unknown)[0]}.")
        row = {}
        for k in (*_TEXT_LIMITS, *_NUM_OR_TEXT):
            v = r.get(k)
            if v is None or v == "":
                continue
            if isinstance(v, bool):
                bad(f"Reading {i}: {k} is invalid.")
            if isinstance(v, (int, float)):
                if k in ("parameter", "unit"):
                    bad(f"Reading {i}: {k} must be text.")
                if not math.isfinite(v):
                    bad(f"Reading {i}: {k} is invalid.")
            elif isinstance(v, str):
                v = v.strip()
                if len(v) > _TEXT_LIMITS.get(k, 50):
                    bad(f"Reading {i}: {k} is too long.")
            else:
                bad(f"Reading {i}: {k} is invalid.")
            row[k] = v
        if not row.get("parameter"):
            bad(f"Reading {i}: parameter is required.")
        out.append(row)
    return out


# ------------------------------------------------------------------ calibration actions
def record_calibration(*, request, facility, equipment, data):
    uid = request.user.id
    with transaction.atomic():
        sch = CalibrationSchedule.objects.select_for_update().filter(
            facility_id=facility.id, equipment_id=equipment.pk, is_active=True).first()
        if sch is None:
            raise ValidationError({"equipment": ["This equipment has no active calibration schedule."]})
        eq = Equipment.objects.select_for_update().filter(
            pk=equipment.pk, facility_id=facility.id, is_active=True).first()
        if eq is None or eq.lifecycle_stage != "COMMISSIONED":
            raise ValidationError({"equipment": ["Equipment must be commissioned."]})
        today, performed = today_for(facility), data["performed_date"]
        if performed > today:
            raise ValidationError({"performed_date": ["Cannot be in the future."]})
        if sch.last_calibrated_date and performed < sch.last_calibrated_date:
            raise ValidationError({"performed_date": [
                f"Cannot be earlier than the last calibration ({sch.last_calibrated_date.isoformat()})."]})
        readings = validate_readings(data.get("readings"))
        next_due = data.get("next_due_date")
        if next_due is not None:
            if next_due <= performed:
                raise ValidationError({"next_due_date": ["Must be after the performed date."]})
        else:
            next_due = add_interval(performed, sch.frequency_type, sch.frequency_value)
        rec = CalibrationRecord.objects.create(
            facility_id=facility.id, equipment_id=eq.pk, calibration_schedule_id=sch.pk, performed_date=performed,
            calibration_reason=data["calibration_reason"], performed_by_type=data["performed_by_type"],
            performer_vendor=data.get("performer_vendor"), performer_name=data.get("performer_name"),
            reference_standard_details=data.get("reference_standard_details"),
            certificate_number=data.get("certificate_number"), result=data["result"], readings=readings,
            deviation_summary=data.get("deviation_summary"), next_due_date=next_due, notes=data.get("notes"),
            created_by=uid)
        before = {"last_calibrated_date": sch.last_calibrated_date, "next_due_date": sch.next_due_date}
        sch.last_calibrated_date, sch.next_due_date, sch.updated_by = performed, next_due, uid
        sch.save(update_fields=["last_calibrated_date", "next_due_date", "updated_by"])
        audit.record(
            request=request, action="CALIBRATION_RECORDED", facility_id=facility.id, entity_type="CalibrationRecord",
            entity_public_id=rec.public_id,
            new={"equipment": str(eq.public_id), "asset_tag": eq.asset_tag, "result": rec.result,
                 "performed_date": performed, "next_due_date": next_due,
                 "certificate_number": rec.certificate_number, "schedule_before": before})
        if rec.result == "FAIL":
            if sch.on_fail_hold_equipment:
                holds.place_hold(request=request, equipment=eq, hold_type="OUT_OF_SERVICE", source_type="CALIBRATION",
                                 calibration_record=rec,
                                 reason=f"Calibration failed on {performed.isoformat()}")
            if sch.on_fail_open_work_order:
                mx.create_work_order(request=request, facility=facility, work_order_type="CORRECTIVE", equipment=eq,
                                     priority="HIGH", problem_description="Calibration failed",
                                     source_calibration_record=rec)
        else:
            holds.release_calibration_holds(request=request, equipment=eq, reason="Calibration passed")
    return rec


def review_impact(*, request, record, notes, patient_impact_found):
    notes = (notes or "").strip()
    if not notes:
        raise ValidationError({"review_notes": ["This field is required."]})
    with transaction.atomic():
        rec = CalibrationRecord.objects.select_for_update().filter(pk=record.pk, facility_id=record.facility_id).first()
        if rec is None:
            raise NotFound()
        if rec.result != "FAIL":
            raise Conflict("An impact review applies only to failed calibrations.")
        if CalibrationImpactReview.objects.filter(calibration_record_id=rec.pk).exists():
            raise Conflict("This calibration has already been reviewed.")
        try:
            with transaction.atomic():
                review = CalibrationImpactReview.objects.create(
                    facility_id=rec.facility_id, calibration_record_id=rec.pk, review_notes=notes,
                    patient_impact_found=patient_impact_found, created_by=request.user.id)
        except IntegrityError:
            raise Conflict("This calibration has already been reviewed.")
        audit.record(request=request, action="CALIBRATION_IMPACT_REVIEWED", facility_id=rec.facility_id,
                     entity_type="CalibrationRecord", entity_public_id=rec.public_id,
                     new={"patient_impact_found": patient_impact_found, "review": str(review.public_id)})
    return review


def generate_schedules(*, request, facility, equipment_model=None, category=None, frequency_type=None,
                       frequency_value=None, last_calibrated_date=None, lead_days=30, on_fail_hold_equipment=True,
                       on_fail_open_work_order=True):
    if (equipment_model is None) == (category is None):
        raise ValidationError({"scope": ["Give either equipment_model or category."]})
    if (frequency_type is None) != (frequency_value is None):
        raise ValidationError({"frequency_value": ["Give frequency_type and frequency_value together."]})
    today = today_for(facility)
    if last_calibrated_date and last_calibrated_date > today:
        raise ValidationError({"last_calibrated_date": ["Cannot be in the future."]})
    qs = Equipment.objects.filter(facility_id=facility.id, is_active=True, lifecycle_stage="COMMISSIONED") \
        .select_related("equipment_model__category")
    qs = qs.filter(equipment_model=equipment_model) if equipment_model is not None \
        else qs.filter(equipment_model__category=category)
    created = skipped_existing = skipped_no_interval = 0
    uid = request.user.id
    with transaction.atomic():
        for eq in qs.order_by("id"):
            if CalibrationSchedule.objects.filter(facility_id=facility.id, equipment_id=eq.pk, is_active=True).exists():
                skipped_existing += 1
                continue
            if frequency_type:
                ftype, fval = frequency_type, frequency_value
            else:
                m = eq.equipment_model
                interval = m.default_calibration_interval_days if m.default_calibration_interval_days is not None \
                    else m.category.default_calibration_interval_days
                if not interval:
                    skipped_no_interval += 1
                    continue
                ftype, fval = "DAYS", interval
            CalibrationSchedule.objects.create(
                facility=facility, equipment=eq, frequency_type=ftype, frequency_value=fval, lead_days=lead_days,
                last_calibrated_date=last_calibrated_date,
                next_due_date=add_interval(last_calibrated_date or today, ftype, fval),
                on_fail_hold_equipment=on_fail_hold_equipment, on_fail_open_work_order=on_fail_open_work_order,
                created_by=uid, updated_by=uid)
            created += 1
        result = {"created": created, "skipped_existing": skipped_existing, "skipped_no_interval": skipped_no_interval}
        audit.record(request=request, action="BULK_CREATE", facility_id=facility.id,
                     entity_type="CalibrationSchedule",
                     new={**result, "scope": str((equipment_model or category).public_id)})
    return result


# ------------------------------------------------------------------ coverage suggestion
def find_coverage(equipment, on_date):
    """Returns ('WARRANTY', warranty) | ('AMC', contract) | (None, None). Warranty wins."""
    w = Warranty.objects.filter(
        facility_id=equipment.facility_id, equipment_id=equipment.pk, is_active=True,
        start_date__lte=on_date, end_date__gte=on_date).order_by("-end_date", "-id").first()
    if w is not None:
        return "WARRANTY", w
    cov = AmcCoverage.objects.filter(
        facility_id=equipment.facility_id, equipment_id=equipment.pk, amc_contract__is_active=True,
        amc_contract__start_date__lte=on_date, amc_contract__end_date__gte=on_date,
    ).select_related("amc_contract").order_by("-amc_contract__end_date", "-id").first()
    if cov is not None:
        return "AMC", cov.amc_contract
    return None, None


def suggest_coverage(equipment, on_date):
    source, obj = find_coverage(equipment, on_date)
    out = {"coverage_source": source, "warranty_id": None, "amc_contract_id": None}
    if source == "WARRANTY":
        out["warranty_id"] = str(obj.public_id)
        out["message"] = (f"Covered by an active {obj.warranty_type.lower()} warranty until "
                          f"{obj.end_date.isoformat()}. Check the warranty exclusions before raising a claim.")
    elif source == "AMC":
        out["amc_contract_id"] = str(obj.public_id)
        if obj.contract_type == "COMPREHENSIVE":
            out["message"] = (f"Covered by comprehensive AMC {obj.contract_number} until {obj.end_date.isoformat()}. "
                              "Check the contract exclusions.")
        else:
            out["message"] = (f"Covered by non-comprehensive AMC {obj.contract_number} until "
                              f"{obj.end_date.isoformat()}. Spare parts may be excluded: check the contract exclusions.")
    else:
        out["message"] = "No active warranty or AMC contract covers this equipment on that date."
    return out


def resolve_coverage_links(*, facility, equipment, coverage_source, warranty, amc_contract):
    """Validate the FINAL coverage state of a work order. Returns (coverage_source, warranty, amc_contract)."""
    if warranty is not None and amc_contract is not None:
        raise ValidationError({"warranty_id": ["Link either a warranty or an AMC contract, not both."]})
    if warranty is not None:
        if warranty.facility_id != facility.id or warranty.equipment_id != equipment.pk or not warranty.is_active:
            raise ValidationError({"warranty_id": ["This warranty does not belong to the work order's equipment."]})
        if coverage_source not in (None, "WARRANTY"):
            raise ValidationError({"coverage_source": ["Must be WARRANTY when a warranty is linked."]})
        coverage_source = "WARRANTY"
    if amc_contract is not None:
        ok = amc_contract.facility_id == facility.id and amc_contract.is_active and AmcCoverage.objects.filter(
            facility_id=facility.id, amc_contract_id=amc_contract.pk, equipment_id=equipment.pk).exists()
        if not ok:
            raise ValidationError({"amc_contract_id": ["This contract does not cover the work order's equipment."]})
        if coverage_source not in (None, "AMC"):
            raise ValidationError({"coverage_source": ["Must be AMC when an AMC contract is linked."]})
        coverage_source = "AMC"
    return coverage_source, warranty, amc_contract


def equipment_compliance_summary(equipment, today):
    """Read-only fields for the equipment detail serializer."""
    cal = calibration_status(equipment, today)
    source, obj = find_coverage(equipment, today)
    w = obj if source == "WARRANTY" else Warranty.objects.filter(
        facility_id=equipment.facility_id, equipment_id=equipment.pk, is_active=True,
        start_date__lte=today, end_date__gte=today).order_by("-end_date").first()
    cov = AmcCoverage.objects.filter(
        facility_id=equipment.facility_id, equipment_id=equipment.pk, amc_contract__is_active=True,
        amc_contract__start_date__lte=today, amc_contract__end_date__gte=today,
    ).select_related("amc_contract").order_by("-amc_contract__end_date").first()
    amc = cov.amc_contract if cov else None
    return {
        "calibration_status": cal["status"], "next_calibration_due": cal["next_due_date"],
        "has_unresolved_failure": cal["has_unresolved_failure"],
        "current_warranty": None if w is None else {
            "public_id": str(w.public_id), "warranty_type": w.warranty_type, "start_date": w.start_date,
            "end_date": w.end_date},
        "current_amc": None if amc is None else {
            "public_id": str(amc.public_id), "contract_number": amc.contract_number,
            "contract_type": amc.contract_type, "start_date": amc.start_date, "end_date": amc.end_date},
    }


# ------------------------------------------------------------------ AMC
def find_overlaps(*, facility_id, equipment_pks, start, end, exclude_contract_pk=None):
    qs = AmcCoverage.objects.filter(
        facility_id=facility_id, equipment_id__in=list(equipment_pks), amc_contract__is_active=True,
        amc_contract__start_date__lte=end, amc_contract__end_date__gte=start).select_related("amc_contract")
    if exclude_contract_pk is not None:
        qs = qs.exclude(amc_contract_id=exclude_contract_pk)
    return list(qs)


def overlap_conflict(overlaps):
    tags = dict(Equipment.objects.filter(pk__in=[o.equipment_id for o in overlaps]).values_list("pk", "asset_tag"))
    first = overlaps[0]
    exc = Conflict(f"Equipment {tags.get(first.equipment_id, '')} is already covered by AMC contract "
                   f"{first.amc_contract.contract_number} for an overlapping period.")
    exc.extra = {"conflicts": [{"asset_tag": tags.get(o.equipment_id), "contract_number": o.amc_contract.contract_number,
                                "contract": str(o.amc_contract.public_id)} for o in overlaps[:20]]}
    return exc


def check_contract_dates_vs_coverage(contract, start, end):
    """Used by the serializer when an update changes the dates of a contract that already has coverage."""
    pks = list(AmcCoverage.objects.filter(facility_id=contract.facility_id, amc_contract_id=contract.pk)
               .values_list("equipment_id", flat=True))
    if pks:
        overlaps = find_overlaps(facility_id=contract.facility_id, equipment_pks=pks, start=start, end=end,
                                 exclude_contract_pk=contract.pk)
        if overlaps:
            raise overlap_conflict(overlaps)


def set_coverage(*, request, facility, contract, items):
    pks = [i["equipment"].pk for i in items]
    if len(set(pks)) != len(pks):
        raise ValidationError({"items": ["The same equipment is listed twice."]})
    if len(pks) > 500:
        raise ValidationError({"items": ["At most 500 equipment per contract."]})
    with transaction.atomic():
        c = AmcContract.objects.select_for_update().filter(pk=contract.pk, facility_id=facility.id, is_active=True).first()
        if c is None:
            raise NotFound()
        eqs = {e.pk: e for e in Equipment.objects.select_for_update().filter(
            facility_id=facility.id, is_active=True, pk__in=pks).order_by("pk")}
        if len(eqs) != len(pks):
            raise ValidationError({"items": ["Unknown equipment."]})
        overlaps = find_overlaps(facility_id=facility.id, equipment_pks=pks, start=c.start_date, end=c.end_date,
                                 exclude_contract_pk=c.pk)
        if overlaps:
            raise overlap_conflict(overlaps)
        old = list(AmcCoverage.objects.filter(facility_id=facility.id, amc_contract_id=c.pk).select_related("equipment"))
        AmcCoverage.objects.filter(facility_id=facility.id, amc_contract_id=c.pk).delete()
        AmcCoverage.objects.bulk_create([
            AmcCoverage(facility_id=facility.id, amc_contract_id=c.pk, equipment_id=i["equipment"].pk,
                        allocated_cost=i.get("allocated_cost"), created_by=request.user.id) for i in items])
        audit.record(request=request, action="AMC_COVERAGE_CHANGED", facility_id=facility.id, entity_type="AmcContract",
                     entity_public_id=c.public_id,
                     previous={"equipment": [o.equipment.asset_tag for o in old]},
                     new={"equipment": [eqs[p].asset_tag for p in pks]})
    return c


def _renewal_number(facility_id, base):
    for n in range(1, 50):
        cand = f"{base}-R{n}"
        if not AmcContract.objects.filter(facility_id=facility_id, is_active=True, contract_number__iexact=cand).exists():
            return cand
    raise Conflict("Could not generate a renewal contract number; enter one.")


def renew_contract(*, request, facility, contract, contract_number=None, start_date=None, end_date=None,
                   contract_cost=None):
    uid = request.user.id
    with transaction.atomic():
        old = AmcContract.objects.select_for_update().filter(pk=contract.pk, facility_id=facility.id, is_active=True).first()
        if old is None:
            raise NotFound()
        if AmcContract.objects.filter(facility_id=facility.id, renewed_from_contract_id=old.pk, is_active=True).exists():
            raise Conflict("This contract has already been renewed.")
        start = start_date or old.end_date + timedelta(days=1)
        end = end_date or add_months(start, 12) - timedelta(days=1)
        if end < start:
            raise ValidationError({"end_date": ["Must not be before the start date."]})
        if contract_number:
            number = contract_number.strip()
            if AmcContract.objects.filter(facility_id=facility.id, is_active=True, contract_number__iexact=number).exists():
                raise ValidationError({"contract_number": ["This contract number is already in use."]})
        else:
            number = _renewal_number(facility.id, old.contract_number)
        cov = list(AmcCoverage.objects.filter(facility_id=facility.id, amc_contract_id=old.pk))
        overlaps = find_overlaps(facility_id=facility.id, equipment_pks=[c.equipment_id for c in cov],
                                 start=start, end=end)
        if overlaps:
            raise overlap_conflict(overlaps)
        try:
            with transaction.atomic():
                new = AmcContract.objects.create(
                    facility=facility, contract_number=number, vendor_id=old.vendor_id, contract_type=old.contract_type,
                    start_date=start, end_date=end, contract_cost=old.contract_cost if contract_cost is None else contract_cost,
                    covered_scope=old.covered_scope, exclusions=old.exclusions,
                    visit_frequency_per_year=old.visit_frequency_per_year, response_sla_hours=old.response_sla_hours,
                    uptime_guarantee_percent=old.uptime_guarantee_percent, penalty_terms=old.penalty_terms,
                    renewed_from_contract_id=old.pk, notes=old.notes, created_by=uid, updated_by=uid)
        except IntegrityError:
            raise ValidationError({"contract_number": ["This contract number is already in use."]})
        AmcCoverage.objects.bulk_create([
            AmcCoverage(facility_id=facility.id, amc_contract_id=new.pk, equipment_id=c.equipment_id,
                        allocated_cost=c.allocated_cost, created_by=uid) for c in cov])
        audit.record(request=request, action="AMC_RENEWED", facility_id=facility.id, entity_type="AmcContract",
                     entity_public_id=new.public_id,
                     new={"renewed_from": str(old.public_id), "old_contract_number": old.contract_number,
                          "contract_number": number, "start_date": start, "end_date": end,
                          "equipment_count": len(cov)})
    return new


# ------------------------------------------------------------------ warranties and licences
def _acceptance_dates(facility_id, equipment_pks):
    model = django_apps.get_model(*COMMISSIONING_MODEL)
    rows = model.objects.filter(facility_id=facility_id, equipment_id__in=equipment_pks, is_active=True).order_by("id")
    return {r.equipment_id: r.acceptance_date for r in rows if r.acceptance_date}


def bulk_create_warranties(*, request, facility, equipment_list, common):
    """All-or-nothing. common: warranty_type, vendor, start_date?, end_date? | duration_months?, text fields."""
    if not equipment_list:
        raise ValidationError({"equipment": ["Select at least one equipment."]})
    if len(equipment_list) > 200:
        raise ValidationError({"equipment": ["At most 200 equipment per request."]})
    uid = request.user.id
    accept = _acceptance_dates(facility.id, [e.pk for e in equipment_list])
    errors, rows = [], []
    for eq in equipment_list:
        start = common.get("start_date") or accept.get(eq.pk)
        if start is None:
            errors.append(f"{eq.asset_tag}: no acceptance date on record; enter a start date.")
            continue
        end = common.get("end_date") or add_months(start, common["duration_months"]) - timedelta(days=1)
        if end < start:
            errors.append(f"{eq.asset_tag}: end date is before the start date.")
            continue
        rows.append(Warranty(
            facility=facility, equipment=eq, vendor=common.get("vendor"), warranty_type=common["warranty_type"],
            start_date=start, end_date=end, reference_number=common.get("reference_number"),
            coverage_terms=common.get("coverage_terms"), covered_parts=common.get("covered_parts"),
            exclusions=common.get("exclusions"), notes=common.get("notes"), created_by=uid, updated_by=uid))
    if errors:
        raise ValidationError({"equipment": errors[:50]})
    with transaction.atomic():
        Warranty.objects.bulk_create(rows)
        audit.record(request=request, action="BULK_CREATE", facility_id=facility.id, entity_type="Warranty",
                     new={"created": len(rows), "warranty_type": common["warranty_type"]})
    return len(rows)


def renew_licence(*, request, facility, licence, issue_date, expiry_date, licence_number=None,
                  issuing_authority=None, notes=None):
    if expiry_date < issue_date:
        raise ValidationError({"expiry_date": ["Must not be before the issue date."]})
    uid = request.user.id
    with transaction.atomic():
        old = EquipmentLicence.objects.select_for_update().filter(
            pk=licence.pk, facility_id=facility.id, is_active=True).first()
        if old is None:
            raise NotFound()
        if EquipmentLicence.objects.filter(facility_id=facility.id, renewed_from_licence_id=old.pk,
                                           is_active=True).exists():
            raise Conflict("This licence has already been renewed.")
        new = EquipmentLicence.objects.create(
            facility=facility, equipment_id=old.equipment_id, licence_type=old.licence_type,
            licence_number=licence_number or old.licence_number,
            issuing_authority=issuing_authority or old.issuing_authority, issue_date=issue_date,
            expiry_date=expiry_date, renewed_from_licence_id=old.pk, notes=notes, created_by=uid, updated_by=uid)
        snap = audit.snapshot(new)
        audit.record(request=request, action="CREATE", facility_id=facility.id, entity_type="EquipmentLicence",
                     entity_public_id=new.public_id, new={**snap, "renewed_from": str(old.public_id)},
                     changed_fields=audit.diff(None, snap))
    return new


# ------------------------------------------------------------------ due & expiry
def bucket_for(days_left):
    if days_left < 0:
        return "OVERDUE"
    for code, limit in (("D7", 7), ("D30", 30), ("D60", 60), ("D90", 90)):
        if days_left <= limit:
            return code
    return "LATER"


def _window(today, within_days, bucket):
    if bucket == "OVERDUE":
        return None, today - timedelta(days=1)
    spans = {"D7": (0, 7), "D30": (8, 30), "D60": (31, 60), "D90": (61, 90)}
    if bucket:
        a, b = spans[bucket]
        return today + timedelta(days=a), today + timedelta(days=b)
    return None, today + timedelta(days=within_days)


def _between(qs, field, lo, hi):
    if lo is not None:
        qs = qs.filter(**{f"{field}__gte": lo})
    if hi is not None:
        qs = qs.filter(**{f"{field}__lte": hi})
    return qs.order_by(field, "id")[:CAP]


def _eq(e):
    return None if e is None else {"public_id": str(e.public_id), "asset_tag": e.asset_tag, "name": e.name}


def _row(item_type, src, eq, title, due, today, **extra):
    days = (due - today).days
    return {"item_type": item_type, "source_public_id": str(src.public_id), "equipment": _eq(eq), "title": title,
            "due_date": due, "days_left": days, "bucket": bucket_for(days), **extra}


def _eq_filter(qs, prefix, eq_pk, dept_pk):
    if eq_pk is not None:
        qs = qs.filter(**{f"{prefix}": eq_pk})
    if dept_pk is not None:
        qs = qs.filter(**{f"{prefix.rsplit('equipment', 1)[0]}equipment__{EQUIPMENT_DEPARTMENT_FIELD}": dept_pk})
    return qs


def _due_calibration(fid, today, lo, hi, eq_pk, dept_pk):
    qs = CalibrationSchedule.objects.filter(
        facility_id=fid, is_active=True, equipment__is_active=True,
        equipment__lifecycle_stage="COMMISSIONED").select_related("equipment")
    qs = _eq_filter(qs, "equipment_id", eq_pk, dept_pk)
    return [_row("CALIBRATION", s, s.equipment, "Calibration due", s.next_due_date, today)
            for s in _between(qs, "next_due_date", lo, hi)]


def _due_warranty(fid, today, lo, hi, eq_pk, dept_pk):
    qs = Warranty.objects.filter(facility_id=fid, is_active=True, equipment__is_active=True).select_related("equipment")
    qs = _eq_filter(qs, "equipment_id", eq_pk, dept_pk)
    return [_row("WARRANTY", w, w.equipment, f"{w.warranty_type.title()} warranty expires", w.end_date, today)
            for w in _between(qs, "end_date", lo, hi)]


def _due_licence(fid, today, lo, hi, eq_pk, dept_pk):
    renewed = EquipmentLicence.objects.filter(
        facility_id=fid, is_active=True, renewed_from_licence_id__isnull=False).values("renewed_from_licence_id")
    qs = EquipmentLicence.objects.filter(facility_id=fid, is_active=True, equipment__is_active=True) \
        .exclude(pk__in=renewed).select_related("equipment")
    qs = _eq_filter(qs, "equipment_id", eq_pk, dept_pk)
    return [_row("LICENCE", x, x.equipment, f"{x.licence_type.replace('_', ' ').title()} expires", x.expiry_date, today)
            for x in _between(qs, "expiry_date", lo, hi)]


def _due_amc(fid, today, lo, hi, eq_pk, dept_pk):
    renewed = AmcContract.objects.filter(
        facility_id=fid, is_active=True, renewed_from_contract_id__isnull=False).values("renewed_from_contract_id")
    qs = AmcContract.objects.filter(facility_id=fid, is_active=True).exclude(pk__in=renewed)
    if eq_pk is not None or dept_pk is not None:
        cov = AmcCoverage.objects.filter(facility_id=fid, amc_contract_id=OuterRef("pk"), equipment__is_active=True)
        if eq_pk is not None:
            cov = cov.filter(equipment_id=eq_pk)
        if dept_pk is not None:
            cov = cov.filter(**{f"equipment__{EQUIPMENT_DEPARTMENT_FIELD}": dept_pk})
        qs = qs.filter(Exists(cov))
    return [_row("AMC", c, None, f"AMC {c.contract_number} ends", c.end_date, today)
            for c in _between(qs, "end_date", lo, hi)]


_EQ_ENTITIES = {"warranty": Warranty, "equipment_licence": EquipmentLicence, "calibration_record": CalibrationRecord}


def _doc_equipment(fid, docs):
    by = {}
    for d in docs:
        by.setdefault(d.entity_type, set()).add(d.entity_public_id)
    out = {}
    if "equipment" in by:
        for e in Equipment.objects.filter(facility_id=fid, public_id__in=by["equipment"]):
            out[("equipment", e.public_id)] = e
    for etype, model in _EQ_ENTITIES.items():
        if etype in by:
            for r in model.objects.filter(facility_id=fid, public_id__in=by[etype]).select_related("equipment"):
                out[(etype, r.public_id)] = r.equipment
    return out


def _due_documents(fid, today, lo, hi, eq_pk, dept_pk, can):
    from apps.documents.models import Document
    from apps.documents.registry import all_attachables
    allowed = [et for et, att in all_attachables().items() if can(att.view_permission)]
    if not allowed:
        return []
    qs = Document.objects.filter(facility_id=fid, is_active=True, expiry_date__isnull=False, entity_type__in=allowed)
    filtered = eq_pk is not None or dept_pk is not None
    qs = qs.filter(expiry_date__gte=lo) if lo is not None else qs
    qs = qs.filter(expiry_date__lte=hi) if hi is not None else qs
    docs = list(qs.order_by("expiry_date", "id")[: (4 * CAP if filtered else CAP)])
    eqs = _doc_equipment(fid, docs)
    rows = []
    for d in docs:
        eq = eqs.get((d.entity_type, d.entity_public_id))
        if eq is not None and not eq.is_active:
            continue
        if filtered:
            if eq is None or (eq_pk is not None and eq.pk != eq_pk):
                continue
            if dept_pk is not None and getattr(eq, f"{EQUIPMENT_DEPARTMENT_FIELD}_id", None) != dept_pk:
                continue
        title = getattr(d, "title", None) or getattr(d, "name", None) or "Document"
        rows.append(_row("DOCUMENT", d, eq, f"Document expires: {title}", d.expiry_date, today,
                         entity_type=d.entity_type, entity_public_id=str(d.entity_public_id)))
        if len(rows) >= CAP:
            break
    return rows


def compliance_due(*, facility, can, types=None, within_days=90, bucket=None, equipment_pk=None,
                   department_pk=None, today=None):
    today = today or today_for(facility)
    wanted = [t for t in (types or TYPE_PERMS) if t in TYPE_PERMS and can(TYPE_PERMS[t])]
    lo, hi = _window(today, within_days, bucket)
    lo_exp = lo if lo is not None else today - timedelta(days=OVERDUE_LOOKBACK_DAYS)
    fid, rows = facility.id, []
    if "CALIBRATION" in wanted:
        rows += _due_calibration(fid, today, lo, hi, equipment_pk, department_pk)
    if "WARRANTY" in wanted:
        rows += _due_warranty(fid, today, lo_exp, hi, equipment_pk, department_pk)
    if "AMC" in wanted:
        rows += _due_amc(fid, today, lo_exp, hi, equipment_pk, department_pk)
    if "LICENCE" in wanted:
        rows += _due_licence(fid, today, lo_exp, hi, equipment_pk, department_pk)
    if "DOCUMENT" in wanted:
        rows += _due_documents(fid, today, lo_exp, hi, equipment_pk, department_pk, can)
    rows.sort(key=lambda r: (r["due_date"], r["item_type"], r["source_public_id"]))
    return rows