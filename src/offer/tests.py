import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.urls import reverse

from offer import views
from offer.models import Job, Offer, Tag
from worker.models import JobRequest

pytestmark = pytest.mark.django_db


@pytest.fixture
def two_employers(make_offer, make_job, make_worker, make_application, client):
    """Employer A owns a job with one application; employer B is signed in."""
    owner = make_offer("owner")
    intruder = make_offer("intruder")
    job = make_job(owner)
    application = make_application(make_worker("sara"), job)
    client.force_login(intruder.user)
    return job, application, intruder


def test_employer_cannot_open_or_change_another_employers_job(two_employers, client):
    job, _, _ = two_employers
    url = reverse("offer_job", args=[job.pk])

    assert client.get(url).status_code == 302
    client.post(
        reverse("offer_job_edit", args=[job.pk]), {"job_name": "hacked", "detail": "x"}
    )
    client.post(reverse("offer_job_delete", args=[job.pk]))
    client.post(reverse("offer_job_report", args=[job.pk]))

    job.refresh_from_db()
    assert job.job_name != "hacked"
    assert Job.objects.filter(pk=job.pk).exists()


def test_employer_cannot_download_another_employers_resume(two_employers, client):
    _, application, _ = two_employers
    response = client.get(reverse("download_resume", args=[application.pk]))
    assert response.status_code == 302


def test_employer_cannot_change_status_of_another_employers_application(
    two_employers, client
):
    _, application, _ = two_employers
    client.post(reverse("resume_status", args=[application.pk]), {"status": "accepted"})
    application.refresh_from_db()
    assert application.status == "pending"


def test_owner_can_change_status_and_download_resume(
    make_offer, make_job, make_worker, make_application, client
):
    owner = make_offer("owner")
    application = make_application(make_worker("sara"), make_job(owner))
    client.force_login(owner.user)

    client.post(reverse("resume_status", args=[application.pk]), {"status": "accepted"})
    application.refresh_from_db()
    assert application.status == "accepted"

    response = client.get(reverse("download_resume", args=[application.pk]))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert b"".join(response.streaming_content).startswith(b"%PDF-")


def test_invalid_status_is_rejected(
    make_offer, make_job, make_worker, make_application, client
):
    owner = make_offer("owner")
    application = make_application(make_worker("sara"), make_job(owner))
    client.force_login(owner.user)

    client.post(reverse("resume_status", args=[application.pk]), {"status": "hired!!"})
    application.refresh_from_db()
    assert application.status == JobRequest.Status.PENDING


def test_settings_update_changes_the_existing_offer(make_offer, client):
    offer = make_offer("owner")
    client.force_login(offer.user)

    response = client.post(
        reverse("offer_settings"),
        {
            "company_name": "New name",
            "company_email": offer.company_email,
            "detail": "new detail",
        },
    )

    assert response.status_code == 302
    assert Offer.objects.count() == 1
    offer.refresh_from_db()
    assert offer.company_name == "New name"


def test_job_create_edit_delete_flow(make_offer, client):
    offer = make_offer("owner")
    client.force_login(offer.user)

    client.post(reverse("offer_jobs"), {"job_name": "Designer", "detail": "d"})
    job = Job.objects.get(job_name="Designer")
    assert job.offer == offer

    client.post(
        reverse("offer_job_edit", args=[job.pk]),
        {"job_name": "Lead designer", "detail": "d"},
    )
    job.refresh_from_db()
    assert job.job_name == "Lead designer"

    delete_url = reverse("offer_job_delete", args=[job.pk])
    assert client.get(delete_url).status_code == 405
    assert Job.objects.filter(pk=job.pk).exists()
    assert client.post(delete_url).status_code == 302
    assert not Job.objects.filter(pk=job.pk).exists()


def test_dashboard_and_pages_render(
    make_offer, make_job, make_worker, make_application, client
):
    offer = make_offer("owner")
    job = make_job(offer)
    make_application(make_worker("sara"), job)
    client.force_login(offer.user)

    for name in ("offer_dashboard", "offer_jobs", "offer_settings"):
        assert client.get(reverse(name)).status_code == 200
    assert client.get(reverse("offer_job", args=[job.pk])).status_code == 200


def test_logout_requires_post(make_offer, client):
    offer = make_offer("owner")
    client.force_login(offer.user)

    assert client.get(reverse("offer_logout")).status_code == 405
    assert client.get(reverse("offer_dashboard")).status_code == 200

    assert client.post(reverse("offer_logout")).status_code == 302
    assert client.get(reverse("offer_dashboard")).status_code == 302


