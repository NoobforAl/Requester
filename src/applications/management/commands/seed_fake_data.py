"""Fill a development database with lots of realistic, random (Faker) data.

Unlike ``seed_demo_data`` (a few fixed accounts with a known password), this makes
volume: enough employers, postings, candidates and applications for the pages,
dashboards and load tests to show something. Example::

    python manage.py seed_fake_data --employers 20 --postings 200 \\
        --candidates 300 --applications 1500 --seed 42

* Only runs with ``DJANGO_DEBUG`` on, and needs faker (a dev dependency).
* Fake usernames start with ``fake_s<seed>_``; ``--wipe-fake`` first deletes every
  ``fake_`` user (and by cascade their profiles, postings, applications...).
* Running it again with the same seed and counts creates nothing new.
* Fake accounts cannot log in, except the first fake employer and candidate when
  ``FAKE_DATA_PASSWORD`` is set (``fake_s42_emp00000`` / ``fake_s42_cand00000``).
* Rows are bulk inserted (no signals), so the new postings and applications are
  indexed in Elasticsearch here when autosync is on.
"""

import os
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser


class Command(BaseCommand):
    help = "Insert lots of fake (Faker) employers, postings, candidates, applications."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--employers", type=int, default=20)
        parser.add_argument("--postings", type=int, default=200)
        parser.add_argument("--candidates", type=int, default=300)
        parser.add_argument("--applications", type=int, default=1500)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument(
            "--wipe-fake",
            action="store_true",
            help="Delete every fake_ user (with cascades) before seeding.",
        )
        parser.add_argument("--batch-size", type=int, default=500)

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "Fake data is for development only, so this command only runs with "
                "DJANGO_DEBUG on."
            )
        try:
            import faker  # noqa: F401, PLC0415 - only checks that faker is installed

            from applications import fake_data  # noqa: PLC0415 - needs faker
        except ImportError as error:  # faker is a dev dependency
            raise CommandError(
                "faker is not installed (it is a dev dependency): run `uv sync` with "
                "the dev group, or build the dev Docker image."
            ) from error
        for name in ("employers", "postings", "candidates", "applications"):
            if options[name] < 0:
                raise CommandError(f"--{name} must be 0 or more.")

        started = time.perf_counter()
        if options["wipe_fake"]:
            deleted = fake_data.wipe_fake_users()
            self.stdout.write(f"Deleted {deleted} fake users (with their data).")

        seed = options["seed"]
        gen = fake_data.FakeDataGenerator(
            seed, prefix=f"{fake_data.FAKE_PREFIX}s{seed}_"
        )
        self.stdout.write(f"Seeding fake data (seed {seed})...")
        result = fake_data.seed_database(
            gen,
            employers=options["employers"],
            postings=options["postings"],
            candidates=options["candidates"],
            applications=options["applications"],
            password=os.environ.get("FAKE_DATA_PASSWORD", ""),
            batch_size=options["batch_size"],
            log=self.stdout.write,
        )
        indexed = 0
        try:
            indexed = fake_data.index_in_search(result, options["batch_size"])
        except Exception as error:  # search is optional in dev
            self.stderr.write(
                f"Could not index the fake data in Elasticsearch ({error}); "
                "run `manage.py search_index --rebuild -f`."
            )
        counts = ", ".join(f"{count} {name}" for name, count in result.created.items())
        elapsed = time.perf_counter() - started
        self.stdout.write(
            self.style.SUCCESS(
                f"Fake data ready in {elapsed:.2f}s: {counts}"
                + (f"; {indexed} search documents indexed." if indexed else ".")
            )
        )
