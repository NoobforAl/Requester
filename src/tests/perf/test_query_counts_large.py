"""The pinned query counts also hold at a much larger size (N=2 vs N=50).

One test grows a single scenario once and checks every key page, so the bigger
data set is built only once.
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .scenario import Scenario
from .test_query_counts import CANDIDATE_PAGES, EMPLOYER_PAGES, PINNED

SMALL, LARGE = 2, 50


def _count(client, url: str) -> int:
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url)
    assert response.status_code == 200, url
    return len(ctx)


def _measure(client, scenario: Scenario) -> dict[str, int]:
    counts = {}
    for user, pages in (
        (scenario.candidate.user, CANDIDATE_PAGES),
        (scenario.employer.user, EMPLOYER_PAGES),
    ):
        client.force_login(user)
        for name, url_for in pages.items():
            client.get(url_for(scenario))  # warm-up (content types, sessions...)
            counts[name] = _count(client, url_for(scenario))
    search = f"{reverse('candidate_jobs')}?q=Job&skills={scenario.skills[1].pk}"
    client.force_login(scenario.candidate.user)
    counts["candidate_jobs_search"] = _count(client, f"{search}&sort=salary")
    return counts


@pytest.mark.django_db
def test_query_counts_do_not_grow_up_to_50(client):
    scenario = Scenario().grow(SMALL)
    small = _measure(client, scenario)
    scenario.grow(LARGE)
    large = _measure(client, scenario)

    assert small == large
    assert large == {name: PINNED[name] for name in large}
