"""Invariants of the data ``seed_fake_data`` generates (small preset, built once)."""

from collections import Counter
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.db.models import Count
from django.db.models.functions import Lower
from django.utils import timezone

from applications.fake_data import (
    DORMANT_EVERY,
    SCALES,
    STATUS_PATHS,
    FakeDataGenerator,
)
from applications.management.commands.seed_fake_data import SCALE_NAMES
from applications.models import Application, ApplicationEvent
from candidates.models import Candidate, JobAlert, SavedPosting
from employers.models import Employer, JobPosting

pytestmark = [pytest.mark.fakedata, pytest.mark.django_db]


def test_scale_names_match_the_presets():
    assert tuple(SCALES) == SCALE_NAMES
    sizes = [SCALES[name]["applications"] for name in SCALE_NAMES]
    assert sizes == sorted(sizes)


def test_counts_match_the_small_preset(small_fake_site):
    preset = SCALES["small"]
    assert Employer.objects.count() == preset["employers"]
    assert JobPosting.objects.count() == preset["postings"]
    assert Candidate.objects.count() == preset["candidates"]
    assert Application.objects.count() == preset["applications"]


@pytest.mark.parametrize(
    ("model", "field"),
    [
        (User, "email"),
        (Candidate, "email"),
        (Employer, "contact_email"),
        (User, "username"),
    ],
)
def test_emails_and_usernames_are_unique(small_fake_site, model, field):
    values = list(model.objects.annotate(v=Lower(field)).values_list("v", flat=True))
    assert len(values) == len(set(values))


@pytest.mark.parametrize(
    "model",
    [
        User,
        Employer,
        JobPosting,
        Candidate,
        Application,
        ApplicationEvent,
        SavedPosting,
        JobAlert,
    ],
)
def test_samples_pass_full_clean(small_fake_site, model):
    """Choices, max_length, validators (phone, birth date, URLs) all hold."""
    samples = list(model.objects.order_by("?")[:40])
    assert samples
    for obj in samples:
        obj.full_clean()


def test_profiles_are_filled_in(small_fake_site):
    candidates = list(Candidate.objects.all())
    for name in ("headline", "city", "phone_number", "date_of_birth"):
        filled = sum(1 for c in candidates if getattr(c, name) not in ("", None))
        assert filled >= 0.9 * len(candidates), name
    assert all(c.skills.exists() for c in candidates[:20])
    for employer in Employer.objects.all():
        assert employer.description and employer.industry and employer.website


def test_status_history_leads_to_the_final_status(small_fake_site):
    applications = Application.objects.prefetch_related("events")
    paths = {status: set(options) for status, options in STATUS_PATHS.items()}
    for app in applications:
        events = list(app.events.all())
        steps = tuple(event.to_status for event in events)
        assert steps in paths[app.status], (app.status, steps)
        previous = "pending"
        moment = app.applied_at
        for event in events:
            assert event.from_status == previous
            assert event.created_at >= moment
            previous, moment = event.to_status, event.created_at
        if events:
            withdrawn = events[-1].to_status == "withdrawn"
            actor = app.candidate.user if withdrawn else app.posting.employer.user
            assert events[-1].actor == actor


def test_dates_are_consistent(small_fake_site):
    now = timezone.now()
    today = timezone.localdate()
    for posting in JobPosting.objects.all():
        assert posting.created_at <= now
        if posting.deadline:
            assert today - timedelta(days=30) <= posting.deadline
            assert posting.deadline <= today + timedelta(days=60)
        if posting.salary_min is not None:
            assert posting.salary_max is not None
            assert posting.salary_min <= posting.salary_max
    for app in Application.objects.select_related("posting"):
        assert app.posting.created_at <= app.applied_at <= now
    for saved in SavedPosting.objects.select_related("posting"):
        assert saved.posting.created_at <= saved.created_at <= now


def test_skew_popular_postings_dormant_employers_recent_activity(small_fake_site):
    counts = sorted(
        JobPosting.objects.annotate(n=Count("applications")).values_list(
            "n", flat=True
        ),
        reverse=True,
    )
    mean = sum(counts) / len(counts)
    assert counts[0] >= 3 * mean  # a few postings get most of the applications

    dormant = [
        e
        for e in Employer.objects.order_by("user__username")
        if int(e.user.username[-5:]) % DORMANT_EVERY == DORMANT_EVERY - 1
    ]
    assert dormant
    for employer in dormant:
        assert not employer.postings.open().exists()
        assert not employer.postings.filter(is_active=True).exists()

    week = timezone.now() - timedelta(days=7)
    assert Application.objects.filter(applied_at__gte=week).exists()
    assert JobPosting.objects.filter(created_at__gte=week).exists()
    assert ApplicationEvent.objects.exclude(note="").exists()


def test_status_mix_covers_every_status(small_fake_site):
    statuses = Counter(Application.objects.values_list("status", flat=True))
    assert set(statuses) == set(Application.Status.values)


def test_first_accounts_are_the_busiest(small_fake_site):
    first = small_fake_site.candidate
    others = Candidate.objects.exclude(pk=first.pk).annotate(n=Count("applications"))
    assert first.applications.count() >= max(c.n for c in others) * 0.5
    assert first.saved_postings.count() >= 10
    assert first.job_alerts.count() == 3


def test_generator_titles_are_unique_per_employer():
    gen = FakeDataGenerator(3)
    employer = gen.employer(0)
    titles = [gen.posting(employer).posting.title for _ in range(300)]
    assert len(titles) == len(set(titles))
    assert all(len(title) <= 100 for title in titles)
