"""Fill a development database with demo employers, postings, candidates, applications.

A small, hand-written world you can log in to (every account has the password
``password123``): ten employers in seven languages, about thirty postings (open,
expired and closed ones, with and without salary), a dozen candidates with profiles
of different completeness, and a few dozen applications that went through every
status with a history, employer notes and AI summaries. Created rows are backdated
over the last weeks so dashboards and charts show a timeline, not one single day.

Accounts and rows are keyed by username, (employer, title) and (candidate, posting),
and everything random is seeded from those keys, so the command is idempotent:
running it again creates nothing. It refuses to run unless ``DJANGO_DEBUG`` is on.
For volume (thousands of rows, the search log) use ``seed_fake_data``.
"""

import random
from datetime import date, datetime, time, timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from applications.models import Application, ApplicationEvent
from candidates.models import Candidate, JobAlert, SavedPosting
from employers.models import Employer, JobPosting, Skill

DEMO_PASSWORD = "password123"
MINIMAL_PDF = b"%PDF-1.4\n1 0 obj\n<< >>\nendobj\ntrailer\n<< >>\n%%EOF\n"

SKILLS = [
    "Python",
    "Django",
    "JavaScript",
    "TypeScript",
    "React",
    "SQL",
    "Docker",
    "Kubernetes",
    "Go",
    "Machine learning",
    "Data analysis",
    "Data engineering",
    "UX design",
    "Project management",
    "Product management",
    "Cyber security",
    "Android",
    "iOS",
    "DevOps",
    "Testing",
    "Embedded systems",
    "Customer support",
    "Technical writing",
]

# (username, company, email, industry, city, language, size)
EMPLOYERS = [
    ("alice", "Nova Cloud", "hr@novacloud.example", "Cloud", "Tehran", "fa", "51-200"),
    (
        "frank",
        "Brightline Software",
        "jobs@brightline.example",
        "Software",
        "Berlin",
        "de",
        "201-1000",
    ),
    (
        "grace",
        "Atlas Logistics",
        "careers@atlas.example",
        "Logistics",
        "Dubai",
        "ar",
        "1000+",
    ),
    ("heidi", "Pixel Studio", "team@pixel.example", "Design", "Paris", "fr", "11-50"),
    ("ivan", "Volga Systems", "hr@volga.example", "Software", "Moscow", "ru", "51-200"),
    (
        "judy",
        "Lotus Data",
        "hello@lotus.example",
        "Data",
        "Shanghai",
        "zh-hans",
        "11-50",
    ),
    (
        "karen",
        "Harbor Health Tech",
        "jobs@harborhealth.example",
        "Healthcare",
        "London",
        "en",
        "201-1000",
    ),
    (
        "leo",
        "Atelier Numérique",
        "bonjour@atelier.example",
        "Agency",
        "Lyon",
        "fr",
        "1-10",
    ),
    (
        "mia",
        "Kavir Commerce",
        "hr@kavir.example",
        "E-commerce",
        "Isfahan",
        "fa",
        "11-50",
    ),
    (
        "nick",
        "Dragon Robotics",
        "jobs@dragonrobotics.example",
        "Robotics",
        "Shenzhen",
        "zh-hans",
        "51-200",
    ),
]

#: How a posting stands: ``open`` (deadline ahead), ``expired`` (deadline passed) or
#: ``closed`` (the employer stopped accepting applications).
OPEN, EXPIRED, CLOSED = "open", "expired", "closed"

