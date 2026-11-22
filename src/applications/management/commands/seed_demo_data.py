"""Fill a development database with demo employers, postings, candidates, applications.

Demo accounts share a well-known password, so the command refuses to run unless
``DJANGO_DEBUG`` is on. It is idempotent: existing usernames are left alone.
"""

from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from applications.models import Application
from candidates.models import Candidate, JobAlert, SavedPosting
from employers.models import Employer, JobPosting, Skill

DEMO_PASSWORD = "password123"
MINIMAL_PDF = b"%PDF-1.4\n1 0 obj\n<< >>\nendobj\ntrailer\n<< >>\n%%EOF\n"

SKILLS = [
    "Python",
    "Django",
    "JavaScript",
    "React",
    "SQL",
    "Docker",
    "Kubernetes",
    "Machine learning",
    "Data analysis",
    "UX design",
    "Project management",
    "Cyber security",
    "Android",
    "iOS",
    "DevOps",
    "Technical writing",
]

EMPLOYERS = [
    ("alice", "Nova Cloud", "hr@novacloud.example", "Cloud", "Tehran", "fa"),
    (
        "frank",
        "Brightline Software",
        "jobs@brightline.example",
        "Software",
        "Berlin",
        "de",
    ),
    ("grace", "Atlas Logistics", "careers@atlas.example", "Logistics", "Dubai", "ar"),
    ("heidi", "Pixel Studio", "team@pixel.example", "Design", "Paris", "fr"),
    ("ivan", "Volga Systems", "hr@volga.example", "Software", "Moscow", "ru"),
    ("judy", "Lotus Data", "hello@lotus.example", "Data", "Shanghai", "zh-hans"),
]

# (employer username, title, city, work mode, type, seniority, salary range, skills)
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
    ),
]

# (username, first, last, email, city, headline, years, skills, work mode, language)
CANDIDATES = [
    (
        "worker1",
        "Ali",
        "Rezaei",
        "ali.rezaei@example.com",
        "Tehran",
        "Backend developer",
        4,
        ["Python", "Django", "SQL"],
        "hybrid",
        "fa",
    ),
    (
        "worker2",
        "Maryam",
        "Ahmadi",
        "maryam.ahmadi@example.com",
        "Berlin",
        "Data scientist",
        6,
        ["Python", "Machine learning"],
        "remote",
        "en",
    ),
    (
        "worker3",
        "Hossein",
        "Karimi",
        "hossein.karimi@example.com",
        "Paris",
        "Mobile developer",
        3,
        ["Android", "iOS"],
        "onsite",
        "fr",
    ),
    (
        "worker4",
        "Zahra",
        "Moradi",
        "zahra.moradi@example.com",
        "Dubai",
        "UX designer",
        5,
        ["UX design"],
        "remote",
        "ar",
    ),
]


class Command(BaseCommand):
    help = "Insert demo employers, skills, postings, candidates and applications."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "Demo accounts use a well-known password, so this command only "
                "runs with DJANGO_DEBUG on."
            )

        skills = {name: Skill.objects.get_or_create(name=name)[0] for name in SKILLS}
        employers = self.create_employers()
        postings = self.create_postings(employers, skills)
        candidates = self.create_candidates(skills)
        applications = self.create_applications(candidates, postings)
        self.create_saved_and_alerts(candidates, postings, skills)
        self.stdout.write(
            self.style.SUCCESS(
                f"Demo data ready: {len(employers)} employers, {len(postings)} "
                f"postings, {len(candidates)} candidates, {applications} applications."
            )
        )

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

    def create_employers(self) -> dict[str, Employer]:
        employers = {}
        for username, name, email, industry, city, language in EMPLOYERS:
            employers[username], _ = Employer.objects.get_or_create(
                user=self.user(username, email),
                defaults={
                    "name": name,
                    "contact_email": email,
                    "description": f"{name} builds products in {industry.lower()}.",
                    "industry": industry,
                    "city": city,
                    "language": language,
                    "website": f"https://{email.split('@')[1]}",
                },
            )
        return employers

    @staticmethod
    def create_postings(employers, skills) -> list[JobPosting]:
        today = timezone.localdate()
        postings = []
        for index, row in enumerate(POSTINGS):
            username, title, city, mode, kind, level, salary, wanted = row
            posting, created = JobPosting.objects.get_or_create(
                employer=employers[username],
                title=title,
                defaults={
                    "description": f"{title} at {employers[username].name}. "
                    "Work with a friendly team on real products.",
                    "location": city,
                    "work_mode": mode,
                    "employment_type": kind,
                    "seniority": level,
                    "salary_min": salary[0],
                    "salary_max": salary[1],
                    "salary_currency": salary[2],
                    "deadline": today + timedelta(days=14 + index * 3),
                },
            )
            if created:
                posting.skills.set(skills[name] for name in wanted)
            postings.append(posting)
        return postings

    def create_candidates(self, skills) -> list[Candidate]:
        candidates = []
        for (
            username,
            first,
            last,
            email,
            city,
            headline,
            years,
            own,
            mode,
            lang,
        ) in CANDIDATES:
            candidate, created = Candidate.objects.get_or_create(
                user=self.user(username, email, first, last),
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "email": email,
                    "city": city,
                    "headline": headline,
                    "experience_years": years,
                    "preferred_work_mode": mode,
                    "language": lang,
                },
            )
            if created:
                candidate.skills.set(skills[name] for name in own)
            candidates.append(candidate)
        return candidates

    def create_applications(self, candidates, postings) -> int:
        if Application.objects.exists():
            return 0
        resume = Path(settings.MEDIA_ROOT) / "resumes" / "resume.pdf"
        resume.parent.mkdir(parents=True, exist_ok=True)
        if not resume.exists():
            resume.write_bytes(MINIMAL_PDF)

        statuses = ["pending", "in_review", "shortlisted", "rejected"]
        created = 0
        for index, candidate in enumerate(candidates):
            for offset in range(3):
                posting = postings[(index * 2 + offset) % len(postings)]
                _app, was_created = Application.objects.get_or_create(
                    candidate=candidate,
                    posting=posting,
                    defaults={
                        "resume": "resumes/resume.pdf",
                        "cover_letter": "I have the experience this role needs.",
                        "status": statuses[(index + offset) % len(statuses)],
                    },
                )
                created += was_created
        return created

    @staticmethod
    def create_saved_and_alerts(candidates, postings, skills) -> None:
        first = candidates[0]
        for posting in postings[2:4]:
            SavedPosting.objects.get_or_create(candidate=first, posting=posting)
        alert, created = JobAlert.objects.get_or_create(
            candidate=first,
            name="Remote Python jobs",
            defaults={"keywords": "developer", "work_mode": "remote"},
        )
        if created:
            alert.skills.set([skills["Python"]])