def test_worker_account_cannot_use_the_employer_portal(make_worker, client):
    worker = make_worker("sara")
    client.force_login(worker.user)

    response = client.get(reverse("offer_dashboard"))
    assert response.status_code == 302
    assert response["Location"] == "/offer/login/"
    # The login page must render for them instead of bouncing back (no redirect loop).
    assert client.get(reverse("offer_login")).status_code == 200


def test_registration_rejects_duplicate_company_email(make_offer, client):
    existing = make_offer("owner")
    response = client.post(
        reverse("offer_register"),
        {
            "username": "newbie",
            "email": "newbie@example.com",
            "password1": "pw-12345-xyz-long",
            "password2": "pw-12345-xyz-long",
            "company_name": "X",
            "company_email": existing.company_email,
            "detail": "",
        },
    )
    assert response.status_code == 200
    assert Offer.objects.count() == 1


def test_report_request_is_a_post_that_queues_a_report_and_keeps_the_job(
    make_offer, make_job, client, monkeypatch
):
    queued: list[int] = []
    monkeypatch.setattr(views.get_report, "delay", queued.append)
    offer = make_offer("owner")
    job = make_job(offer)
    client.force_login(offer.user)
    url = reverse("offer_job_report", args=[job.pk])

    assert client.get(url).status_code == 405  # a link click must not queue anything
    assert queued == []

    assert client.post(url).status_code == 302
    assert queued == [job.pk]
    assert Job.objects.filter(pk=job.pk).exists()


def test_duplicate_job_name_is_a_form_error_not_a_crash(make_offer, make_job, client):
    offer = make_offer("owner")
    make_job(offer, "Designer")
    other = make_job(offer, "Writer")
    client.force_login(offer.user)

    created = client.post(
        reverse("offer_jobs"), {"job_name": "Designer", "detail": "d"}
    )
    renamed = client.post(
        reverse("offer_job_edit", args=[other.pk]),
        {"job_name": "Designer", "detail": "d"},
    )

    assert created.status_code == 200
    assert renamed.status_code == 302
    assert Job.objects.filter(offer=offer, job_name="Designer").count() == 1
    other.refresh_from_db()
    assert other.job_name == "Writer"


def test_tasks_use_the_projects_celery_app_and_run_inline_without_a_broker():
    from requester_handler.tasks import get_report  # noqa: PLC0415

    assert get_report.app.main == "requester"
    assert get_report.app.conf.task_always_eager is True


def test_offer_company_email_is_unique_ignoring_case(make_offer):
    first = make_offer("acme")
    user = User.objects.create_user("other", "other@example.com", "pw-12345-xyz")
    with pytest.raises(IntegrityError), transaction.atomic():
        Offer.objects.create(
            user=user, company_name="Other", company_email=first.company_email.upper()
        )


def test_default_ordering_of_offers_tags_and_jobs(make_offer, make_job):
    zed, abe = make_offer("zed"), make_offer("abe")
    assert list(Offer.objects.all()) == [abe, zed]

    Tag.objects.create(name="python")
    Tag.objects.create(name="django")
    assert [t.name for t in Tag.objects.all()] == ["django", "python"]

    older = make_job(abe, "older")
    newer = make_job(abe, "newer")
    assert list(Job.objects.all()) == [newer, older]


def test_old_query_string_modes_are_gone(make_offer, make_job, client, monkeypatch):
    queued: list[int] = []
    monkeypatch.setattr(views.get_report, "delay", queued.append)
    offer = make_offer("owner")
    job = make_job(offer)
    client.force_login(offer.user)
    url = reverse("offer_job", args=[job.pk])

    for query in ("?edit=true", "?report=true", ""):
        assert (
            client.post(url + query, {"job_name": "x", "detail": "x"}).status_code
            == 405
        )

    job.refresh_from_db()
    assert job.job_name != "x"
    assert queued == []


def test_edit_and_delete_are_post_only_and_owner_scoped(
    two_employers, make_offer, client
):
    job, _, _ = two_employers
    owner = job.offer
    client.force_login(owner.user)
    assert client.get(reverse("offer_job_edit", args=[job.pk])).status_code == 405

    intruder = make_offer("intruder2")
    client.force_login(intruder.user)
    response = client.post(reverse("offer_job_delete", args=[job.pk]))
    assert response.status_code == 302
    assert Job.objects.filter(pk=job.pk).exists()
