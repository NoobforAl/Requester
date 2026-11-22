import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.urls import reverse

from conftest import PDF_BYTES, make_pdf
from worker.models import JobRequest, Worker

pytestmark = pytest.mark.django_db


@pytest.fixture
def signed_in_worker(make_worker, client):
    worker = make_worker("sara")
    client.force_login(worker.user)
    return worker


@pytest.fixture
def job(make_offer, make_job):
    return make_job(make_offer("acme"))


def apply(client, job, **files):
    return client.post(
        reverse("worker_pick_jobs", args=[job.pk]),
        {"cover_letter": "hello", **files},
    )


def test_valid_pdf_is_stored_under_a_generated_name(signed_in_worker, job, client):
    response = apply(client, job, resume=make_pdf("../../evil name.pdf"))

    assert response.status_code == 302
    application = JobRequest.objects.get()
    assert application.worker == signed_in_worker
    name = application.resume.name or ""
    assert name.startswith(f"resumes/{job.pk}__")
    assert "evil" not in name
    assert application.resume.read() == PDF_BYTES


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("cv.docx", PDF_BYTES),
        ("cv.pdf", b"MZ not a pdf at all"),
        ("cv.pdf", PDF_BYTES + b"0" * (5 * 1024 * 1024)),
    ],
    ids=["wrong-extension", "wrong-magic-bytes", "too-large"],
)
def test_bad_uploads_are_rejected(signed_in_worker, job, client, name, content):
    apply(client, job, resume=make_pdf(name, content))
    assert JobRequest.objects.count() == 0


def test_uppercase_pdf_extension_is_accepted(signed_in_worker, job, client):
    apply(client, job, resume=make_pdf("CV.PDF"))
    assert JobRequest.objects.count() == 1


def test_second_application_for_same_job_is_refused(signed_in_worker, job, client):
    apply(client, job, resume=make_pdf())
    apply(client, job, resume=make_pdf())
    assert JobRequest.objects.count() == 1


def test_dashboard_counts_each_status(
    signed_in_worker, make_offer, make_job, make_application, client
):
    offer = make_offer("acme")
    for index, status in enumerate(["pending", "accepted", "accepted", "rejected"]):
        make_application(signed_in_worker, make_job(offer, f"job {index}"), status)

    response = client.get(reverse("worker_dashboard"))

    assert response.status_code == 200
    assert response.context["num_of_user_send_resume"] == 4
    assert response.context["accepted"] == 2
    assert response.context["rejected"] == 1
    assert response.context["in_progress"] == 1


def test_job_list_search_and_pages_render(signed_in_worker, job, client):
    search = client.get(reverse("worker_jobs"), {"search": job.job_name})
    assert search.status_code == 200
    assert client.get(reverse("worker_pick_jobs", args=[job.pk])).status_code == 200
    assert client.get(reverse("worker_pick_jobs", args=[9999])).status_code == 302
    assert client.get(reverse("worker_settings")).status_code == 200


def test_logout_requires_post(signed_in_worker, client):
    assert client.get(reverse("worker_logout")).status_code == 405
    assert client.post(reverse("worker_logout")).status_code == 302
    assert client.get(reverse("worker_dashboard")).status_code == 302


def test_registration_rejects_duplicate_email(make_worker, client):
    existing = make_worker("sara")
    response = client.post(
        reverse("worker_register"),
        {
            "username": "other",
            "first_name": "a",
            "last_name": "b",
            "email": existing.email,
            "password1": "pw-12345-xyz-long",
            "password2": "pw-12345-xyz-long",
        },
    )
    assert response.status_code == 200
    assert Worker.objects.count() == 1


def test_worker_email_is_unique_ignoring_case(make_worker):
    first = make_worker("sara")
    user = User.objects.create_user("other", "other@example.com", "pw-12345-xyz")
    with pytest.raises(IntegrityError), transaction.atomic():
        Worker.objects.create(
            user=user, first_name="o", last_name="t", email=first.email.upper()
        )


def test_applications_default_to_newest_first(
    make_worker, make_offer, make_job, make_application
):
    worker = make_worker("sara")
    offer = make_offer("acme")
    first = make_application(worker, make_job(offer, "one"))
    second = make_application(worker, make_job(offer, "two"))
    assert list(JobRequest.objects.all()) == [second, first]


def _resume_exists(application: JobRequest) -> bool:
    return application.resume.storage.exists(application.resume.name or "")


def test_resume_file_is_removed_when_the_application_is_deleted(
    make_worker,
    make_offer,
    make_job,
    make_application,
    django_capture_on_commit_callbacks,
):
    application = make_application(make_worker("sara"), make_job(make_offer("acme")))
    assert _resume_exists(application)

    with django_capture_on_commit_callbacks(execute=True):
        application.delete()

    assert not application.resume.storage.exists(application.resume.name or "")


def test_resume_file_is_removed_when_the_job_is_deleted(
    make_worker,
    make_offer,
    make_job,
    make_application,
    django_capture_on_commit_callbacks,
):
    job = make_job(make_offer("acme"))
    application = make_application(make_worker("sara"), job)
    name = application.resume.name

    with django_capture_on_commit_callbacks(execute=True):
        job.delete()  # cascades to the application

    assert not application.resume.storage.exists(name)


def test_failed_insert_does_not_leave_a_resume_file(
    signed_in_worker, job, client, monkeypatch
):
    storage = JobRequest._meta.get_field("resume").storage
    before = set(storage.listdir("resumes")[1]) if storage.exists("resumes") else set()

    def boom(self, *args, **kwargs):
        # let the FileField write the file (pre_save), then fail the INSERT
        self._meta.get_field("resume").pre_save(self, True)
        raise IntegrityError("simulated race")

    monkeypatch.setattr(JobRequest, "save", boom)
    response = apply(client, job, resume=make_pdf())

    assert response.status_code == 302
    assert JobRequest.objects.count() == 0
    after = set(storage.listdir("resumes")[1]) if storage.exists("resumes") else set()
    assert after == before
