from datetime import timedelta

import django_filters as df
from django.db.models import DateField, ExpressionWrapper, F, Exists, OuterRef, Q

from apps.maintenance.services import today_for

from .models import AmcContract, AmcCoverage, CalibrationRecord, CalibrationSchedule, EquipmentLicence, Warranty, WarrantyClaim


def _today(fs):
    return today_for(fs.request.bems.facility)


class CalibrationScheduleFilter(df.FilterSet):
    equipment = df.UUIDFilter(field_name="equipment__public_id")
    category = df.UUIDFilter(field_name="equipment__equipment_model__category__public_id")
    status = df.ChoiceFilter(choices=[(c, c) for c in ("OK", "DUE_SOON", "OVERDUE")], method="f_status")
    due_within_days = df.NumberFilter(method="f_due_within")
    search = df.CharFilter(method="f_search")

    class Meta:
        model = CalibrationSchedule
        fields = []

    def f_status(self, qs, name, value):
        today = _today(self)
        qs = qs.annotate(due_start=ExpressionWrapper(F("next_due_date") - F("lead_days"), output_field=DateField()))
        if value == "OVERDUE":
            return qs.filter(next_due_date__lt=today)
        if value == "DUE_SOON":
            return qs.filter(next_due_date__gte=today, due_start__lte=today)
        return qs.filter(due_start__gt=today)

    def f_due_within(self, qs, name, value):
        return qs.filter(next_due_date__lte=_today(self) + timedelta(days=int(value)))

    def f_search(self, qs, name, value):
        return qs.filter(Q(equipment__asset_tag__icontains=value) | Q(equipment__name__icontains=value))


class CalibrationRecordFilter(df.FilterSet):
    equipment = df.UUIDFilter(field_name="equipment__public_id")
    result = df.ChoiceFilter(choices=[("PASS", "PASS"), ("FAIL", "FAIL")])
    performed_from = df.DateFilter(field_name="performed_date", lookup_expr="gte")
    performed_to = df.DateFilter(field_name="performed_date", lookup_expr="lte")
    unresolved_failure = df.BooleanFilter(method="f_unresolved")

    class Meta:
        model = CalibrationRecord
        fields = []

    def f_unresolved(self, qs, name, value):
        later = CalibrationRecord.objects.filter(equipment_id=OuterRef("equipment_id")).filter(
            Q(performed_date__gt=OuterRef("performed_date")) |
            Q(performed_date=OuterRef("performed_date"), id__gt=OuterRef("id")))
        failed = qs.filter(result="FAIL").filter(~Exists(later))
        return failed if value else qs.exclude(pk__in=failed.values("pk"))


class WarrantyFilter(df.FilterSet):
    equipment = df.UUIDFilter(field_name="equipment__public_id")
    vendor = df.UUIDFilter(field_name="vendor__public_id")
    active_on = df.DateFilter(method="f_active_on")
    expiring_within_days = df.NumberFilter(method="f_expiring")

    class Meta:
        model = Warranty
        fields = []

    def f_active_on(self, qs, name, value):
        return qs.filter(start_date__lte=value, end_date__gte=value)

    def f_expiring(self, qs, name, value):
        t = _today(self)
        return qs.filter(end_date__gte=t, end_date__lte=t + timedelta(days=int(value)))


class WarrantyClaimFilter(df.FilterSet):
    warranty = df.UUIDFilter(field_name="warranty__public_id")
    equipment = df.UUIDFilter(field_name="equipment__public_id")
    status = df.ChoiceFilter(choices=[(s, s) for s in ("RAISED", "ACCEPTED", "REJECTED", "RESOLVED")])

    class Meta:
        model = WarrantyClaim
        fields = []


class AmcContractFilter(df.FilterSet):
    vendor = df.UUIDFilter(field_name="vendor__public_id")
    contract_type = df.ChoiceFilter(choices=[("COMPREHENSIVE", "COMPREHENSIVE"), ("NON_COMPREHENSIVE", "NON_COMPREHENSIVE")])
    equipment = df.UUIDFilter(method="f_equipment")
    active_on = df.DateFilter(method="f_active_on")
    expiring_within_days = df.NumberFilter(method="f_expiring")

    class Meta:
        model = AmcContract
        fields = []

    def f_equipment(self, qs, name, value):
        return qs.filter(Exists(AmcCoverage.objects.filter(amc_contract_id=OuterRef("pk"),
                                                           equipment__public_id=value)))

    def f_active_on(self, qs, name, value):
        return qs.filter(start_date__lte=value, end_date__gte=value)

    def f_expiring(self, qs, name, value):
        t = _today(self)
        return qs.filter(end_date__gte=t, end_date__lte=t + timedelta(days=int(value)))


class EquipmentLicenceFilter(df.FilterSet):
    equipment = df.UUIDFilter(field_name="equipment__public_id")
    licence_type = df.ChoiceFilter(choices=[(t, t) for t in (
        "AERB_LICENCE", "AERB_QA_CERTIFICATE", "PRESSURE_VESSEL_INSPECTION", "ELECTRICAL_SAFETY_TEST", "OTHER")])
    expiring_within_days = df.NumberFilter(method="f_expiring")

    class Meta:
        model = EquipmentLicence
        fields = []

    def f_expiring(self, qs, name, value):
        t = _today(self)
        return qs.filter(expiry_date__gte=t, expiry_date__lte=t + timedelta(days=int(value)))