import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile

from offer.models import Job, Offer
from worker.models import JobRequest, Worker

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< >>\nendobj\ntrailer\n<< >>\n%%EOF\n"


def make_pdf(name: str = "cv.pdf", content: bytes = PDF_BYTES) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content, content_type="application/pdf")


@pytest.fixture
def make_offer(db):
    def _make(name: str = "acme") -> Offer:
        user = User.objects.create_user(name, f"{name}@example.com", "pw-12345-xyz")
        return Offer.objects.create(
            user=user,
            company_name=name,
            company_email=f"hr@{name}.example.com",
            detail="detail",
        )

    return _make


@pytest.fixture
def make_worker(db):
    def _make(name: str = "sara") -> Worker:
        user = User.objects.create_user(name, f"{name}@example.com", "pw-12345-xyz")
        return Worker.objects.create(
            user=user, first_name=name, last_name="test", email=f"{name}@example.com"
        )

    return _make


@pytest.fixture
def make_job(db):
    def _make(offer: Offer, name: str = "Backend developer") -> Job:
        return Job.objects.create(job_name=name, detail="detail", offer=offer)

    return _make


@pytest.fixture
def make_application(db):
    def _make(worker: Worker, job: Job, status: str = "pending") -> JobRequest:
        return JobRequest.objects.create(
            worker=worker, job=job, resume=make_pdf(), status=status
        )

    return _make
