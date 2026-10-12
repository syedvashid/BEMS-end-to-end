from datetime import datetime, time, timedelta

import django_filters as df
from django.db.models import Exists, OuterRef, Q

from apps.maintenance.services import facility_tz

from .models import (
    EquipmentIncident, PhysicalVerification, PhysicalVerificationItem, RecallAffectedUnit, RecallNotice,
    RecallNoticeModel,
)


def _choices(*values):
    return [(v, v) for v in values]


def _day_start(fs, day, plus_days=0):
    tz = facility_tz(fs.request.bems.facility)
    return datetime.combine(day + timedelta(days=plus_days), time.min, tzinfo=tz)


class IncidentFilter(df.FilterSet):
    status = df.ChoiceFilter(choices=_choices("REPORTED", "UNDER_INVESTIGATION", "ACTION_TAKEN", "CLOSED"))
    severity = df.ChoiceFilter(choices=_choices("NO_HARM", "MINOR", "MODERATE", "SEVERE", "DEATH"))
    incident_type = df.ChoiceFilter(choices=_choices("MALFUNCTION", "USE_ERROR", "NEAR_MISS", "OTHER"))
    equipment = df.UUIDFilter(field_name="equipment__public_id")
    department = df.UUIDFilter(field_name="department__public_id")
    occurred_from = df.DateFilter(method="f_from")
    occurred_to = df.DateFilter(method="f_to")
    reportable = df.BooleanFilter(field_name="reportable_to_regulator")
    mine = df.BooleanFilter(method="f_mine")
    search = df.CharFilter(method="f_search")

    class Meta:
        model = EquipmentIncident
        fields = []

    def f_from(self, qs, name, value):
        return qs.filter(occurred_at__gte=_day_start(self, value))

    def f_to(self, qs, name, value):
        return qs.filter(occurred_at__lt=_day_start(self, value, 1))

    def f_mine(self, qs, name, value):
        return qs.filter(created_by=self.request.user.id) if value else qs

    def f_search(self, qs, name, value):
        return qs.filter(Q(incident_number__icontains=value) | Q(description__icontains=value))


class RecallNoticeFilter(df.FilterSet):
    status = df.ChoiceFilter(choices=_choices("OPEN", "CLOSED", "CANCELLED"))
    urgency = df.ChoiceFilter(choices=_choices("LOW", "MEDIUM", "HIGH", "CRITICAL"))
    notice_type = df.ChoiceFilter(choices=_choices("RECALL", "FIELD_SAFETY_NOTICE", "SAFETY_ALERT", "ADVISORY"))
    model = df.UUIDFilter(method="f_model")
    search = df.CharFilter(method="f_search")

    class Meta:
        model = RecallNotice
        fields = []

    def f_model(self, qs, name, value):
        return qs.filter(Exists(RecallNoticeModel.objects.filter(
            recall_notice_id=OuterRef("pk"), equipment_model__public_id=value)))

    def f_search(self, qs, name, value):
        return qs.filter(Q(notice_number__icontains=value) | Q(title__icontains=value)
                         | Q(reference_number__icontains=value))


class RecallUnitFilter(df.FilterSet):
    status = df.ChoiceFilter(choices=_choices("PENDING", "ACTION_COMPLETED", "NOT_APPLICABLE"))
    search = df.CharFilter(method="f_search")

    class Meta:
        model = RecallAffectedUnit
        fields = []

    def f_search(self, qs, name, value):
        return qs.filter(Q(equipment__asset_tag__icontains=value) | Q(equipment__name__icontains=value)
                         | Q(equipment__serial_number__icontains=value))


class VerificationFilter(df.FilterSet):
    status = df.ChoiceFilter(choices=_choices("PLANNED", "IN_PROGRESS", "COMPLETED", "CANCELLED"))
    scope_type = df.ChoiceFilter(choices=_choices("FACILITY", "DEPARTMENT", "LOCATION"))
    planned_from = df.DateFilter(field_name="planned_date", lookup_expr="gte")
    planned_to = df.DateFilter(field_name="planned_date", lookup_expr="lte")
    search = df.CharFilter(method="f_search")

    class Meta:
        model = PhysicalVerification
        fields = []

    def f_search(self, qs, name, value):
        return qs.filter(Q(verification_number__icontains=value) | Q(title__icontains=value))


class VerificationItemFilter(df.FilterSet):
    result = df.ChoiceFilter(choices=_choices("PENDING", "FOUND", "FOUND_ELSEWHERE", "MISSING", "UNEXPECTED"))
    resolution = df.ChoiceFilter(choices=_choices("NONE", "LOCATION_UPDATED", "CONFIRMED_MISSING", "FOUND_LATER", "IGNORED"))
    search = df.CharFilter(method="f_search")

    class Meta:
        model = PhysicalVerificationItem
        fields = []

    def f_search(self, qs, name, value):
        return qs.filter(Q(equipment__asset_tag__icontains=value) | Q(equipment__name__icontains=value)
                         | Q(equipment__serial_number__icontains=value))
