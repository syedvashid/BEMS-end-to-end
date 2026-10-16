"""Nightly rebuild and backfill of equipment_daily_stats.
Examples:
  python manage.py rebuild_daily_stats                          # yesterday, every active facility
  python manage.py rebuild_daily_stats --facility MAIN --from 2026-01-01 --to 2026-03-31
  python manage.py rebuild_daily_stats --facility MAIN --equipment AST-0001 --from 2026-09-01 --to 2026-09-30"""
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from rest_framework.exceptions import APIException, ValidationError

from apps.equipment.models import Equipment
from apps.foundation.models import Facility
from apps.reports.common import facility_today
from apps.reports.stats import rebuild_daily_stats


def _date(value):
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise CommandError(f"Invalid date: {value} (use YYYY-MM-DD)")


class Command(BaseCommand):
    help = "Rebuild equipment_daily_stats for a date range (default: yesterday)."

    def add_arguments(self, parser):
        parser.add_argument("--facility", help="Facility code (default: all active facilities)")
        parser.add_argument("--from", dest="date_from", help="First date, YYYY-MM-DD")
        parser.add_argument("--to", dest="date_to", help="Last date, YYYY-MM-DD")
        parser.add_argument("--equipment", help="Asset tag (needs --facility)")

    def handle(self, *args, **opts):
        facilities = Facility.objects.filter(is_active=True)
        if opts["facility"]:
            facilities = facilities.filter(code__iexact=opts["facility"])
            if not facilities.exists():
                raise CommandError("Unknown facility.")
        if opts["equipment"] and not opts["facility"]:
            raise CommandError("--equipment needs --facility.")
        failures = 0
        for fac in facilities.order_by("id"):
            yesterday = facility_today(fac) - timedelta(days=1)
            d_from = _date(opts["date_from"]) if opts["date_from"] else yesterday
            d_to = _date(opts["date_to"]) if opts["date_to"] else yesterday
            eq = None
            if opts["equipment"]:
                eq = Equipment.objects.filter(facility_id=fac.id, asset_tag__iexact=opts["equipment"],
                                              is_active=True).first()
                if eq is None:
                    raise CommandError("Unknown asset tag in this facility.")
            try:
                r = rebuild_daily_stats(fac, d_from, d_to, equipment=eq)
                self.stdout.write(f"{fac.code}: {r['equipment_processed']} equipment, {r['rows_written']} rows, "
                                  f"{d_from}..{d_to}, {r['seconds']}s")
            except (APIException, ValidationError) as exc:
                failures += 1
                self.stderr.write(f"{fac.code}: skipped ({exc.detail if hasattr(exc, 'detail') else exc})")
        if failures:
            raise CommandError(f"{failures} facility run(s) did not complete.")
