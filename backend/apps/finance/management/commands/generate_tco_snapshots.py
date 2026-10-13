from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.finance import tco
from apps.foundation.models import Facility


class Command(BaseCommand):
    help = "Generate TCO snapshots (idempotent per equipment and date). Run from cron."

    def add_arguments(self, parser):
        parser.add_argument("--facility", help="Facility code (default: all active facilities).")
        parser.add_argument("--as-of", dest="as_of", help="Date YYYY-MM-DD (default: today in the facility timezone).")

    def handle(self, *args, **opts):
        as_of = None
        if opts.get("as_of"):
            try:
                as_of = date.fromisoformat(opts["as_of"])
            except ValueError:
                raise CommandError("--as-of must look like 2026-09-30.")
        qs = Facility.objects.filter(is_active=True)
        if opts.get("facility"):
            qs = qs.filter(code__iexact=opts["facility"])
            if not qs.exists():
                raise CommandError("Unknown facility code.")
        failed = False
        for facility in qs.order_by("id"):
            try:
                s = tco.generate_tco_snapshots(facility=facility, as_of_date=as_of, request=None)
                self.stdout.write(f"{facility.code}: {s['as_of_date']} created={s['created']} "
                                  f"skipped_existing={s['skipped_existing']} considered={s['equipment_considered']}")
            except Exception as exc:
                failed = True
                self.stderr.write(f"{facility.code}: FAILED ({type(exc).__name__}: {getattr(exc, 'detail', exc)})")
        if failed:
            raise CommandError("One or more facilities failed.")