# (employer username, title, city, work mode, type, seniority, salary or None, skills,
#  state). Salary is (min, max, currency).
POSTINGS = [
    (
        "alice",
        "Backend Developer",
        "Tehran",
        "hybrid",
        "full_time",
        "mid",
        (30_000_000, 50_000_000, "IRR"),
        ["Python", "Django", "SQL"],
        OPEN,
    ),
    (
        "alice",
        "DevOps Engineer",
        "Tehran",
        "remote",
        "full_time",
        "senior",
        (60_000_000, 90_000_000, "IRR"),
        ["Docker", "Kubernetes", "DevOps"],
        OPEN,
    ),
    (
        "alice",
        "Site Reliability Engineer",
        "Tehran",
        "remote",
        "full_time",
        "senior",
        (70_000_000, 100_000_000, "IRR"),
        ["Kubernetes", "DevOps", "Go"],
        CLOSED,
    ),
    (
        "frank",
        "Frontend Developer",
        "Berlin",
        "onsite",
        "full_time",
        "junior",
        (45_000, 55_000, "EUR"),
        ["JavaScript", "React"],
        OPEN,
    ),
    (
        "frank",
        "Data Scientist",
        "Berlin",
        "hybrid",
        "full_time",
        "senior",
        (70_000, 90_000, "EUR"),
        ["Python", "Machine learning", "Data analysis"],
        OPEN,
    ),
    (
        "frank",
        "Python Trainer",
        "Berlin",
        "remote",
        "freelance",
        "mid",
        None,
        ["Python", "Technical writing"],
        EXPIRED,
    ),
    (
        "grace",
        "Logistics Analyst",
        "Dubai",
        "onsite",
        "contract",
        "mid",
        (12_000, 18_000, "AED"),
        ["Data analysis", "SQL"],
        OPEN,
    ),
    (
        "grace",
        "Operations Manager",
        "Dubai",
        "onsite",
        "full_time",
        "lead",
        (25_000, 35_000, "AED"),
        ["Project management"],
        OPEN,
    ),
    (
        "heidi",
        "UX Designer",
        "Paris",
        "remote",
        "freelance",
        "mid",
        (400, 600, "EUR"),
        ["UX design"],
        OPEN,
    ),
    (
        "heidi",
        "Mobile Developer",
        "Paris",
        "hybrid",
        "full_time",
        "mid",
        (50_000, 65_000, "EUR"),
        ["Android", "iOS"],
        OPEN,
    ),
    (
        "ivan",
        "Security Engineer",
        "Moscow",
        "onsite",
        "full_time",
        "senior",
        (250_000, 350_000, "RUB"),
        ["Cyber security"],
        OPEN,
    ),
    (
        "ivan",
        "Android Developer",
        "Moscow",
        "hybrid",
        "full_time",
        "junior",
        (120_000, 180_000, "RUB"),
        ["Android"],
        OPEN,
    ),
    (
        "judy",
        "ML Engineer",
        "Shanghai",
        "remote",
        "full_time",
        "senior",
        (30_000, 45_000, "CNY"),
        ["Python", "Machine learning"],
        OPEN,
    ),
    (
        "judy",
        "Technical Writer",
        "Shanghai",
        "remote",
        "part_time",
        "junior",
        (8_000, 12_000, "CNY"),
        ["Technical writing"],
        OPEN,
    ),
    (
        "judy",
        "Data Analyst",
        "Shanghai",
        "hybrid",
        "full_time",
        "junior",
        (12_000, 18_000, "CNY"),
        ["SQL", "Data analysis"],
        EXPIRED,
    ),
    (
        "karen",
        "Full-stack Engineer",
        "London",
        "hybrid",
        "full_time",
        "mid",
        (60_000, 80_000, "GBP"),
        ["JavaScript", "TypeScript", "Python", "SQL"],
        OPEN,
    ),
    (
        "karen",
        "Data Engineer",
        "London",
        "remote",
        "full_time",
        "senior",
        (80_000, 105_000, "GBP"),
        ["Python", "SQL", "Data engineering", "Docker"],
        OPEN,
    ),
    (
        "karen",
        "QA Automation Engineer",
        "London",
        "onsite",
        "contract",
        "mid",
        (450, 550, "GBP"),
        ["Testing", "Python"],
        OPEN,
    ),
    (
        "karen",
        "Product Intern",
        "London",
        "hybrid",
        "internship",
        "intern",
        (1_800, 2_200, "GBP"),
        ["Product management"],
        OPEN,
    ),
    (
        "leo",
        "Directeur artistique",
        "Lyon",
        "hybrid",
        "full_time",
        "senior",
        (48_000, 60_000, "EUR"),
        ["UX design"],
        OPEN,
    ),
    (
        "leo",
        "Développeur front-end",
        "Lyon",
        "remote",
        "freelance",
        "mid",
        (400, 520, "EUR"),
        ["JavaScript", "React", "TypeScript"],
        OPEN,
    ),
    (
        "leo",
        "Community manager",
        "Lyon",
        "onsite",
        "part_time",
        "junior",
        None,
        ["Customer support"],
        OPEN,
    ),
    (
        "mia",
        "برنامه‌نویس جنگو",
        "Isfahan",
        "hybrid",
        "full_time",
        "mid",
        (35_000_000, 55_000_000, "IRR"),
        ["Python", "Django", "SQL"],
        OPEN,
    ),
    (
        "mia",
        "Product Manager",
        "Isfahan",
        "hybrid",
        "full_time",
        "senior",
        (70_000_000, 100_000_000, "IRR"),
        ["Product management", "Project management"],
        OPEN,
    ),
    (
        "mia",
        "Customer Support Specialist",
        "Isfahan",
        "onsite",
        "full_time",
        "junior",
        (15_000_000, 22_000_000, "IRR"),
        ["Customer support"],
        EXPIRED,
    ),
    (
        "nick",
        "Robotics Software Engineer",
        "Shenzhen",
        "onsite",
        "full_time",
        "mid",
        (25_000, 40_000, "CNY"),
        ["Python", "Go", "Machine learning"],
        OPEN,
    ),
    (
        "nick",
        "Embedded Firmware Engineer",
        "Shenzhen",
        "onsite",
        "full_time",
        "senior",
        (35_000, 55_000, "CNY"),
        ["Embedded systems", "Testing"],
        OPEN,
    ),
    (
        "nick",
        "Machine Learning Intern",
        "Shenzhen",
        "hybrid",
        "internship",
        "intern",
        (4_000, 6_000, "CNY"),
        ["Python", "Machine learning"],
        OPEN,
    ),
]

