"""Fake (Faker-based) data for development, load tests, tests and benchmarks.

One implementation, used in two ways:

* ``seed_fake_data`` (management command) calls :func:`seed_database`, which builds
  thousands of rows with ``bulk_create``;
* ``tests/factories.py`` wraps :class:`FakeDataGenerator` to create single objects.

The generator only builds *unsaved* model instances. All randomness comes from the
generator's own ``random.Random`` and its own Faker instance, so the same seed gives
the same data whatever the database already holds.

Faker is a dev dependency: import this module only where faker is installed (the
command checks that first and fails with a clear message).

The ``random`` module is fine here (S311): this is test data, not security.
"""
# ruff: noqa: S311

from __future__ import annotations

import contextlib
import itertools
import random
import time
from collections import defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import models, transaction
from django.utils import timezone
from django_elasticsearch_dsl.registries import registry
from faker import Faker

from applications.models import Application, ApplicationEvent, resume_upload_to
from candidates.models import Candidate, JobAlert, SavedPosting
from employers.models import Employer, JobPosting, Skill, WorkMode

#: Every fake account's username starts with this, so they can be wiped safely.
FAKE_PREFIX = "fake_"
BATCH_SIZE = 500

#: A tiny but valid PDF, the same bytes as the test suite and ``seed_demo_data`` use.
MINIMAL_PDF = b"%PDF-1.4\n1 0 obj\n<< >>\nendobj\ntrailer\n<< >>\n%%EOF\n"


@dataclass(frozen=True)
class LocaleInfo:
    language: str  # a code from settings.LANGUAGES
    currency: str
    country: str
    phone_prefix: str
    cities: tuple[str, ...]
    #: Salary range for ``salary_min`` in this currency: (low, high, step).
    salary: tuple[int, int, int]
    weight: int


#: Faker locales, one per site language.
LOCALES: dict[str, LocaleInfo] = {
    "fa_IR": LocaleInfo(
        "fa",
        "IRR",
        "Iran",
        "+98",
        ("Tehran", "Isfahan", "Shiraz", "Tabriz", "Mashhad", "Karaj"),
        (20_000_000, 120_000_000, 1_000_000),
        3,
    ),
    "en_US": LocaleInfo(
        "en",
        "USD",
        "United States",
        "+1",
        ("New York", "San Francisco", "Austin", "Seattle", "Boston", "Chicago"),
        (50_000, 180_000, 5_000),
        3,
    ),
    "de_DE": LocaleInfo(
        "de",
        "EUR",
        "Germany",
        "+49",
        ("Berlin", "Munich", "Hamburg", "Frankfurt", "Cologne"),
        (35_000, 110_000, 5_000),
        2,
    ),
    "ar_AA": LocaleInfo(
        "ar",
        "AED",
        "United Arab Emirates",
        "+971",
        ("Dubai", "Abu Dhabi", "Sharjah"),
        (8_000, 40_000, 1_000),
        1,
    ),
    "fr_FR": LocaleInfo(
        "fr",
        "EUR",
        "France",
        "+33",
        ("Paris", "Lyon", "Marseille", "Toulouse", "Lille"),
        (32_000, 95_000, 5_000),
        1,
    ),
    "ru_RU": LocaleInfo(
        "ru",
        "RUB",
        "Russia",
        "+7",
        ("Moscow", "Saint Petersburg", "Kazan", "Novosibirsk"),
        (80_000, 450_000, 10_000),
        1,
    ),
    "zh_CN": LocaleInfo(
        "zh-hans",
        "CNY",
        "China",
        "+86",
        ("Shanghai", "Beijing", "Shenzhen", "Hangzhou", "Chengdu"),
        (8_000, 60_000, 1_000),
        1,
    ),
}
LOCALE_BY_LANGUAGE = {info.language: code for code, info in LOCALES.items()}

