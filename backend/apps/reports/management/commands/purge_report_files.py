"""Deletes expired report files and marks the runs EXPIRED (audit REPORT_FILES_PURGED, actor system)."""
from django.core.management.base import BaseCommand

from apps.reports import services


class Command(BaseCommand):
    help = "Purge expired report files."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=None,
                            help="Retention in days (default: BEMS_REPORT_RETENTION_DAYS, 14)")

    def handle(self, *args, **opts):
        n = services.purge_expired(opts["days"])
        self.stdout.write(f"purged={n}")
