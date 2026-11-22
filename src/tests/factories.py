"""Faker-based builders for tests and benchmarks (plain functions, no factory_boy).

They reuse :mod:`applications.fake_data` (the generator behind ``seed_fake_data``),
so tests and the dev data come from one implementation. Each builder saves one
object; keyword arguments override the generated field values.

Call :func:`seed` first for deterministic data::

    factories.seed(1234)
    employer = factories.make_employer()
    posting = factories.make_posting(employer, title="Backend developer")
"""

import itertools
import random

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.db.models import Model
from faker import Faker

from applications.fake_data import (
    LOCALES,
    MINIMAL_PDF,
    SKILLS,
    FakeDataGenerator,
    clip,
    ensure_skills,
)
from applications.models import Application, ApplicationEvent
from candidates.models import Candidate, JobAlert, SavedPosting
from employers.models import Employer, JobPosting, Skill

#: One generator (and Faker, with every site locale) for the whole test session.
generator = FakeDataGenerator(0, prefix="fake_t_")
fake: Faker = generator.faker
_counter = itertools.count()

__all__ = [
    "LOCALES",
    "fake",
    "job_title",
    "make_alert",
    "make_application",
    "make_candidate",
    "make_employer",
    "make_posting",
    "make_saved",
    "make_skill_pool",
    "seed",
]


def seed(n: int = 0) -> None:
    """Make every following builder call deterministic."""
    global _counter  # noqa: PLW0603 - usernames restart with the seed
    Faker.seed(n)
    random.seed(n)
    generator.reseed(n)
    _counter = itertools.count()


def _username(kind: str, username: str | None) -> str:
    return username or generator.username(kind, next(_counter))


def _apply[M: Model](instance: M, overrides: dict) -> M:
    for name, value in overrides.items():
        setattr(instance, name, value)
    return instance


def _skills(names, skills) -> list[Skill]:
    if skills is not None:
        return list(skills)
    return list(ensure_skills(names).values())


def job_title() -> str:
    return generator.job_title()


def make_skill_pool(names=SKILLS) -> list[Skill]:
    """The skills ``names`` (created when missing), ordered by name."""
    return sorted(ensure_skills(names).values(), key=lambda skill: skill.name)


def _save_user(user: User, username: str) -> User:
    user.username = username
    user.email = f"{username.replace('_', '.')}@example.com"
    user.save()
    return user


def make_employer(*, username: str | None = None, **overrides) -> Employer:
    employer = generator.employer(0)
    username = _username("emp", username)
    employer.user = _save_user(employer.user, username)
    employer.contact_email = f"hr.{employer.user.email}"
    _apply(employer, overrides)
    employer.save()
    return employer


def make_posting(employer: Employer, *, skills=None, **overrides) -> JobPosting:
    """A posting with 1-4 skills (or exactly ``skills``, which may be empty)."""
    item = generator.posting(employer)
    posting = clip(_apply(item.posting, overrides))
    posting.save()
    posting.skills.set(_skills(item.skills, skills))
    return posting


def make_candidate(
    *, username: str | None = None, skills=None, **overrides
) -> Candidate:
    candidate, names = generator.candidate(0)
    username = _username("cand", username)
    candidate.user = _save_user(candidate.user, username)
    candidate.email = candidate.user.email
    _apply(candidate, overrides)
    candidate.save()
    candidate.skills.set(_skills(names, skills))
    return candidate


def make_application(
    candidate: Candidate,
    posting: JobPosting,
    *,
    status: str | None = None,
    events: bool = True,
    **overrides,
) -> Application:
    """An application with a tiny PDF resume and (``events``) its status history."""
    item = generator.application(candidate, posting, status)
    application = _apply(item.application, overrides)
    application.resume = ContentFile(MINIMAL_PDF, name="resume.pdf")
    application.save()
    if events and item.events:
        ApplicationEvent.objects.bulk_create(
            ApplicationEvent(
                application=application,
                from_status=from_status,
                to_status=to_status,
                actor=actor,
            )
            for from_status, to_status, actor, _time in item.events
        )
    return application


def make_saved(candidate: Candidate, posting: JobPosting) -> SavedPosting:
    return SavedPosting.objects.create(candidate=candidate, posting=posting)


def make_alert(candidate: Candidate, *, skills=None, **overrides) -> JobAlert:
    alert, names = generator.alert(candidate, next(_counter))
    _apply(alert, overrides)
    alert.save()
    alert.skills.set(_skills(names, skills))
    return alert
