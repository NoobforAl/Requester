"""Caches for the candidate job list: search results and job cards.

Search results: which postings a search finds.

The search itself (``icontains`` over titles, descriptions and company names, a
COUNT for the pager) is the same for every candidate, so its *result* is cached
for ``JOB_SEARCH_CACHE_SECONDS``: the posting ids of the page and the total.

What stays fresh and per user:

* the rows are always re-read by id through the same filters, so an edited,
  closed or deleted posting is never shown out of date (it just drops out);
* the match score and the "saved" button are added by the view on every request.

What can be up to ``JOB_SEARCH_CACHE_SECONDS`` old: a brand-new posting may appear
in a search that late, and the total in the pager may be off by the postings
created or closed in that window.
"""

import functools
import hashlib
import json
from collections.abc import Iterable
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.core.paginator import Page, Paginator
from django.template.loader import get_template, render_to_string
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.translation import get_language

from employers.models import JobPosting, JobPostingQuerySet, Skill

KEY_PREFIX = "jobsearch:v1:"


def search_key(query: str, filters: dict[str, Any], sort: str, page: str) -> str:
    """Cache key of one result page. Today's date is part of it, because ``open()``
    hides postings past their deadline."""
    normalized = {
        name: sorted(s.pk if isinstance(s, Skill) else s for s in value)
        if name == "skills"
        else value
        for name, value in filters.items()
    }
    raw = json.dumps(
        [query.strip().casefold(), normalized, sort, page, str(timezone.localdate())],
        sort_keys=True,
        default=str,
    )
    return KEY_PREFIX + hashlib.sha256(raw.encode()).hexdigest()


def search_page(
    postings: JobPostingQuerySet, key: str, page: str | None, per_page: int
) -> Page:
    """``Paginator(postings, per_page).get_page(page)``, with the ids cached."""
    ttl = settings.JOB_SEARCH_CACHE_SECONDS
    if ttl <= 0:
        return Paginator(postings, per_page).get_page(page)

    hit = cache.get(key)
    if hit is not None:
        ids, total, number = hit
        rows = {p.pk: p for p in postings.filter(pk__in=ids)}
        # The pager only needs the total: a range stands in for the result list.
        pager: Paginator[Any] = Paginator(range(total), per_page)
        return Page([rows[pk] for pk in ids if pk in rows], number, pager)

    result = Paginator(postings, per_page).get_page(page)
    ids = [posting.pk for posting in result]
    cache.set(key, (ids, result.paginator.count, result.number), ttl)
    return result


# ------------------------------------------------------------------ job cards
#: The visitor-independent half of a job card (title, company, skills, summary).
CARD_TEMPLATE = "candidates/_posting_card_body.html"


def _template_hash() -> str:
    source = get_template(CARD_TEMPLATE).template.source  # type: ignore[attr-defined]
    return hashlib.sha256(source.encode()).hexdigest()[:12]


_cached_template_hash = functools.cache(_template_hash)


def _card_template_hash() -> str:
    """Changes with the card template, so a deploy never serves old card HTML.

    Read once per process, except with DEBUG on, where templates are edited while
    the server runs.
    """
    return _template_hash() if settings.DEBUG else _cached_template_hash()


def card_key(posting: JobPosting, language: str) -> str:
    """One card per posting, language and version of the data it shows.

    ``posting.updated_at`` moves on every edit, including skill changes and skill
    renames (``employers.signals``); the company name is ``employer.updated_at``.
    """
    return ":".join(
        (
            "jobcard",
            _card_template_hash(),
            str(posting.pk),
            str(posting.updated_at.timestamp()),
            str(posting.employer.updated_at.timestamp()),
            language,
        )
    )


def attach_card_bodies(postings: Iterable[JobPosting]) -> None:
    """Set ``posting.card_body`` (safe HTML) on each posting: one cache round trip,
    and the missing cards rendered and stored with a second one."""
    ttl = settings.JOB_CARD_CACHE_SECONDS
    if ttl <= 0:
        return  # the template renders the card itself
    language = get_language() or settings.LANGUAGE_CODE
    by_key = {card_key(posting, language): posting for posting in postings}
    found = cache.get_many(list(by_key))
    rendered = {}
    for key, posting in by_key.items():
        html = found.get(key)
        if html is None:
            html = rendered[key] = render_to_string(CARD_TEMPLATE, {"posting": posting})
        # Our own template's output (autoescaped when it was rendered).
        posting.card_body = mark_safe(html)  # noqa: S308  # nosec B308 B703
    if rendered:
        cache.set_many(rendered, ttl)
