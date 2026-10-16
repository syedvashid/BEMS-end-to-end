"""Picks QUEUED report runs (SELECT ... FOR UPDATE SKIP LOCKED) and generates them. Run every minute."""
from django.core.management.base import BaseCommand

from apps.reports import services


class Command(BaseCommand):
    help = "Process queued report exports."

    def add_arguments(self, parser):
        parser.add_argument("--max", type=int, default=20, help="Most runs to process in one invocation")

    def handle(self, *args, **opts):
        stuck = services.fail_stuck()
        done = failed = 0
        for _ in range(opts["max"]):
            run_id = services.claim_next()
            if run_id is None:
                break
            if services.process_run(run_id):
                done += 1
            else:
                failed += 1
        self.stdout.write(f"completed={done} failed={failed} timed_out={stuck}")
