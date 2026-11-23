"""Record what candidates search for, and summarize it (``manage.py top_searches``).

Why: the searches say which jobs people want. The most searched words, cities and
skills, and the searches that found nothing, show what the site is missing.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

import structlog
from django.db import DatabaseError, transaction
from django.db.models import Count, QuerySet
from django.utils import timezone

from employers.models import Skill

from .form import JobFilterForm
from .models import JobSearch

logger = structlog.get_logger(__name__)

#: Filters that make a request "a search" (sorting alone or paging is not).
SEARCH_FIELDS = (
    "q",
    "location",
    "work_mode",
    "employment_type",
    "seniority",
    "min_salary",
    "skills",
    "remote_only",
)


def normalize(text: str) -> str:
    """``"  Python   Developer "`` → ``"python developer"``, so equal words group."""
    return " ".join(text.split()).casefold()


def is_search(form: JobFilterForm) -> bool:
    """A valid form with at least one filter set."""
    return form.is_valid() and any(form.cleaned_data.get(f) for f in SEARCH_FIELDS)


def record_search(form: JobFilterForm, results: int, language: str = "") -> None:
    """Save one ``JobSearch`` row for a valid, filtered job-list form.

    One INSERT, plus one for the skill links when skills were chosen (both in a
    transaction then). Never fails the page: a database error is logged and
    swallowed; the atomic block keeps an outer transaction usable.
    """
    if not is_search(form):
        return
    data = form.cleaned_data
    try:
        with transaction.atomic():
            search = JobSearch.objects.create(
                query=normalize(data["q"])[: JobSearch.QUERY_MAX_LENGTH],
                location=normalize(data["location"])[:80],
                work_mode=data["work_mode"],
                employment_type=data["employment_type"],
                seniority=data["seniority"],
                min_salary=data["min_salary"],
                remote_only=data["remote_only"],
                language=language[:7],
                results=results,
            )
            if data["skills"]:
                # The search is new, so no link exists yet: skip what .set() reads.
                link = JobSearch.skills.through
                link.objects.bulk_create(
                    link(jobsearch_id=search.pk, skill_id=skill.pk)
                    for skill in data["skills"]
                )
    except DatabaseError:
        logger.warning("job_search_not_recorded", exc_info=True)


@dataclass
class SearchStats:
    since: datetime
    searches: int
    top_queries: list[dict]
    no_result_queries: list[dict]
    top_locations: list[dict]
    top_skills: list[dict]


def _top(rows: QuerySet, field: str, limit: int) -> list[dict]:
    return list(
        rows.exclude(**{field: ""})
        .values(field)
        .annotate(searches=Count("id"))
        .order_by("-searches", field)[:limit]
    )


def search_stats(days: int = 30, limit: int = 20) -> SearchStats:
    """The most searched words, cities and skills of the last ``days`` days."""
    since = timezone.now() - timedelta(days=days)
    rows = JobSearch.objects.filter(created_at__gte=since)
    top_skills = list(
        Skill.objects.filter(searches__created_at__gte=since)
        .annotate(searches_count=Count("searches"))
        .order_by("-searches_count", "name")
        .values("name", "searches_count")[:limit]
    )
    return SearchStats(
        since=since,
        searches=rows.count(),
        top_queries=_top(rows, "query", limit),
        no_result_queries=_top(rows.filter(results=0), "query", limit),
        top_locations=_top(rows, "location", limit),
        top_skills=[
            {"name": s["name"], "searches": s["searches_count"]} for s in top_skills
        ],
    )


def purge_old_searches(days: int) -> int:
    """Delete searches older than ``days`` days; returns how many were deleted."""
    cutoff = timezone.now() - timedelta(days=days)
    _total, per_model = JobSearch.objects.filter(created_at__lt=cutoff).delete()
    return per_model.get(JobSearch._meta.label, 0)  # without the skill links
