"""Copy data from the pre-rename tables into the renamed apps (idempotent).

Before the rename the project had the apps ``offer`` (Offer, Tag, Job) and ``worker``
(Worker, JobRequest). They are now ``employers`` (Employer, Skill, JobPosting),
``candidates`` (Candidate) and ``applications`` (Application). ``migrate`` creates the
new tables; this command then copies every row from the old tables into them, keeping
primary keys (so uploaded resumes, which are named after the posting id, still match).

* It runs in ``make dev`` / ``make deploy`` right after ``migrate`` and does
  nothing on a fresh database (no old tables) or when the new tables already hold data.
* The old tables are left untouched as a backup; drop them yourself when satisfied:
  ``offer_offer, offer_tag, offer_job, offer_job_tags, worker_worker,
  worker_jobrequest``.
"""

from datetime import UTC, date, datetime
from typing import Any

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.utils.dateparse import parse_date, parse_datetime

from applications.models import Application
from candidates.models import Candidate
from employers.models import Employer, JobPosting, Skill

OLD_TABLES = (
    "offer_offer",
    "offer_tag",
    "offer_job",
    "offer_job_tags",
    "worker_worker",
    "worker_jobrequest",
)


def fetch_rows(table: str) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        quoted = connection.ops.quote_name(table)  # a fixed name from OLD_TABLES
        cursor.execute(f"SELECT * FROM {quoted}")  # noqa: S608  # nosec B608
        names = [column[0] for column in cursor.description]
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def to_datetime(value: Any) -> datetime | None:
    if value is None or (isinstance(value, datetime) and value.tzinfo):
        return value
    if isinstance(value, str):
        value = parse_datetime(value)
    if value is not None and value.tzinfo is None:
        value = value.replace(tzinfo=UTC)  # the database stores UTC (USE_TZ)
    return value


def to_date(value: Any) -> date | None:
    if isinstance(value, str):
        return parse_date(value)
    return value


def keep_timestamps(model, rows: list[dict[str, Any]], created: str, updated: str):
    """``auto_now(_add)`` overwrites timestamps on insert, so put the old ones back."""
    for row in rows:
        model.objects.filter(pk=row["id"]).update(
            **{created: to_datetime(row[created]), updated: to_datetime(row[updated])}
        )


class Command(BaseCommand):
    help = "Copy data from the old offer_*/worker_* tables into the renamed apps."

    def handle(self, *args, **options):
        existing = set(connection.introspection.table_names())
        if not existing.issuperset(OLD_TABLES):
            self.stdout.write("No legacy tables found; nothing to import.")
            return

        with transaction.atomic():
            counts = {
                "employers": self.import_employers(),
                "skills": self.import_skills(),
                "postings": self.import_postings(),
                "candidates": self.import_candidates(),
                "applications": self.import_applications(),
            }

        summary = ", ".join(f"{name}: {count}" for name, count in counts.items())
        self.stdout.write(self.style.SUCCESS(f"Imported legacy data ({summary})."))

    def import_employers(self) -> int:
        if Employer.objects.exists():
            return 0
        rows = fetch_rows("offer_offer")
        Employer.objects.bulk_create(
            Employer(
                id=row["id"],
                user_id=row["user_id"],
                name=row["company_name"],
                contact_email=row["company_email"],
                description=row["detail"] or "",
            )
            for row in rows
        )
        keep_timestamps(Employer, rows, "created_at", "updated_at")
        return len(rows)

    def import_skills(self) -> int:
        if Skill.objects.exists():
            return 0
        rows = fetch_rows("offer_tag")
        Skill.objects.bulk_create(Skill(id=row["id"], name=row["name"]) for row in rows)
        keep_timestamps(Skill, rows, "created_at", "updated_at")
        return len(rows)

    def import_postings(self) -> int:
        if JobPosting.objects.exists():
            return 0
        rows = fetch_rows("offer_job")
        JobPosting.objects.bulk_create(
            JobPosting(
                id=row["id"],
                title=row["job_name"],
                description=row["detail"],
                employer_id=row["offer_id"],
            )
            for row in rows
        )
        keep_timestamps(JobPosting, rows, "created_at", "updated_at")

        through = JobPosting.skills.through
        through.objects.bulk_create(
            through(jobposting_id=row["job_id"], skill_id=row["tag_id"])
            for row in fetch_rows("offer_job_tags")
        )
        return len(rows)

    def import_candidates(self) -> int:
        if Candidate.objects.exists():
            return 0
        rows = fetch_rows("worker_worker")
        Candidate.objects.bulk_create(
            Candidate(
                id=row["id"],
                user_id=row["user_id"],
                first_name=row["first_name"],
                last_name=row["last_name"],
                email=row["email"],
                phone_number=row["phone_number"] or "",
                address=row["address"] or "",
                date_of_birth=to_date(row["date_of_birth"]),
            )
            for row in rows
        )
        keep_timestamps(Candidate, rows, "created_at", "updated_at")
        return len(rows)

    def import_applications(self) -> int:
        if Application.objects.exists():
            return 0
        rows = fetch_rows("worker_jobrequest")
        Application.objects.bulk_create(
            Application(
                id=row["id"],
                candidate_id=row["worker_id"],
                posting_id=row["job_id"],
                resume=row["resume"],
                cover_letter=row["cover_letter"] or "",
                status=row["status"],
                ai_summary=row["ai_summary"] or "",
            )
            for row in rows
        )
        keep_timestamps(Application, rows, "applied_at", "updated_at")
        return len(rows)
