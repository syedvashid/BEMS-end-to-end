from .models import AmcContract, CalibrationRecord, Warranty


def vendor_compliance_blockers(vendor):
    """Readable reasons a vendor cannot be deleted (empty list = no compliance record uses it)."""
    fid, pk, out = vendor.facility_id, vendor.pk, []
    n = Warranty.objects.filter(facility_id=fid, vendor_id=pk, is_active=True).count()
    if n:
        out.append(f"{n} active warranties")
    n = AmcContract.objects.filter(facility_id=fid, vendor_id=pk, is_active=True).count()
    if n:
        out.append(f"{n} active AMC contracts")
    n = CalibrationRecord.objects.filter(facility_id=fid, performer_vendor_id=pk).count()
    if n:
        out.append(f"{n} calibration records")
    return out