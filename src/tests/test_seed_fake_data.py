"""The ``seed_fake_data`` command and the Faker generator behind it."""

import sys
from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.test import override_settings

from applications.fake_data import FakeDataGenerator
from applications.models import Application, ApplicationEvent
from candidates.models import Candidate, JobAlert, JobSearch, SavedPosting
from employers.models import Employer, JobPosting

SMALL = {"employers": 3, "postings": 8, "candidates": 6, "applications": 12}


@pytest.fixture(autouse=True)
def debug_on(settings):
    # pytest-django turns DEBUG off; the command only runs with it on.
    settings.DEBUG = True


def seed(**options) -> str:
    out = StringIO()
    call_command("seed_fake_data", **{**SMALL, "seed": 5, **options}, stdout=out)
    return out.getvalue()


def titles() -> list[str]:
    return sorted(JobPosting.objects.values_list("title", flat=True))


@pytest.mark.django_db
def test_creates_the_requested_counts():
    output = seed()

    assert Employer.objects.count() == SMALL["employers"]
    assert JobPosting.objects.count() == SMALL["postings"]
    assert Candidate.objects.count() == SMALL["candidates"]
    assert Application.objects.count() == SMALL["applications"]
    assert not User.objects.exclude(username__startswith="fake_s5_").exists()
    # Every employer has at least one posting; every posting 1-4 skills.
    assert not Employer.objects.filter(postings=None).exists()
    for posting in JobPosting.objects.prefetch_related("skills"):
        assert 1 <= len(posting.skills.all()) <= 4
    # Non-pending applications have a status history ending at their status.
    for app in Application.objects.exclude(status="pending").prefetch_related("events"):
        assert list(app.events.all())[-1].to_status == app.status
    assert "Fake data ready" in output
    assert "12 applications" in output


@pytest.mark.django_db
def test_same_seed_gives_same_data_and_reruns_create_nothing():
    seed()
    first = titles()
    counts = (Application.objects.count(), SavedPosting.objects.count())

    seed()  # same seed: every row already exists
    assert titles() == first
    assert (Application.objects.count(), SavedPosting.objects.count()) == counts

    seed(wipe_fake=True)  # wiped and rebuilt from the same seed
    assert titles() == first


def test_generator_is_deterministic_without_a_database():
    def build(seed_value):
        gen = FakeDataGenerator(seed_value)
        employer = gen.employer(0)
        return [gen.posting(employer).posting.title for _ in range(10)]

    assert build(1) == build(1)
    assert build(1) != build(2)


@pytest.mark.django_db
def test_other_seed_adds_a_separate_set():
    seed()
    seed(seed=6)
    assert Employer.objects.count() == 2 * SMALL["employers"]
    assert User.objects.filter(username__startswith="fake_s6_").exists()


@pytest.mark.django_db
def test_refuses_without_debug():
    with override_settings(DEBUG=False), pytest.raises(CommandError, match="DEBUG"):
        seed()
    assert not User.objects.exists()


@pytest.mark.django_db
def test_clear_error_without_faker(monkeypatch):
    # A None entry in sys.modules makes the import fail, as when faker is missing.
    monkeypatch.setitem(sys.modules, "faker", None)
    with pytest.raises(CommandError, match="faker"):
        seed()


@pytest.mark.django_db
def test_wipe_fake_removes_only_fake_users(make_employer, make_candidate, make_posting):
    real_employer = make_employer("acme")
    make_posting(real_employer)
    real_candidate = make_candidate("sara")
    seed()
    assert User.objects.filter(username__startswith="fake_").exists()

    seed(wipe_fake=True, employers=0, postings=0, candidates=0, applications=0)

    assert not User.objects.filter(username__startswith="fake_").exists()
    assert set(User.objects.values_list("username", flat=True)) == {"acme", "sara"}
    assert JobPosting.objects.get().employer == real_employer
    assert Candidate.objects.get() == real_candidate
    assert not Application.objects.exists()
    assert not ApplicationEvent.objects.exists()


@pytest.mark.django_db
def test_passwords_unusable_except_first_accounts(monkeypatch):
    monkeypatch.setenv("FAKE_DATA_PASSWORD", "load-test-pw")
    seed()
    users = {u.username: u for u in User.objects.all()}

    assert users["fake_s5_emp00000"].check_password("load-test-pw")
    assert users["fake_s5_cand00000"].check_password("load-test-pw")
    others = [u for name, u in users.items() if not name.endswith("00000")]
    assert others
    assert not any(u.has_usable_password() for u in others)


@pytest.mark.django_db
def test_passwords_unusable_without_env(monkeypatch):
    monkeypatch.delenv("FAKE_DATA_PASSWORD", raising=False)
    seed()
    assert not any(u.has_usable_password() for u in User.objects.all())


@pytest.mark.django_db
def test_generated_rows_pass_model_validation():
    seed(employers=5, postings=30, candidates=20, applications=60)

    samples = [
        *User.objects.all()[:10],
        *Employer.objects.all(),
        *JobPosting.objects.all()[:30],
        *Candidate.objects.all()[:20],
        *Application.objects.all()[:30],
        *ApplicationEvent.objects.all()[:20],
        *SavedPosting.objects.all()[:10],
        *JobAlert.objects.all()[:10],
    ]
    for obj in samples:
        obj.full_clean()
    for app in Application.objects.all()[:5]:
        with app.resume.open("rb") as resume:
            assert resume.read().startswith(b"%PDF")


@pytest.mark.django_db
def test_fills_the_search_log_once():
    JobSearch.objects.all().delete()  # a shared fixture may have seeded some
    seed(searches=40)

    assert JobSearch.objects.count() == 40
    assert JobSearch.objects.filter(results=0).exists()  # words nobody matches
    assert JobSearch.objects.exclude(query="").exists()
    assert JobSearch.skills.through.objects.exists()
    first, last = (
        JobSearch.objects.earliest("created_at"),
        JobSearch.objects.latest("created_at"),
    )
    assert (last.created_at - first.created_at).days >= 1  # spread over time

    seed(searches=40)  # same seed again: the log is not empty, nothing is added
    assert JobSearch.objects.count() == 40


@pytest.mark.django_db
def test_searches_default_to_half_the_applications():
    JobSearch.objects.all().delete()
    seed()

    assert JobSearch.objects.count() == SMALL["applications"] // 2