CITY_COUNTRY = {
    "Tehran": "Iran",
    "Isfahan": "Iran",
    "Berlin": "Germany",
    "Dubai": "United Arab Emirates",
    "Paris": "France",
    "Lyon": "France",
    "Moscow": "Russia",
    "Shanghai": "China",
    "Shenzhen": "China",
    "London": "United Kingdom",
    "Remote": "",
}

# (username, first, last, city, headline, years, skills, work mode, language,
#  education, expected salary or None, open to work)
# worker1-worker4 are the original demo accounts; the load generator logs in as worker1.
CANDIDATES = [
    (
        "worker1",
        "Ali",
        "Rezaei",
        "Tehran",
        "Backend developer",
        4,
        ["Python", "Django", "SQL"],
        "hybrid",
        "fa",
        "bachelor",
        (40_000_000, "IRR"),
        True,
    ),
    (
        "worker2",
        "Maryam",
        "Ahmadi",
        "Berlin",
        "Data scientist",
        6,
        ["Python", "Machine learning"],
        "remote",
        "en",
        "master",
        (85_000, "EUR"),
        True,
    ),
    (
        "worker3",
        "Hossein",
        "Karimi",
        "Paris",
        "Mobile developer",
        3,
        ["Android", "iOS"],
        "onsite",
        "fr",
        "bachelor",
        (55_000, "EUR"),
        True,
    ),
    (
        "worker4",
        "Zahra",
        "Moradi",
        "Dubai",
        "UX designer",
        5,
        ["UX design"],
        "remote",
        "ar",
        "bachelor",
        None,
        True,
    ),
    (
        "worker5",
        "Lena",
        "Fischer",
        "Munich",
        "Full-stack developer",
        7,
        ["JavaScript", "TypeScript", "React", "Python", "SQL"],
        "hybrid",
        "de",
        "master",
        (75_000, "EUR"),
        True,
    ),
    (
        "worker6",
        "Dmitri",
        "Petrov",
        "Moscow",
        "Security engineer",
        9,
        ["Cyber security", "Docker"],
        "onsite",
        "ru",
        "master",
        (300_000, "RUB"),
        True,
    ),
    (
        "worker7",
        "Wei",
        "Zhang",
        "Shanghai",
        "ML engineer",
        5,
        ["Python", "Machine learning", "Data analysis"],
        "remote",
        "zh-hans",
        "doctorate",
        (40_000, "CNY"),
        True,
    ),
    (
        "worker8",
        "Sara",
        "Johnson",
        "London",
        "Data engineer",
        8,
        ["Python", "SQL", "Data engineering", "Docker"],
        "remote",
        "en",
        "master",
        (95_000, "GBP"),
        True,
    ),
    (
        "worker9",
        "Omar",
        "Haddad",
        "Dubai",
        "Operations analyst",
        2,
        ["Data analysis", "SQL", "Project management"],
        "onsite",
        "ar",
        "bachelor",
        (14_000, "AED"),
        True,
    ),
    (
        "worker10",
        "Camille",
        "Dubois",
        "Lyon",
        "Front-end developer",
        1,
        ["JavaScript", "React"],
        "remote",
        "fr",
        "associate",
        (36_000, "EUR"),
        True,
    ),
    (
        "worker11",
        "Niloofar",
        "Sadeghi",
        "Isfahan",
        "Product manager",
        10,
        ["Product management", "Project management", "UX design"],
        "hybrid",
        "fa",
        "master",
        (85_000_000, "IRR"),
        False,  # not looking right now
    ),
    # A brand-new account: nothing filled in but the name (profile 0%).
    (
        "worker12",
        "Tom",
        "Becker",
        "",
        "",
        None,
        [],
        "",
        "en",
        "",
        None,
        True,
    ),
]

