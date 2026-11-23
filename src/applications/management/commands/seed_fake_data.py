"""Fill a development database with lots of realistic, random (Faker) data.

Unlike ``seed_demo_data`` (a few fixed accounts with a known password), this makes
volume: enough employers, postings, candidates and applications for the pages,
dashboards and load tests to show something. Examples::

    python manage.py seed_fake_data                  # --scale large (the default)
    python manage.py seed_fake_data --scale small    # fast, for CI and tests
    python manage.py seed_fake_data --scale medium --applications 5000 --seed 7

* ``--scale small|medium|large`` picks the counts (see ``fake_data.SCALES``);
  an explicit ``--employers``/``--postings``/``--candidates``/``--applications``
  wins over the preset.
* Only runs with ``DJANGO_DEBUG`` on, and needs faker (a dev dependency).
* Fake usernames start with ``fake_s<seed>_``; ``--wipe-fake`` first deletes every
  ``fake_`` user (and by cascade their profiles, postings, applications...).
* Running it again with the same seed and counts creates nothing new.
* Fake accounts cannot log in, except the first fake employer and candidate when
  ``FAKE_DATA_PASSWORD`` is set (``fake_s42_emp00000`` / ``fake_s42_cand00000``).
  Those two are also the busiest accounts, the best ones to look around with.
* Big runs store one shared resume PDF instead of one per application
  (``--shared-resume`` / ``--no-shared-resume`` to choose).
* Rows are bulk inserted with backdated timestamps. Logstash's minute-by-minute
  sync only picks up rows changed since its last run, so rows seeded into a
  database it already copied show in Elasticsearch after the nightly full sync,
  or at once with ``make analytics-resync`` (docs/analytics.md).
"""

import argparse
import os
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

#: Must match the keys of ``applications.fake_data.SCALES`` (a test checks it);
#: repeated here because that module needs faker, which may be missing.
SCALE_NAMES = ("small", "medium", "large")
COUNTS = ("employers", "postings", "candidates", "applications")


class Command(BaseCommand):
    help = "Insert lots of fake (Faker) employers, postings, candidates, applications."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--scale",
            choices=SCALE_NAMES,
            default="large",
            help="Size preset (default: large). Explicit counts win over it.",
        )
        for name in COUNTS:
            parser.add_argument(f"--{name}", type=int, default=None)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument(
            "--wipe-fake",
            action="store_true",
            help="Delete every fake_ user (with cascades) before seeding.",
        )
        parser.add_argument(
            "--shared-resume",
            action=argparse.BooleanOptionalAction,
            default=None,
            help="One PDF for all applications (default: on for big runs).",
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

        counts = dict(fake_data.SCALES[options["scale"]])
        for name in COUNTS:
            if options[name] is not None:
                if options[name] < 0:
                    raise CommandError(f"--{name} must be 0 or more.")
                counts[name] = options[name]

        started = time.perf_counter()
        if options["wipe_fake"]:
            deleted = fake_data.wipe_fake_users()
            self.stdout.write(f"Deleted {deleted} fake users (with their data).")

        seed = options["seed"]
        gen = fake_data.FakeDataGenerator(
            seed, prefix=f"{fake_data.FAKE_PREFIX}s{seed}_"
        )
        sizes = ", ".join(f"{count} {name}" for name, count in counts.items())
        self.stdout.write(f"Seeding fake data (seed {seed}, {sizes})...")
        result = fake_data.seed_database(
            gen,
            **counts,
            password=os.environ.get("FAKE_DATA_PASSWORD", ""),
            shared_resume=options["shared_resume"],
            batch_size=options["batch_size"],
            log=self.stdout.write,
        )
        created = ", ".join(f"{count} {name}" for name, count in result.created.items())
        elapsed = time.perf_counter() - started
        self.stdout.write(
            self.style.SUCCESS(f"Fake data ready in {elapsed:.2f}s: {created}.")
        )
