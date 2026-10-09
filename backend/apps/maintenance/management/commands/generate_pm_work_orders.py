"""Daily cron: create preventive work orders for plans that are due (next_due_date - lead_days <= today).

    python manage.py generate_pm_work_orders [--date YYYY-MM-DD] [--facility CODE]

Idempotent: a work order already existing for (plan, due date) is never recreated (the partial unique index is
the final guard). Overdue is NOT marked here; it is computed at query time.
"""
import logging
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.foundation.models import Facility
from apps.maintenance import services
from apps.maintenance.models import MaintenancePlan

log = logging.getLogger("bems.scheduler")


class Command(BaseCommand):
    help = "Generate preventive work orders for due maintenance plans."

    def add_arguments(self, parser):
        parser.add_argument("--date", help="Treat this date (YYYY-MM-DD) as today.")
        parser.add_argument("--facility", help="Only this facility code.")

    def handle(self, *args, **opts):
        forced = None
        if opts.get("date"):
            try:
                forced = date.fromisoformat(opts["date"])
            except ValueError:
                raise CommandError("--date must be YYYY-MM-DD")
        facilities = Facility.objects.filter(is_active=True)
        if opts.get("facility"):
            facilities = facilities.filter(code__iexact=opts["facility"])
        request = services.SystemRequest()
        totals = {"created": 0, "skipped": 0, "errors": 0}
        for fac in facilities.order_by("code"):
            today = forced or services.today_for(fac)
            plans = MaintenancePlan.objects.filter(facility_id=fac.id, is_active=True).extra(
                where=["maintenance_plans.next_due_date - maintenance_plans.lead_days <= %s"], params=[today],
            ).order_by("next_due_date", "id")
            created = skipped = errors = 0
            for plan in plans:
                try:
                    wo = services.create_pm_work_order(request=request, plan=plan, due_date=plan.next_due_date)
                except Exception as exc:   # one bad plan must not stop the run (e.g. equipment no longer commissioned)
                    errors += 1
                    log.warning("plan %s skipped: %s", plan.public_id, exc)
                    continue
                if wo is None:
                    skipped += 1
                else:
                    created += 1
            self.stdout.write(f"{fac.code}: date={today} created={created} skipped={skipped} errors={errors}")
            totals["created"] += created
            totals["skipped"] += skipped
            totals["errors"] += errors
        self.stdout.write(f"TOTAL created={totals['created']} skipped={totals['skipped']} errors={totals['errors']}")
