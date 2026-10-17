"""Weekly (or after an outage): create the charges that are missing for released allocations and usage logs.
Examples:  python manage.py generate_missing_charges --facility MAIN --from 2026-10-01 --to 2026-10-15"""
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError

from apps.billing import services
from apps.foundation.models import Facility
from apps.reports.common import facility_today


class Command(BaseCommand):
    help = "Sweep a date range and create missing charge records (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--facility", help="Facility code (default: every active facility).")
        parser.add_argument("--from", dest="date_from", help="First date (YYYY-MM-DD). Default: 7 days ago.")
        parser.add_argument("--to", dest="date_to", help="Last date (YYYY-MM-DD). Default: today.")

    def handle(self, *args, **opts):
        facilities = Facility.objects.filter(is_active=True)
        if opts["facility"]:
            facilities = facilities.filter(code__iexact=opts["facility"])
            if not facilities.exists():
                raise CommandError("Unknown facility code.")
        try:
            d_from = date.fromisoformat(opts["date_from"]) if opts["date_from"] else None
            d_to = date.fromisoformat(opts["date_to"]) if opts["date_to"] else None
        except ValueError:
            raise CommandError("Dates must be YYYY-MM-DD.")
        failed = 0
        for facility in facilities.order_by("code"):
            today = facility_today(facility)
            res = services.generate_missing_charges(facility, d_from or today - timedelta(days=7), d_to or today)
            failed += res["failed"]
            self.stdout.write(f"{facility.code}: allocations {res['allocations']}, usage logs {res['usage_logs']}, "
                              f"created {res['created']}, already charged {res['already']}, failed {res['failed']}")
        if failed:
            raise CommandError(f"{failed} source(s) failed; see CHARGE_CALCULATION_FAILED in the audit trail.")
