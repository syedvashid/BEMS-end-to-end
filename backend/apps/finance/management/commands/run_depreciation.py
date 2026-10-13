from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.finance import services
from apps.foundation.models import Facility


class Command(BaseCommand):
    help = "Monthly depreciation catch-up for every active facility (or one). Run from cron."

    def add_arguments(self, parser):
        parser.add_argument("--facility", help="Facility code (default: all active facilities).")
        parser.add_argument("--month", help="Target month YYYY-MM (default: the last completed month).")

    def handle(self, *args, **opts):
        month = None
        if opts.get("month"):
            try:
                y, m = opts["month"].split("-")
                month = date(int(y), int(m), 1)
            except ValueError:
                raise CommandError("--month must look like 2026-09.")
        qs = Facility.objects.filter(is_active=True)
        if opts.get("facility"):
            qs = qs.filter(code__iexact=opts["facility"])
            if not qs.exists():
                raise CommandError("Unknown facility code.")
        failed = False
        for facility in qs.order_by("id"):
            try:
                _, s = services.run_depreciation(facility=facility, target_month=month, request=None)
                self.stdout.write(f"{facility.code}: {s['run_period']} processed={s['assets_processed']} "
                                  f"entries={s['entries_created']} charge={s['total_charge']} "
                                  f"no_policy={s['skipped_no_policy']} no_cost={s['skipped_no_cost']} "
                                  f"no_start={s['skipped_no_start_date']} failed={s['failed_count']}")
            except Exception as exc:   # one facility must not stop the others
                failed = True
                self.stderr.write(f"{facility.code}: FAILED ({type(exc).__name__}: {getattr(exc, 'detail', exc)})")
        if failed:
            raise CommandError("One or more facilities failed.")
