import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile

from applications.models import Application
from candidates.models import Candidate
from employers.models import Employer, JobPosting

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< >>\nendobj\ntrailer\n<< >>\n%%EOF\n"


def make_pdf(name: str = "cv.pdf", content: bytes = PDF_BYTES) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content, content_type="application/pdf")


@pytest.fixture
def make_employer(db):
    def _make(name: str = "acme", **extra) -> Employer:
        user = User.objects.create_user(name, f"{name}@example.com", "pw-12345-xyz")
        return Employer.objects.create(
            user=user,
            name=name,
            contact_email=f"hr@{name}.example.com",
            description="description",
            **extra,
        )

    return _make


@pytest.fixture
def make_candidate(db):
    def _make(name: str = "sara", **extra) -> Candidate:
        user = User.objects.create_user(name, f"{name}@example.com", "pw-12345-xyz")
        return Candidate.objects.create(
            user=user,
            first_name=name,
            last_name="test",
            email=f"{name}@example.com",
            **extra,
        )

    return _make


@pytest.fixture
def make_posting(db):
    def _make(
        employer: Employer, title: str = "Backend developer", **extra
    ) -> JobPosting:
        return JobPosting.objects.create(
            title=title, description="description", employer=employer, **extra
        )

    return _make


@pytest.fixture
def make_application(db):
    def _make(
        candidate: Candidate, posting: JobPosting, status: str = "pending"
    ) -> Application:
        return Application.objects.create(
            candidate=candidate, posting=posting, resume=make_pdf(), status=status
        )

    return _make
