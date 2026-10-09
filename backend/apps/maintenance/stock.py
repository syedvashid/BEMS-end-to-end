"""Spare-parts ledger. On-hand = sum(quantity) of spare_part_stock_entries; there is no stored balance."""
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import NotFound, ValidationError

from apps.core import audit
from apps.core.errors import Conflict

from .errors import InsufficientStock
from .models import SparePart, SparePartStockEntry
from .services import _event, _lock_wo

PART_STATUSES = ("IN_PROGRESS", "WAITING_PARTS", "COMPLETED")
ZERO = Decimal("0")


def on_hand(spare_part):
    return SparePartStockEntry.objects.filter(spare_part_id=spare_part.pk).aggregate(t=Sum("quantity"))["t"] or ZERO


def _lock_part(spare_part, facility_id):
    sp = SparePart.objects.select_for_update().filter(pk=spare_part.pk, facility_id=facility_id, is_active=True).first()
    if sp is None:
        raise NotFound()
    return sp


def _positive(q, field="quantity"):
    q = Decimal(q)
    if q <= 0:
        raise ValidationError({field: ["Must be greater than zero."]})
    return q


def _audit(request, action, sp, entry, extra):
    audit.record(request=request, action=action, facility_id=sp.facility_id, entity_type="SparePart",
                 entity_public_id=sp.public_id,
                 new={"entry": str(entry.public_id), "part_code": sp.part_code,
                      "quantity": format(entry.quantity, "f"), **extra})


def issue_part(*, request, wo, spare_part, quantity, unit_cost=None):
    q = _positive(quantity)
    with transaction.atomic():
        wo = _lock_wo(wo)                                  # lock order: work order, then part
        if wo.status not in PART_STATUSES:
            raise Conflict("Parts can only be issued while the work order is in progress, waiting for parts or completed.")
        sp = _lock_part(spare_part, wo.facility_id)
        available = on_hand(sp)
        if available < q:
            raise InsufficientStock(available)
        entry = SparePartStockEntry.objects.create(
            facility_id=wo.facility_id, spare_part=sp, entry_type="CONSUMPTION", quantity=-q, work_order=wo,
            unit_cost=unit_cost if unit_cost is not None else sp.standard_unit_cost, created_by=request.user.id)
        _event(wo, "PART_ISSUED", request.user.id, wo.status, wo.status,
               f"{format(q, 'f')} {sp.unit} x {sp.part_code}")
        _audit(request, "PART_CONSUMED", sp, entry, {"work_order": wo.wo_number})
    return entry


def return_part(*, request, wo, entry, quantity=None):
    with transaction.atomic():
        wo = _lock_wo(wo)
        if wo.status not in PART_STATUSES:
            raise Conflict("Parts can only be returned while the work order is in progress, waiting for parts or completed.")
        sp = _lock_part(entry.spare_part, wo.facility_id)
        orig = SparePartStockEntry.objects.filter(pk=entry.pk, work_order_id=wo.pk, entry_type="CONSUMPTION").first()
        if orig is None:
            raise NotFound()
        returned = SparePartStockEntry.objects.filter(related_entry_id=orig.pk, entry_type="RETURN") \
            .aggregate(t=Sum("quantity"))["t"] or ZERO
        returnable = -orig.quantity - returned
        q = returnable if quantity is None else _positive(quantity)
        if q <= 0 or q > returnable:
            raise ValidationError({"quantity": [f"At most {format(returnable, 'f')} can be returned."]})
        ret = SparePartStockEntry.objects.create(
            facility_id=wo.facility_id, spare_part=sp, entry_type="RETURN", quantity=q, work_order=wo,
            related_entry=orig, unit_cost=orig.unit_cost, created_by=request.user.id)
        _event(wo, "PART_RETURNED", request.user.id, wo.status, wo.status,
               f"{format(q, 'f')} {sp.unit} x {sp.part_code}")
        _audit(request, "PART_RETURNED", sp, ret, {"work_order": wo.wo_number})
    return ret


def receive_stock(*, request, spare_part, quantity, unit_cost=None, supplier_vendor=None, reference_note=None):
    q = _positive(quantity)
    with transaction.atomic():
        sp = _lock_part(spare_part, spare_part.facility_id)
        if supplier_vendor is not None and (
                supplier_vendor.facility_id != sp.facility_id or not supplier_vendor.is_active):
            raise ValidationError({"supplier_vendor": ["Unknown reference."]})
        entry = SparePartStockEntry.objects.create(
            facility_id=sp.facility_id, spare_part=sp, entry_type="RECEIPT", quantity=q, unit_cost=unit_cost,
            supplier_vendor=supplier_vendor, reference_note=reference_note, created_by=request.user.id)
        _audit(request, "STOCK_RECEIPT", sp, entry, {})
    return entry


def adjust_stock(*, request, spare_part, quantity, reason):
    q = Decimal(quantity)
    if q == 0:
        raise ValidationError({"quantity": ["Must not be zero."]})
    if not (reason or "").strip():
        raise ValidationError({"reason": ["This field is required."]})
    with transaction.atomic():
        sp = _lock_part(spare_part, spare_part.facility_id)
        available = on_hand(sp)
        if available + q < 0:
            raise InsufficientStock(available)
        entry = SparePartStockEntry.objects.create(
            facility_id=sp.facility_id, spare_part=sp, entry_type="ADJUSTMENT", quantity=q, reason=reason.strip(),
            created_by=request.user.id)
        _audit(request, "STOCK_ADJUSTMENT", sp, entry, {"reason": reason.strip()})
    return entry
