"""Benchmarks of hot paths: job matching and the busiest pages.

In the normal suite (``--benchmark-disable``) each benchmark runs once, untimed, so
it doubles as a smoke test. Time them with::

    uv run pytest src/tests/benchmarks --benchmark-enable --benchmark-only
"""

import pytest
from django.urls import reverse

from candidates.matching import candidate_skill_ids, match_score
from employers.models import JobPosting
from tests.perf.scenario import Scenario

POSTINGS = 50


@pytest.fixture
def scenario(make_employer, make_candidate, make_posting, make_application):
    scenario = Scenario(make_employer, make_candidate, make_posting, make_application)
    return scenario.grow(POSTINGS)


@pytest.mark.benchmark(group="matching")
def test_bench_match_score_many_postings(benchmark, scenario):
    """Score every posting for one candidate, as the jobs page does per row."""
    candidate = scenario.candidate
    postings = list(JobPosting.objects.prefetch_related("skills"))
    skill_ids = candidate_skill_ids(candidate)

    scores = benchmark(lambda: [match_score(candidate, p, skill_ids) for p in postings])

    assert len(scores) == POSTINGS
    assert all(0 <= score <= 100 for score in scores)


@pytest.mark.benchmark(group="matching")
def test_bench_candidate_skill_ids(benchmark, scenario):
    skill_ids = benchmark(candidate_skill_ids, scenario.candidate)
    assert skill_ids == {skill.pk for skill in scenario.skills[:2]}


def _get_ok(client, url: str):
    response = client.get(url)
    assert response.status_code == 200
    return response


@pytest.mark.benchmark(group="views")
def test_bench_candidate_jobs_list(benchmark, client, scenario):
    client.force_login(scenario.candidate.user)
    response = benchmark(_get_ok, client, reverse("candidate_jobs"))
    assert b"Job 49" in response.content


@pytest.mark.benchmark(group="views")
def test_bench_candidate_jobs_search(benchmark, client, scenario):
    client.force_login(scenario.candidate.user)
    skill = scenario.skills[1].pk
    url = f"{reverse('candidate_jobs')}?q=Job&skills={skill}&sort=salary"
    benchmark(_get_ok, client, url)


@pytest.mark.benchmark(group="views")
def test_bench_employer_dashboard(benchmark, client, scenario):
    client.force_login(scenario.employer.user)
    benchmark(_get_ok, client, reverse("employer_dashboard"))


@pytest.mark.benchmark(group="views")
def test_bench_employer_job_detail(benchmark, client, scenario):
    client.force_login(scenario.employer.user)
    benchmark(_get_ok, client, reverse("employer_job", args=[scenario.postings[0].pk]))