COVER_LETTERS = [
    "I have {years} years of experience and the {title} role at {company} is exactly "
    "what I am looking for. I would be glad to talk about how I can help your team.",
    "Hello {company} team, I enjoy shipping reliable software and your {title} "
    "opening matches my background. My CV is attached.",
    "I am excited about {company}. At my last job I owned features end to end, from "
    "the first idea to production, and I would like to do the same as your {title}.",
    "",  # some candidates only send the CV
]
EMPLOYER_NOTES = [
    "Strong CV. Call this week.",
    "Good fit on skills, salary expectation is high.",
    "Waiting for a second opinion from the tech lead.",
    "Nice portfolio, asked for a code sample.",
    "Not enough experience for this level.",
    "Moved to the other opening.",
]
AI_SUMMARY = (
    "{first} has {years} years of experience in {skills}. The CV shows steady work "
    "on production systems and clear writing. A good match for the {title} role."
)

#: Status mix of demo applications (weights).
STATUS_WEIGHTS = {
    "pending": 30,
    "in_review": 22,
    "shortlisted": 14,
    "accepted": 8,
    "rejected": 18,
    "withdrawn": 8,
}
#: How an application reached each status, after "pending".
STATUS_PATHS = {
    "pending": ((),),
    "in_review": (("in_review",),),
    "shortlisted": (("in_review", "shortlisted"),),
    "accepted": (("in_review", "shortlisted", "accepted"),),
    "rejected": (("rejected",), ("in_review", "rejected")),
    "withdrawn": (("withdrawn",), ("in_review", "withdrawn")),
}
#: Every fifth open posting has no deadline (open until filled).
NO_DEADLINE_EVERY = 5
#: Share of applications with an AI summary, and of status changes with a note.
SUMMARY_SHARE = 0.5
EVENT_NOTE_SHARE = 0.4
#: How many postings each candidate applies to: matching ones, then random others.
MATCHING_APPLICATIONS = 4
OTHER_APPLICATIONS = 2


