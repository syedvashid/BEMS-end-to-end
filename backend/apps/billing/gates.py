"""Delete / edit gates of Phase 11, one clearly named place each. They raise 409 conflict."""
from apps.core.errors import Conflict


def ensure_usage_log_unbilled(instance):
    """A usage log cannot be edited or deleted while it has a live charge: a CHARGE record that is pending review or
    approved. Cancelled records and reversed charges (REVERSED original plus its REVERSAL record) do not block."""
    from .models import ChargeRecord
    if ChargeRecord.objects.filter(
            facility_id=instance.facility_id, usage_log_id=instance.pk, record_type="CHARGE",
            status__in=("PENDING_REVIEW", "APPROVED")).exists():
        raise Conflict("This usage log has charge records. Cancel or reverse the charges first, then try again.")


def mapping_count_for_item(instance):
    from .models import ChargeMapping
    return ChargeMapping.objects.filter(
        facility_id=instance.facility_id, charge_item_id=instance.pk, is_active=True).count()


def ensure_item_deletable(instance):
    n = mapping_count_for_item(instance)
    if n:
        raise Conflict(f"Cannot delete: {n} active charge mapping(s) still use this charge item.")


def category_mapping_count(instance):
    """Used by the equipment category delete gate (Phase 2)."""
    from .models import ChargeMapping
    return ChargeMapping.objects.filter(
        facility_id=instance.facility_id, category_id=instance.pk, is_active=True).count()
