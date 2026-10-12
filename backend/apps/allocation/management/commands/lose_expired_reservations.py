"""Daily cron: settle past CONFIRMED reservations.

    python manage.py close_expired_reservations [--facility CODE]

FULFILLED when an active usage log of the equipment overlaps the booking window, otherwise NO_SHOW.
Grace period: env BEMS_RESERVATION_GRACE_MINUTES (default 60). Idempotent.
"""
from django.core.management.base import BaseCommand

from apps.allocation import services
from apps.foundation.models import Facility
from apps.maintenance.services import SystemRequest


class _Req(SystemRequest):
    path = "manage.py close_expired_reservations"


class Command(BaseCommand):
    help = "Settle past reservations as FULFILLED or NO_SHOW."

    def add_arguments(self, parser):
        parser.add_argument("--facility", help="Only this facility code.")

    def handle(self, *args, **opts):
        facilities = Facility.objects.filter(is_active=True)
        if opts.get("facility"):
            facilities = facilities.filter(code__iexact=opts["facility"])
        total = {"FULFILLED": 0, "NO_SHOW": 0}
        for fac in facilities.order_by("code"):
            c = services.close_expired_reservations(request=_Req(), facility=fac)
            self.stdout.write(f"{fac.code}: fulfilled={c['FULFILLED']} no_show={c['NO_SHOW']}")
            for k in total:
                total[k] += c[k]
        self.stdout.write(f"TOTAL fulfilled={total['FULFILLED']} no_show={total['NO_SHOW']}")