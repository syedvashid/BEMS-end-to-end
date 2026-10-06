from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Verify the audit_log hash chain. Exits with code 1 if it is broken."

    def handle(self, *args, **options):
        with connection.cursor() as cur:
            cur.execute("SELECT verify_audit_chain()")
            broken = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM audit_log")
            total = cur.fetchone()[0]
        if broken is not None:
            raise CommandError(f"Audit chain BROKEN at audit_log.id = {broken}")
        self.stdout.write(self.style.SUCCESS(f"Audit chain OK ({total} rows)"))