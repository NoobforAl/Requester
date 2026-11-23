"""Query-count tests: the number of SQL queries per page must not grow with the data.

Each test renders a page with N=2 objects, grows the data to N=10 and renders it
again. Both counts must be equal (no N+1), and equal to the pinned number, so an
extra query (a missing ``select_related``/``prefetch_related``) fails the test.

When a view legitimately changes, update the number in ``PINNED``.
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .scenario import Scenario

SMALL, LARGE = 2, 10

# Queries per request, including session and user lookups by the auth middleware.
PINNED = {
    "home": 0,
    "candidate_dashboard": 7,
    "candidate_jobs": 9,
    "candidate_job": 9,
    "candidate_saved": 6,
    "candidate_applications": 5,
    "candidate_alerts": 6,
    "employer_dashboard": 10,
    "employer_jobs": 7,
    "employer_job": 8,
    # One more than the plain list: the form validates the chosen skill ids. Then
    # four to record the search (candidates.search_log): the search and its skill
    # links in one atomic block (a SAVEPOINT pair inside the test's transaction).
    "candidate_jobs_search": 14,
}


@pytest.fixture
def scenario(make_employer, make_candidate, make_posting, make_application):
    return Scenario(make_employer, make_candidate, make_posting, make_application)


def _count(client, url: str) -> int:
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url)
    assert response.status_code == 200, url
    return len(ctx)


def _assert_constant(client, scenario, url_for, name, django_assert_num_queries):
    scenario.grow(SMALL)
    client.get(url_for(scenario))  # warm-up: first-request caches (content types...)
    small = _count(client, url_for(scenario))

    scenario.grow(LARGE)
    large = _count(client, url_for(scenario))
    assert small == large, f"{name}: {small} queries at N={SMALL}, {large} at N={LARGE}"

    with django_assert_num_queries(PINNED[name]):
        response = client.get(url_for(scenario))
    assert response.status_code == 200


def test_home_anonymous(db, client, django_assert_num_queries):
    with django_assert_num_queries(PINNED["home"]):
        response = client.get(reverse("home"))
    assert response.status_code == 200


CANDIDATE_PAGES = {
    "candidate_dashboard": lambda s: reverse("candidate_dashboard"),
    "candidate_jobs": lambda s: reverse("candidate_jobs"),
    "candidate_job": lambda s: reverse("candidate_job", args=[s.postings[0].pk]),
    "candidate_saved": lambda s: reverse("candidate_saved"),
    "candidate_applications": lambda s: reverse("candidate_applications"),
    "candidate_alerts": lambda s: reverse("candidate_alerts"),
}

EMPLOYER_PAGES = {
    "employer_dashboard": lambda s: reverse("employer_dashboard"),
    "employer_jobs": lambda s: reverse("employer_jobs"),
    "employer_job": lambda s: reverse("employer_job", args=[s.postings[0].pk]),
}


@pytest.mark.parametrize("name", CANDIDATE_PAGES)
def test_candidate_page_query_count_is_constant(
    client, scenario, name, django_assert_num_queries
):
    client.force_login(scenario.candidate.user)
    _assert_constant(
        client, scenario, CANDIDATE_PAGES[name], name, django_assert_num_queries
    )


@pytest.mark.parametrize("name", EMPLOYER_PAGES)
def test_employer_page_query_count_is_constant(
    client, scenario, name, django_assert_num_queries
):
    client.force_login(scenario.employer.user)
    _assert_constant(
        client, scenario, EMPLOYER_PAGES[name], name, django_assert_num_queries
    )


def test_candidate_jobs_search_query_count_is_constant(
    client, scenario, django_assert_num_queries
):
    """The filtered list (text query and skill filter) stays constant too."""
    client.force_login(scenario.candidate.user)
    skill = scenario.skills[1].pk
    url = f"{reverse('candidate_jobs')}?q=Job&skills={skill}&sort=salary"
    _assert_constant(
        client,
        scenario,
        lambda s: url,
        "candidate_jobs_search",
        django_assert_num_queries,
    )