class Command(BaseCommand):
    help = "Insert demo employers, skills, postings, candidates and applications."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "Demo accounts use a well-known password, so this command only "
                "runs with DJANGO_DEBUG on."
            )

        self.now = timezone.now()
        skills = {name: Skill.objects.get_or_create(name=name)[0] for name in SKILLS}
        employers = self.create_employers()
        postings = self.create_postings(employers, skills)
        candidates = self.create_candidates(skills)
        applications = self.create_applications(candidates, postings)
        self.create_saved_and_alerts(candidates, postings, skills)
        self.stdout.write(
            self.style.SUCCESS(
                f"Demo data ready: {len(employers)} employers, {len(postings)} "
                f"postings, {len(candidates)} candidates, {applications} new "
                "applications."
            )
        )

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def rng(*key: str) -> random.Random:
        """A random generator seeded from ``key``: the same rows get the same data."""
        return random.Random(":".join(key))

    @staticmethod
    def user(username: str, email: str, first: str = "", last: str = "") -> User:
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": email, "first_name": first, "last_name": last},
        )
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save()
        return user

    def backdate(self, instance, days: float, **extra_fields: datetime) -> None:
        """Move ``created_at`` (and ``updated_at``) of a new row ``days`` back."""
        moment = self.now - timedelta(days=days)
        fields = {"created_at": moment, "updated_at": moment, **extra_fields}
        fields = {k: v for k, v in fields.items() if hasattr(instance, k)}
        type(instance).objects.filter(pk=instance.pk).update(**fields)
        for name, value in fields.items():
            setattr(instance, name, value)

    # -------------------------------------------------------------- employers
    def create_employers(self) -> dict[str, Employer]:
        employers = {}
        for index, row in enumerate(EMPLOYERS):
            username, name, email, industry, city, language, size = row
            employer, created = Employer.objects.get_or_create(
                user=self.user(username, email),
                defaults={
                    "name": name,
                    "contact_email": email,
                    "description": f"{name} builds products in {industry.lower()}. "
                    "A friendly team that ships often and reviews every change.",
                    "industry": industry,
                    "size": size,
                    "city": city,
                    "language": language,
                    "website": f"https://{email.split('@')[1]}",
                },
            )
            if created:
                self.backdate(employer, 120 - index * 9)
            employers[username] = employer
        return employers

    # --------------------------------------------------------------- postings
    def create_postings(self, employers, skills) -> list[JobPosting]:
        today = timezone.localdate()
        postings = []
        for index, row in enumerate(POSTINGS):
            username, title, city, mode, kind, level, salary, wanted, state = row
            employer = employers[username]
            rng = self.rng("posting", username, title)
            deadline: date | None
            deadline, age = {
                OPEN: (today + timedelta(days=rng.randint(5, 40)), rng.randint(2, 35)),
                EXPIRED: (
                    today - timedelta(days=rng.randint(3, 30)),
                    rng.randint(50, 80),
                ),
                CLOSED: (today + timedelta(days=10), rng.randint(20, 45)),
            }[state]
            if index % NO_DEADLINE_EVERY == NO_DEADLINE_EVERY - 1 and state == OPEN:
                deadline = None  # some postings stay open until filled
            posting, created = JobPosting.objects.get_or_create(
                employer=employer,
                title=title,
                defaults={
                    "description": self.describe(title, employer.name, wanted, level),
                    "location": city,
                    "country": CITY_COUNTRY.get(city, ""),
                    "work_mode": mode,
                    "employment_type": kind,
                    "seniority": level,
                    "salary_min": salary[0] if salary else None,
                    "salary_max": salary[1] if salary else None,
                    "salary_currency": salary[2] if salary else "USD",
                    "deadline": deadline,
                    "is_active": state != CLOSED,
                },
            )
            if created:
                posting.skills.set(skills[name] for name in wanted)
                self.backdate(posting, age)
            postings.append(posting)
        return postings

    @staticmethod
    def describe(title: str, company: str, wanted: list[str], level: str) -> str:
        needs = "\n".join(f"- {name}" for name in wanted)
        return (
            f"{company} is looking for a {title}.\n\n"
            "What you will do\n"
            "- Work with a friendly team on real products used every day\n"
            "- Review code, share what you learn and own what you ship\n"
            f"- Grow as a {level or 'team'} member with a mentor\n\n"
            f"What we are looking for\n{needs}\n"
            "- Clear communication and care about quality\n\n"
            "We reply to every application."
        )

    # ------------------------------------------------------------- candidates
    def create_candidates(self, skills) -> list[Candidate]:
        candidates = []
        for index, row in enumerate(CANDIDATES):
            username, first, last, city, headline, years, own, mode, lang = row[:9]
            education, salary, open_to_work = row[9:]
            email = f"{first}.{last}@example.com".lower()
            rich = bool(headline)
            candidate, created = Candidate.objects.get_or_create(
                user=self.user(username, email, first, last),
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "email": email,
                    "phone_number": f"+1555010{index:04d}" if rich else "",
                    "city": city,
                    "headline": headline,
                    "experience_years": years,
                    "education_level": education,
                    "expected_salary": salary[0] if salary else None,
                    "expected_salary_currency": salary[1] if salary else "IRR",
                    "preferred_work_mode": mode,
                    "linkedin_url": (
                        f"https://www.linkedin.com/in/{first}-{last}".lower()
                        if rich
                        else ""
                    ),
                    "is_open_to_work": open_to_work,
                    "language": lang,
                },
            )
            if created:
                candidate.skills.set(skills[name] for name in own)
                self.backdate(candidate, 75 - index * 6)
            candidates.append(candidate)
        return candidates

    # ----------------------------------------------------------- applications
    def create_applications(self, candidates, postings) -> int:
        resume = Path(settings.MEDIA_ROOT) / "resumes" / "resume.pdf"
        resume.parent.mkdir(parents=True, exist_ok=True)
        if not resume.exists():
            resume.write_bytes(MINIMAL_PDF)

        created = 0
        for candidate in candidates:
            own = {s.name for s in candidate.skills.all()}
            if not own:
                continue  # the empty profile has not applied anywhere yet
            rng = self.rng("applications", candidate.user.username)
            matching = [p for p in postings if own & {s.name for s in p.skills.all()}]
            others = [p for p in postings if p not in matching]
            rng.shuffle(matching)
            rng.shuffle(others)
            picks = matching[:MATCHING_APPLICATIONS] + others[:OTHER_APPLICATIONS]
            for posting in picks:
                created += self.apply(candidate, posting, own)
        return created

    def apply(self, candidate: Candidate, posting: JobPosting, own: set[str]) -> int:
        if Application.objects.filter(candidate=candidate, posting=posting).exists():
            return 0
        rng = self.rng("apply", candidate.user.username, posting.title)
        status = rng.choices(list(STATUS_WEIGHTS), list(STATUS_WEIGHTS.values()))[0]
        letter = rng.choice(COVER_LETTERS).format(
            years=candidate.experience_years or 0,
            title=posting.title,
            company=posting.employer.name,
        )
        # Applied between the day the posting went up and now (or its deadline).
        end = self.now
        if posting.deadline:
            end = min(
                end,
                timezone.make_aware(datetime.combine(posting.deadline, time.max)),
            )
        start = min(posting.created_at + timedelta(hours=2), end)
        applied = start + (end - start) * rng.random()

        reviewed = status != "pending"
        summary = rng.random() < SUMMARY_SHARE
        application = Application.objects.create(
            candidate=candidate,
            posting=posting,
            resume="resumes/resume.pdf",
            cover_letter=letter,
            status="pending",
            employer_note=rng.choice(EMPLOYER_NOTES) if reviewed else "",
            ai_summary=AI_SUMMARY.format(
                first=candidate.first_name,
                years=candidate.experience_years or 0,
                skills=", ".join(sorted(own)),
                title=posting.title,
            )
            if summary
            else "",
            ai_provider="openrouter" if summary else "",
        )
        moment = applied
        previous = "pending"
        for step in rng.choice(STATUS_PATHS[status]):
            actor = candidate.user if step == "withdrawn" else posting.employer.user
            moment = min(moment + timedelta(hours=rng.randint(3, 96)), self.now)
            event = ApplicationEvent.objects.create(
                application=application,
                from_status=previous,
                to_status=step,
                actor=actor,
                note=rng.choice(EMPLOYER_NOTES)
                if rng.random() < EVENT_NOTE_SHARE
                else "",
            )
            ApplicationEvent.objects.filter(pk=event.pk).update(created_at=moment)
            previous = step
        Application.objects.filter(pk=application.pk).update(
            status=status, applied_at=applied, updated_at=moment
        )
        return 1

    # ----------------------------------------------------- saved and alerts
    def create_saved_and_alerts(self, candidates, postings, skills) -> None:
        open_postings = [
            p
            for p in postings
            if p.is_active
            and (p.deadline is None or p.deadline >= timezone.localdate())
        ]
        for candidate in candidates:
            own = list(candidate.skills.all())
            if not own:
                continue
            rng = self.rng("saved", candidate.user.username)
            for posting in rng.sample(open_postings, rng.randint(2, 6)):
                saved, created = SavedPosting.objects.get_or_create(
                    candidate=candidate, posting=posting
                )
                if created:
                    SavedPosting.objects.filter(pk=saved.pk).update(
                        created_at=self.now - timedelta(days=rng.randint(0, 20))
                    )
            self.create_alert(
                candidate,
                f"{candidate.headline} jobs",
                keywords=candidate.headline.split()[0].lower(),
                location=candidate.city,
                frequency=JobAlert.Frequency.DAILY
                if candidate.pk % 2
                else JobAlert.Frequency.WEEKLY,
                skills=own[:2],
            )

        first = candidates[0]
        self.create_alert(
            first,
            "Remote Python jobs",
            keywords="developer",
            work_mode="remote",
            skills=[skills["Python"]],
        )
        self.create_alert(
            first,
            "Paused: senior roles",
            keywords="senior",
            min_salary=60_000_000,
            is_active=False,
        )

    def create_alert(
        self, candidate: Candidate, name: str, skills=(), **fields
    ) -> None:
        alert, created = JobAlert.objects.get_or_create(
            candidate=candidate, name=name, defaults=fields
        )
        if created:
            alert.skills.set(skills)
            self.backdate(alert, self.rng("alert", name).randint(5, 40))
