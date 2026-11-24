"""Shared fixtures for the tests that run on a whole ``seed_fake_data`` site."""

from dataclasses import dataclass
from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import override_settings

from applications.fake_data import wipe_fake_users
from candidates.models import Candidate
from employers.models import Employer, Skill

FAKE_SITE_SEED = 2024


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "fakedata: runs on a seed_fake_data site built once per module "
        "(medium preset, about 2 s); deselect with -m 'not fakedata'.",
    )


@dataclass
class FakeSite:
    seed: int
    prefix: str
    #: The busiest accounts: many applications, saved postings and alerts.
    candidate: Candidate
    employer: Employer


def build_fake_site(django_db_blocker, scale: str, seed: int = FAKE_SITE_SEED):
    """Seed a committed fake site; yields a :class:`FakeSite`, then deletes it.

    The rows are committed (each test still runs in its own transaction on top),
    so everything is removed again after the module.
    """
    with django_db_blocker.unblock():
        assert not User.objects.exists(), "the fake site needs an empty database"
        with override_settings(DEBUG=True):
            call_command(
                "seed_fake_data",
                scale=scale,
                seed=seed,
                shared_resume=True,
                stdout=StringIO(),
            )
        prefix = f"fake_s{seed}_"
        try:
            yield FakeSite(
                seed=seed,
                prefix=prefix,
                candidate=Candidate.objects.select_related("user").get(
                    user__username=f"{prefix}cand00000"
                ),
                employer=Employer.objects.select_related("user").get(
                    user__username=f"{prefix}emp00000"
                ),
            )
        finally:
            wipe_fake_users()
            Skill.objects.all().delete()


@pytest.fixture(scope="module")
def fake_site(request, django_db_blocker):
    """A medium ``seed_fake_data`` site shared by the tests of one module."""
    request.getfixturevalue("django_db_setup")
    yield from build_fake_site(django_db_blocker, "medium")


@pytest.fixture(scope="module")
def small_fake_site(request, django_db_blocker):
    """A small ``seed_fake_data`` site shared by the tests of one module."""
    request.getfixturevalue("django_db_setup")
    yield from build_fake_site(django_db_blocker, "small")