#: Job roles and the skills they usually ask for.
ROLES: dict[str, tuple[str, ...]] = {
    "Backend Developer": ("Python", "Django", "SQL", "Docker", "Redis"),
    "Frontend Developer": ("JavaScript", "TypeScript", "React", "CSS"),
    "Full-stack Developer": ("JavaScript", "Python", "React", "SQL"),
    "Go Developer": ("Go", "Docker", "Kubernetes", "SQL"),
    "Java Developer": ("Java", "Spring", "SQL", "Docker"),
    "DevOps Engineer": ("Docker", "Kubernetes", "DevOps", "Linux", "Terraform"),
    "Site Reliability Engineer": ("Linux", "Kubernetes", "Prometheus", "Go"),
    "Cloud Architect": ("AWS", "Terraform", "Kubernetes", "DevOps"),
    "Database Administrator": ("SQL", "MariaDB", "PostgreSQL", "Linux"),
    "Data Scientist": ("Python", "Machine learning", "Data analysis", "SQL"),
    "Data Analyst": ("SQL", "Data analysis", "Excel", "Power BI"),
    "ML Engineer": ("Python", "Machine learning", "PyTorch", "Docker"),
    "Mobile Developer": ("Android", "iOS", "Kotlin", "Swift"),
    "Android Developer": ("Android", "Kotlin", "Java"),
    "iOS Developer": ("iOS", "Swift"),
    "QA Engineer": ("Test automation", "Python", "Selenium"),
    "Security Engineer": ("Cyber security", "Linux", "Networking"),
    "UX Designer": ("UX design", "Figma", "User research"),
    "Product Manager": ("Project management", "User research", "Agile"),
    "Project Manager": ("Project management", "Agile", "Communication"),
    "Technical Writer": ("Technical writing", "Communication"),
    "Support Engineer": ("Communication", "Linux", "Networking"),
    "Marketing Specialist": ("Marketing", "Communication", "SEO"),
    "Sales Manager": ("Sales", "Communication", "Negotiation"),
    "Accountant": ("Accounting", "Excel"),
    "HR Specialist": ("Recruiting", "Communication"),
}
SKILLS: tuple[str, ...] = tuple(
    sorted({skill for skills in ROLES.values() for skill in skills})
)

SENIORITY_PREFIX = {
    "intern": "Intern",
    "junior": "Junior",
    "mid": "",
    "senior": "Senior",
    "lead": "Lead",
    "": "",
}
SENIORITY_WEIGHTS = {"intern": 1, "junior": 3, "mid": 5, "senior": 4, "lead": 1, "": 1}
INDUSTRIES = (
    "Software",
    "Cloud",
    "Fintech",
    "E-commerce",
    "Logistics",
    "Healthcare",
    "Education",
    "Gaming",
    "Media",
    "Telecom",
    "Manufacturing",
    "Consulting",
)
#: Status mix of fake applications (weights).
STATUS_WEIGHTS = {
    Application.Status.PENDING: 35,
    Application.Status.IN_REVIEW: 20,
    Application.Status.SHORTLISTED: 12,
    Application.Status.ACCEPTED: 6,
    Application.Status.REJECTED: 20,
    Application.Status.WITHDRAWN: 7,
}
#: How an application reached each status, as a chain of statuses after "pending".
STATUS_PATHS: dict[str, tuple[tuple[str, ...], ...]] = {
    "pending": ((),),
    "in_review": (("in_review",),),
    "shortlisted": (("shortlisted",), ("in_review", "shortlisted")),
    "accepted": (("in_review", "accepted"), ("in_review", "shortlisted", "accepted")),
    "rejected": (("rejected",), ("in_review", "rejected")),
    "withdrawn": (("withdrawn",), ("in_review", "withdrawn")),
}


def clip[M: models.Model](instance: M) -> M:
    """Cut each string value to its field's ``max_length`` (Faker text can be long)."""
    for model_field in instance._meta.concrete_fields:
        max_length = getattr(model_field, "max_length", None)
        if not max_length:
            continue
        value = getattr(instance, model_field.attname)
        if isinstance(value, str) and len(value) > max_length:
            setattr(instance, model_field.attname, value[:max_length].rstrip())
    return instance


