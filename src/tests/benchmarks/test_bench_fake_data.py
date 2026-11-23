"""Benchmarks on Faker data sets of several sizes (``applications.fake_data``).

Data sets are bulk inserted with a fixed seed, so runs compare. In the normal
suite (``--benchmark-disable``) each benchmark runs once as a smoke test. Time
them with::

    uv run pytest src/tests/benchmarks --benchmark-enable --benchmark-only
"""

from io import StringIO

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse

from applications.fake_data import FakeDataGenerator, seed_database
from candidates.matching import candidate_skill_ids, match_score
from candidates.models import Candidate
from employers.models import Employer, JobPosting

SEED = 99
SIZES = [50, 500]


def build(size: str | int, **counts) -> tuple[Candidate, Employer]:
    """Seed a data set; return its busiest candidate and employer."""
    prefix = f"fake_b{size}_"
    seed_database(FakeDataGenerator(SEED, prefix=prefix), shared_resume=True, **counts)
    return (
        Candidate.objects.select_related("user").get(
            user__username=f"{prefix}cand00000"
        ),
        Employer.objects.select_related("user").get(user__username=f"{prefix}emp00000"),
    )


def _get_ok(client, url: str, params=None):
    response = client.get(url, params)
    assert response.status_code == 200
    return response


@pytest.fixture(params=SIZES, ids=lambda n: f"{n}-postings")
def sized(request, db):
    size = request.param
    return build(
        size, employers=10, postings=size, candidates=50, applications=size * 2
    )


@pytest.fixture
def busy(db):
    """Few postings, many applicants: the employer job page gets hundreds."""
    return build("busy", employers=3, postings=30, candidates=800, applications=2400)


# ------------------------------------------------------------ jobs (by size)
@pytest.mark.benchmark(group="jobs-list")
def test_bench_jobs_list(benchmark, client, sized):
    candidate, _employer = sized
    client.force_login(candidate.user)
    benchmark(_get_ok, client, reverse("candidate_jobs"))


@pytest.mark.benchmark(group="jobs-search")
def test_bench_jobs_search(benchmark, client, sized):
    candidate, _employer = sized
    client.force_login(candidate.user)
    skill = JobPosting.objects.open().filter(skills__isnull=False)[0].skills.first()
    assert skill is not None
    params = {"q": "developer", "skills": skill.pk, "sort": "salary", "page": 2}
    benchmark(_get_ok, client, reverse("candidate_jobs"), params)


@pytest.mark.benchmark(group="jobs-detail")
def test_bench_job_detail(benchmark, client, sized):
    candidate, _employer = sized
    client.force_login(candidate.user)
    posting = candidate.applications.first().posting
    benchmark(_get_ok, client, reverse("candidate_job", args=[posting.pk]))


# ---------------------------------------------------------------- dashboards
@pytest.mark.benchmark(group="dashboards")
def test_bench_candidate_dashboard_busy(benchmark, client, busy):
    candidate, _employer = busy
    client.force_login(candidate.user)
    benchmark(_get_ok, client, reverse("candidate_dashboard"))


@pytest.mark.benchmark(group="dashboards")
def test_bench_employer_dashboard_busy(benchmark, client, busy):
    _candidate, employer = busy
    client.force_login(employer.user)
    benchmark(_get_ok, client, reverse("employer_dashboard"))


@pytest.mark.benchmark(group="dashboards")
def test_bench_employer_job_many_applications(benchmark, client, busy):
    _candidate, employer = busy
    posting = max(employer.postings.all(), key=lambda p: p.applications.count())
    assert posting.applications.count() >= 200
    client.force_login(employer.user)
    benchmark(_get_ok, client, reverse("employer_job", args=[posting.pk]))


# ------------------------------------------------------------------ matching
@pytest.mark.benchmark(group="matching")
def test_bench_match_score_1000_postings(benchmark, db):
    candidate, _employer = build(
        "match", employers=10, postings=1000, candidates=1, applications=0
    )
    postings = list(JobPosting.objects.prefetch_related("skills"))
    skill_ids = candidate_skill_ids(candidate)

    scores = benchmark(lambda: [match_score(candidate, p, skill_ids) for p in postings])

    assert len(scores) == 1000
    assert all(0 <= score <= 100 for score in scores)
    assert any(score > 0 for score in scores)


# ------------------------------------------------------------------- seeding
@pytest.mark.benchmark(group="seed")
def test_bench_seed_fake_data_small(benchmark, db):
    """The whole command on the small preset (wiped first, so every round works)."""

    def run():
        with override_settings(DEBUG=True):
            call_command(
                "seed_fake_data",
                scale="small",
                seed=1,
                wipe_fake=True,
                stdout=StringIO(),
            )

    benchmark.pedantic(run, rounds=3, iterations=1)
    assert JobPosting.objects.count() == 60
