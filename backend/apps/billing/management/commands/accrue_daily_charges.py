"""Nightly: create the charges of every completed day block of active DAILY allocations (idempotent).
Examples:  python manage.py accrue_daily_charges
           python manage.py accrue_daily_charges --facility MAIN --date 2026-10-15"""
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.billing import services
from apps.foundation.models import Facility
from apps.reports.common import day_start, facility_tz


class Command(BaseCommand):
    help = "Accrue daily charges for long-running DAILY allocations."

    def add_arguments(self, parser):
        parser.add_argument("--facility", help="Facility code (default: every active facility).")
        parser.add_argument("--date", help="Treat this facility date (YYYY-MM-DD) as today.")

    def handle(self, *args, **opts):
        facilities = Facility.objects.filter(is_active=True)
        if opts["facility"]:
            facilities = facilities.filter(code__iexact=opts["facility"])
            if not facilities.exists():
                raise CommandError("Unknown facility code.")
        try:
            on = date.fromisoformat(opts["date"]) if opts["date"] else None
        except ValueError:
            raise CommandError("--date must be YYYY-MM-DD.")
        failed = 0
        for facility in facilities.order_by("code"):
            as_of = day_start(on, facility_tz(facility)) if on else None
            res = services.accrue_daily_charges(facility, as_of=as_of)
            failed += res["failed"]
            self.stdout.write(f"{facility.code}: scanned {res['scanned']}, created {res['created']}, "
                              f"already charged {res['already']}, failed {res['failed']}")
        if failed:
            raise CommandError(f"{failed} allocation(s) failed; see CHARGE_CALCULATION_FAILED in the audit trail.")