@dataclass
class FakePosting:
    posting: JobPosting
    skills: list[str]


@dataclass
class FakeApplication:
    application: Application
    #: (from_status, to_status, actor, time) for each status change, oldest first.
    #: Generated with the application, so random draws never depend on the database.
    events: list[tuple[str, str, User | None, datetime]] = field(default_factory=list)


class FakeDataGenerator:
    """Builds unsaved, realistic model instances from a seed.

    Usernames are ``<prefix>emp00001`` / ``<prefix>cand00001``; the prefix must start
    with :data:`FAKE_PREFIX`.
    """

    def __init__(self, seed: int | None = None, prefix: str = FAKE_PREFIX) -> None:
        if not prefix.startswith(FAKE_PREFIX):
            raise ValueError(f"The username prefix must start with {FAKE_PREFIX!r}.")
        self.prefix = prefix
        self.faker = Faker(list(LOCALES))
        self.rng = random.Random()
        self.reseed(seed)

    def reseed(self, seed: int | None) -> None:
        """Restart the random streams, so the same calls give the same data again."""
        self.faker.seed_instance(seed)
        self.rng.seed(seed)
        self.now = timezone.now()
        self._titles: defaultdict[str, set[str]] = defaultdict(set)

    # ------------------------------------------------------------- helpers
    def locale(self) -> str:
        codes = list(LOCALES)
        return self.rng.choices(codes, weights=[LOCALES[c].weight for c in codes])[0]

    def past(self, max_days: int, min_days: int = 0):
        """A random moment between ``min_days`` and ``max_days`` days ago."""
        seconds = self.rng.randint(min_days * 86_400, max_days * 86_400)
        return self.now - timedelta(seconds=seconds)

    def chance(self, probability: float) -> bool:
        """True with the given probability."""
        return self.rng.random() < probability

    def phone(self, locale: str) -> str:
        prefix = LOCALES[locale].phone_prefix
        digits = "".join(str(self.rng.randint(0, 9)) for _ in range(13 - len(prefix)))
        return f"{prefix}{digits}"

    def salary(self, locale: str) -> tuple[int, int]:
        low, high, step = LOCALES[locale].salary
        minimum = self.rng.randrange(low, high, step)
        maximum = minimum + step * self.rng.randint(
            1, max(1, (high - low) // step // 3)
        )
        return minimum, maximum

    def role(self) -> str:
        return self.rng.choice(list(ROLES))

    def job_title(self, locale: str | None = None, seniority: str = "mid") -> str:
        """A job title: mostly a tech role, sometimes a localised Faker job."""
        locale = locale or self.locale()
        if self.chance(0.2):
            return self.faker[locale].job()[:100]
        prefix = SENIORITY_PREFIX.get(seniority, "")
        return f"{prefix} {self.role()}".strip()

    def username(self, kind: str, index: int) -> str:
        return f"{self.prefix}{kind}{index:05d}"

    def user(self, username: str, first: str = "", last: str = "") -> User:
        user = User(
            username=username,
            email=f"{username.replace('_', '.')}@example.com",
            first_name=first,
            last_name=last,
            date_joined=self.past(365, 120),
        )
        user.set_unusable_password()
        return clip(user)

    # ------------------------------------------------------------- builders
    def employer(self, index: int) -> Employer:
        """An unsaved employer; its unsaved user is ``employer.user``."""
        locale = self.locale()
        info = LOCALES[locale]
        fake = self.faker[locale]
        username = self.username("emp", index)
        name = fake.company()
        industry = self.rng.choice(INDUSTRIES)
        created = self.past(365, 120)
        employer = Employer(
            user=self.user(username),
            name=name,
            contact_email=f"hr.{username.replace('_', '.')}@example.com",
            description=f"{fake.catch_phrase()}. {fake.paragraph(nb_sentences=3)}",
            website=f"https://{username.replace('_', '-')}.example.com",
            industry=industry,
            size=self.rng.choice(Employer.Size.values),
            city=self.rng.choice(info.cities),
            language=info.language,
            created_at=created,
            updated_at=created,
        )
        return clip(employer)

    def posting(self, employer: Employer, skill_names=None) -> FakePosting:
        """An unsaved posting of ``employer`` and the 1-4 skill names it asks for."""
        locale = LOCALE_BY_LANGUAGE.get(employer.language, "en_US")
        info = LOCALES[locale]
        fake = self.faker[locale]
        seniority = self.rng.choices(
            list(SENIORITY_WEIGHTS), weights=list(SENIORITY_WEIGHTS.values())
        )[0]
        role = self.role()
        title = self.job_title(locale, seniority)
        if title.endswith(tuple(ROLES)):
            role = next(r for r in ROLES if title.endswith(r))
        # A title is unique per employer: number the repeats.
        taken = self._titles[employer.user.username]
        base, number = title, 2
        while title in taken:
            title = f"{base[:94]} ({number})"
            number += 1
        taken.add(title)

        if skill_names is None:
            wanted = list(ROLES[role])
            count = self.rng.randint(1, min(4, len(wanted)))
            skill_names = self.rng.sample(wanted, count)
        salary_min, salary_max = (
            self.salary(locale) if self.chance(0.85) else (None, None)
        )
        kind = self.rng.choices(("none", "closed", "open"), weights=(1, 1, 8))[0]
        deadline = None
        if kind == "closed":
            deadline = timezone.localdate() - timedelta(days=self.rng.randint(1, 30))
        elif kind == "open":
            deadline = timezone.localdate() + timedelta(days=self.rng.randint(7, 60))
        created = self.past(120)
        requirements = "\n".join(f"- {name}" for name in skill_names)
        posting = JobPosting(
            title=title,
            description=(
                f"{fake.paragraph(nb_sentences=4)}\n\n"
                f"{fake.paragraph(nb_sentences=3)}\n\n{requirements}"
            ),
            employer=employer,
            location=employer.city or self.rng.choice(info.cities),
            country=info.country,
            work_mode=self.rng.choices(WorkMode.values, weights=[5, 3, 3])[0],
            employment_type=self.rng.choices(
                JobPosting.EmploymentType.values, weights=[10, 2, 2, 1, 1]
            )[0],
            seniority=seniority,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=info.currency,
            deadline=deadline,
            is_active=self.chance(0.9),
            created_at=created,
            updated_at=created,
        )
        return FakePosting(clip(posting), list(skill_names))

    def candidate(self, index: int) -> tuple[Candidate, list[str]]:
        """An unsaved candidate (user in ``candidate.user``) and its skill names."""
        locale = self.locale()
        info = LOCALES[locale]
        fake = self.faker[locale]
        username = self.username("cand", index)
        first, last = fake.first_name(), fake.last_name()
        user = self.user(username, first, last)
        role = self.role()
        years = self.rng.choices(range(26), weights=[3] * 6 + [2] * 10 + [1] * 10)[0]
        salary = self.salary(locale)[0] if self.chance(0.7) else None
        created = self.past(300, 1)
        candidate = Candidate(
            user=user,
            first_name=first,
            last_name=last,
            email=user.email,
            phone_number=self.phone(locale) if self.chance(0.8) else "",
            address=fake.address() if self.chance(0.6) else "",
            date_of_birth=fake.date_of_birth(minimum_age=18, maximum_age=60),
            headline=f"{role}, {years} years" if years else f"Junior {role}",
            city=self.rng.choice(info.cities),
            experience_years=years,
            education_level=self.rng.choice(["", *Candidate.Education.values]),
            expected_salary=salary,
            expected_salary_currency=info.currency,
            preferred_work_mode=self.rng.choice(["", *WorkMode.values]),
            linkedin_url=(
                f"https://www.linkedin.com/in/{username.replace('_', '-')}"
                if self.chance(0.5)
                else ""
            ),
            is_open_to_work=self.chance(0.85),
            language=info.language,
            created_at=created,
            updated_at=created,
        )
        wanted = list(ROLES[role])
        skills = self.rng.sample(wanted, self.rng.randint(1, len(wanted)))
        return clip(candidate), skills

    def status(self) -> str:
        return self.rng.choices(
            list(STATUS_WEIGHTS), weights=list(STATUS_WEIGHTS.values())
        )[0]

    def application(
        self, candidate: Candidate, posting: JobPosting, status: str | None = None
    ) -> FakeApplication:
        """An unsaved application (without a resume file) and its status history."""
        status = status or self.status()
        fake = self.faker[LOCALE_BY_LANGUAGE.get(candidate.language, "en_US")]
        start = max(posting.created_at or self.now, self.past(90))
        applied = min(start + timedelta(hours=self.rng.randint(1, 240)), self.now)
        application = Application(
            candidate=candidate,
            posting=posting,
            cover_letter=fake.paragraph(nb_sentences=4) if self.chance(0.7) else "",
            status=status,
            employer_note=fake.sentence() if self.chance(0.2) else "",
            applied_at=applied,
            updated_at=applied,
        )
        events: list[tuple[str, str, User | None, datetime]] = []
        previous: str = Application.Status.PENDING
        moment = applied
        for step in self.rng.choice(STATUS_PATHS[status]):
            actor = candidate.user if step == "withdrawn" else posting.employer.user
            moment = min(moment + timedelta(hours=self.rng.randint(2, 120)), self.now)
            events.append((previous, step, actor, moment))
            previous = step
        return FakeApplication(clip(application), events)

    def saved(self, candidate: Candidate, posting: JobPosting) -> SavedPosting:
        return SavedPosting(
            candidate=candidate, posting=posting, created_at=self.past(60)
        )

    def alert(
        self, candidate: Candidate, number: int = 1
    ) -> tuple[JobAlert, list[str]]:
        """An unsaved job alert and the names of 0-2 skills it filters on."""
        role = self.role()
        locale = LOCALE_BY_LANGUAGE.get(candidate.language, "en_US")
        created = self.past(60)
        alert = JobAlert(
            candidate=candidate,
            name=f"{role} #{number}",
            keywords=role.split()[0].lower() if self.chance(0.7) else "",
            location=self.rng.choice(LOCALES[locale].cities)
            if self.chance(0.4)
            else "",
            work_mode=self.rng.choice(["", *WorkMode.values]),
            employment_type=self.rng.choice(["", JobPosting.EmploymentType.FULL_TIME]),
            min_salary=self.salary(locale)[0] if self.chance(0.3) else None,
            frequency=self.rng.choice(JobAlert.Frequency.values),
            is_active=self.chance(0.9),
            created_at=created,
            updated_at=created,
        )
        skills = self.rng.sample(list(ROLES[role]), self.rng.randint(0, 2))
        return clip(alert), skills


def save_resume(application: Application) -> None:
    """Store a tiny PDF for ``application`` (needs ``posting_id``), like an upload.

    Fake resumes go to ``resumes/fake/`` so they are easy to tell apart and clean
    up; deleting an application removes its file (``applications.signals``).
    """
    name = resume_upload_to(application, "resume.pdf").replace(
        "resumes/", "resumes/fake/", 1
    )
    application.resume.name = default_storage.save(name, ContentFile(MINIMAL_PDF))


def ensure_skills(names=SKILLS) -> dict[str, Skill]:
    """Create the missing skills (in bulk) and return all of ``names`` by name."""
    names = list(dict.fromkeys(names))
    Skill.objects.bulk_create(
        [Skill(name=name) for name in names],
        ignore_conflicts=True,
        batch_size=BATCH_SIZE,
    )
    return {skill.name: skill for skill in Skill.objects.filter(name__in=names)}


@contextlib.contextmanager
def explicit_timestamps(*model_fields: models.DateTimeField) -> Iterator[None]:
    """Let ``auto_now``/``auto_now_add`` fields keep the values we set (backdating).

    Only for the seeding command: the flags are restored on exit.
    """
    saved = [(f, f.auto_now, f.auto_now_add) for f in model_fields]
    try:
        for model_field, _now, _add in saved:
            model_field.auto_now = model_field.auto_now_add = False
        yield
    finally:
        for model_field, auto_now, auto_now_add in saved:
            model_field.auto_now, model_field.auto_now_add = auto_now, auto_now_add


def _timestamp_fields() -> list[models.DateTimeField]:
    pairs = [
        (Employer, ("created_at", "updated_at")),
        (Candidate, ("created_at", "updated_at")),
        (JobPosting, ("created_at", "updated_at")),
        (Application, ("applied_at", "updated_at")),
        (ApplicationEvent, ("created_at",)),
        (SavedPosting, ("created_at",)),
        (JobAlert, ("created_at", "updated_at")),
    ]
    return [
        model._meta.get_field(name)  # type: ignore[misc]
        for model, names in pairs
        for name in names
    ]


def _bulk(model: type[models.Model], objs: list, batch_size: int) -> list:
    """``bulk_create`` that insists on getting primary keys back."""
    created = model._default_manager.bulk_create(objs, batch_size=batch_size)
    if any(obj.pk is None for obj in created):
        raise RuntimeError(
            f"The database did not return primary keys for {model.__name__} "
            "(needs SQLite 3.35+ or MariaDB 10.5+)."
        )
    return created


def _weighted_picker(
    rng: random.Random, size: int, skew: float
) -> Callable[[int], list[int]]:
    """Return ``pick(k)``: ``k`` indexes in ``range(size)``, low ones more often."""
    cum_weights = list(itertools.accumulate(1 / (i + 1) ** skew for i in range(size)))
    population = range(size)
    return lambda k: rng.choices(population, cum_weights=cum_weights, k=k)


@dataclass
class SeedResult:
    created: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    timings: dict[str, float] = field(default_factory=dict)
    posting_ids: list[int] = field(default_factory=list)
    application_ids: list[int] = field(default_factory=list)


def seed_database(  # noqa: PLR0912, PLR0913, PLR0915 - one linear recipe
    gen: FakeDataGenerator,
    *,
    employers: int,
    postings: int,
    candidates: int,
    applications: int,
    password: str = "",
    batch_size: int = BATCH_SIZE,
    log: Callable[[str], None] = lambda _msg: None,
) -> SeedResult:
    """Generate the whole data set from ``gen`` and insert what does not exist yet.

    Rows are keyed by username, (employer, title), (candidate, posting) and
    (candidate, alert name), so running it again with the same seed and counts
    creates nothing. The first fake employer and candidate get ``password`` (when
    given, for load tests); every other fake account has an unusable password.
    """
    result = SeedResult()
    clock = time.perf_counter()

    def lap(name: str) -> None:
        nonlocal clock
        now = time.perf_counter()
        result.timings[name] = now - clock
        clock = now
        log(f"  {name}: {result.timings[name]:.2f}s")

    existing_users = set(
        User.objects.filter(username__startswith=gen.prefix).values_list(
            "username", flat=True
        )
    )
    skills = ensure_skills()
    lap("skills")

    with transaction.atomic(), explicit_timestamps(*_timestamp_fields()):
        # ---------------------------------------------------- employers
        emp_list = [gen.employer(i) for i in range(employers)]
        new_emps = [e for e in emp_list if e.user.username not in existing_users]
        if password and emp_list and emp_list[0].user.username not in existing_users:
            emp_list[0].user.set_password(password)
        _bulk(User, [e.user for e in new_emps], batch_size)
        _bulk(Employer, new_emps, batch_size)
        result.created["employers"] = len(new_emps)
        old = {
            e.user.username: e
            for e in Employer.objects.filter(
                user__username__in=[e.user.username for e in emp_list if e.pk is None]
            ).select_related("user")
        }
        emp_list = [old.get(e.user.username, e) for e in emp_list]
        lap("employers")

        # ----------------------------------------------------- postings
        fake_postings = []
        if emp_list:
            owners = list(range(min(postings, len(emp_list))))
            owners += _weighted_picker(gen.rng, len(emp_list), 0.7)(
                max(0, postings - len(owners))
            )
            fake_postings = [gen.posting(emp_list[i]) for i in owners]
        existing_postings = {
            (employer_id, title): pk
            for employer_id, title, pk in JobPosting.objects.filter(
                employer__in=[e for e in emp_list if e.pk]
            ).values_list("employer_id", "title", "pk")
        }
        new_postings = []
        for fp in fake_postings:
            posting = fp.posting
            posting.employer = posting.employer  # copy the employer pk
            key = (posting.employer_id, posting.title)
            if key in existing_postings:
                posting.pk = existing_postings[key]
            else:
                new_postings.append(fp)
        _bulk(JobPosting, [fp.posting for fp in new_postings], batch_size)
        posting_skills = JobPosting.skills.through
        posting_skills.objects.bulk_create(
            [
                posting_skills(jobposting_id=fp.posting.pk, skill_id=skills[name].pk)
                for fp in new_postings
                for name in fp.skills
            ],
            batch_size=batch_size,
        )
        result.created["postings"] = len(new_postings)
        result.posting_ids = [fp.posting.pk for fp in new_postings]
        posting_list = [fp.posting for fp in fake_postings]
        lap("postings")

        # --------------------------------------------------- candidates
        cand_items = [gen.candidate(i) for i in range(candidates)]
        new_cands = [
            (c, s) for c, s in cand_items if c.user.username not in existing_users
        ]
        first = cand_items[0][0] if cand_items else None
        if password and first and first.user.username not in existing_users:
            first.user.set_password(password)
        _bulk(User, [c.user for c, _ in new_cands], batch_size)
        _bulk(Candidate, [c for c, _ in new_cands], batch_size)
        candidate_skills = Candidate.skills.through
        candidate_skills.objects.bulk_create(
            [
                candidate_skills(candidate_id=c.pk, skill_id=skills[name].pk)
                for c, names in new_cands
                for name in names
            ],
            batch_size=batch_size,
        )
        result.created["candidates"] = len(new_cands)
        old_cands = {
            c.user.username: c
            for c in Candidate.objects.filter(
                user__username__in=[
                    c.user.username for c, _ in cand_items if c.pk is None
                ]
            ).select_related("user")
        }
        cand_list = [old_cands.get(c.user.username, c) for c, _ in cand_items]
        lap("candidates")

        # ------------------------------------------------- applications
        fake_apps: list[FakeApplication] = []
        if cand_list and posting_list:
            target = min(applications, len(cand_list) * len(posting_list))
            seen: set[tuple[int, int]] = set()
            attempts = 0
            pick_candidate = _weighted_picker(gen.rng, len(cand_list), 0.3)
            pick_posting = _weighted_picker(gen.rng, len(posting_list), 0.5)
            while len(fake_apps) < target and attempts < target * 20:
                attempts += 1
                c, p = pick_candidate(1)[0], pick_posting(1)[0]
                if (c, p) in seen:
                    continue
                seen.add((c, p))
                fake_apps.append(gen.application(cand_list[c], posting_list[p]))
        existing_apps = set(
            Application.objects.filter(
                candidate__in=[c for c in cand_list if c.pk],
                posting__in=[p for p in posting_list if p.pk],
            ).values_list("candidate_id", "posting_id")
        )
        new_apps = []
        for fa in fake_apps:
            app = fa.application
            app.candidate, app.posting = app.candidate, app.posting  # copy the pks
            if (app.candidate_id, app.posting_id) not in existing_apps:
                new_apps.append(fa)
        lap("applications (generate)")
        for fa in new_apps:
            save_resume(fa.application)
        lap("resumes")
        _bulk(Application, [fa.application for fa in new_apps], batch_size)
        events = []
        for fa in new_apps:
            for from_status, to_status, actor, moment in fa.events:
                events.append(
                    ApplicationEvent(
                        application=fa.application,
                        from_status=from_status,
                        to_status=to_status,
                        actor=actor,
                        created_at=moment,
                    )
                )
        ApplicationEvent.objects.bulk_create(events, batch_size=batch_size)
        result.created["applications"] = len(new_apps)
        result.created["events"] = len(events)
        result.application_ids = [fa.application.pk for fa in new_apps]
        lap("applications")

        # ------------------------------------------- saved postings, alerts
        saved, alerts = [], []
        for candidate in cand_list:
            if posting_list:
                picks = gen.rng.sample(
                    range(len(posting_list)),
                    min(len(posting_list), gen.rng.randint(0, 4)),
                )
                saved += [gen.saved(candidate, posting_list[i]) for i in picks]
            if gen.chance(0.6):
                alerts += [
                    gen.alert(candidate, n + 1) for n in range(gen.rng.randint(1, 2))
                ]
        existing_saved = set(
            SavedPosting.objects.filter(
                candidate__in=[c for c in cand_list if c.pk]
            ).values_list("candidate_id", "posting_id")
        )
        new_saved = []
        for sp in saved:
            sp.candidate, sp.posting = sp.candidate, sp.posting
            if (sp.candidate_id, sp.posting_id) not in existing_saved:
                new_saved.append(sp)
        SavedPosting.objects.bulk_create(new_saved, batch_size=batch_size)
        existing_alerts = set(
            JobAlert.objects.filter(
                candidate__in=[c for c in cand_list if c.pk]
            ).values_list("candidate_id", "name")
        )
        new_alerts = []
        for alert, names in alerts:
            alert.candidate = alert.candidate
            if (alert.candidate_id, alert.name) not in existing_alerts:
                new_alerts.append((alert, names))
        _bulk(JobAlert, [a for a, _ in new_alerts], batch_size)
        alert_skills = JobAlert.skills.through
        alert_skills.objects.bulk_create(
            [
                alert_skills(jobalert_id=a.pk, skill_id=skills[name].pk)
                for a, names in new_alerts
                for name in names
            ],
            batch_size=batch_size,
        )
        result.created["saved postings"] = len(new_saved)
        result.created["job alerts"] = len(new_alerts)
        lap("saved postings and alerts")
    return result


def index_in_search(result: SeedResult, batch_size: int = BATCH_SIZE) -> int:
    """Index the new postings and applications in Elasticsearch.

    ``bulk_create`` sends no signals, so the autosync signal processor never sees
    these rows. Does nothing unless ``ELASTICSEARCH_DSL_AUTOSYNC`` is on. Returns the
    number of documents sent.
    """
    if not getattr(settings, "ELASTICSEARCH_DSL_AUTOSYNC", False):
        return 0
    querysets = {
        JobPosting: (
            JobPosting.objects.select_related("employer").prefetch_related("skills"),
            result.posting_ids,
        ),
        Application: (
            Application.objects.select_related("candidate", "posting__employer"),
            result.application_ids,
        ),
    }
    sent = 0
    for model, (queryset, ids) in querysets.items():
        for document in registry.get_documents([model]):
            for start in range(0, len(ids), batch_size):
                chunk = list(queryset.filter(pk__in=ids[start : start + batch_size]))
                document().update(chunk)
                sent += len(chunk)
    return sent


def wipe_fake_users(prefix: str = FAKE_PREFIX) -> int:
    """Delete every ``fake_`` user; their profiles, postings etc. go by cascade."""
    if not prefix.startswith(FAKE_PREFIX):
        raise ValueError(f"Only users starting with {FAKE_PREFIX!r} can be wiped.")
    users = User.objects.filter(username__startswith=prefix)
    count = users.count()
    users.delete()
    return count
