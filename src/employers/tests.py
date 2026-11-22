from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from applications.models import Application
from employers import views
from employers.models import Employer, JobPosting, Skill

pytestmark = pytest.mark.django_db


def posting_form(**overrides) -> dict:
    return {
        "title": "Designer",
        "description": "d",
        "work_mode": "onsite",
        "employment_type": "full_time",
        "salary_currency": "IRR",
        **overrides,
    }


@pytest.fixture
def two_employers(
    make_employer, make_posting, make_candidate, make_application, client
):
    """Employer A owns a posting with one application; employer B is signed in."""
    owner = make_employer("owner")
    intruder = make_employer("intruder")
    posting = make_posting(owner)
    application = make_application(make_candidate("sara"), posting)
    client.force_login(intruder.user)
    return posting, application, intruder


def test_employer_cannot_open_or_change_another_employers_posting(
    two_employers, client
):
    posting, _, _ = two_employers
    url = reverse("employer_job", args=[posting.pk])

    assert client.get(url).status_code == 302
    client.post(
        reverse("employer_job_edit", args=[posting.pk]), posting_form(title="hacked")
    )
    client.post(reverse("employer_job_toggle", args=[posting.pk]))
    client.post(reverse("employer_job_delete", args=[posting.pk]))
    client.post(reverse("employer_job_report", args=[posting.pk]))

    posting.refresh_from_db()
    assert posting.title != "hacked"
    assert posting.is_active


def test_employer_cannot_download_another_employers_resume(two_employers, client):
    _, application, _ = two_employers
    response = client.get(reverse("employer_resume", args=[application.pk]))
    assert response.status_code == 302


def test_employer_cannot_change_status_of_another_employers_application(
    two_employers, client
):
    _, application, _ = two_employers
    client.post(
        reverse("employer_application_status", args=[application.pk]),
        {"status": "accepted"},
    )
    application.refresh_from_db()
    assert application.status == "pending"


def test_owner_can_change_status_log_it_and_download_resume(
    make_employer, make_posting, make_candidate, make_application, client, mailoutbox
):
    owner = make_employer("owner")
    application = make_application(make_candidate("sara"), make_posting(owner))
    client.force_login(owner.user)

    client.post(
        reverse("employer_application_status", args=[application.pk]),
        {"status": "accepted", "note": "welcome"},
    )
    application.refresh_from_db()
    assert application.status == "accepted"
    event = application.events.get()
    assert (event.from_status, event.to_status) == ("pending", "accepted")
    assert event.actor == owner.user
    assert event.note == "welcome"
    assert [m.to for m in mailoutbox] == [[application.candidate.email]]

    response = client.get(reverse("employer_resume", args=[application.pk]))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert b"".join(response.streaming_content).startswith(b"%PDF-")


@pytest.mark.parametrize(
    ("current", "wanted", "allowed"),
    [
        ("pending", "in_review", True),
        ("pending", "withdrawn", False),
        ("rejected", "accepted", False),
        ("withdrawn", "in_review", False),
        ("accepted", "pending", False),
    ],
)
def test_status_transitions_follow_the_rules(
    make_employer,
    make_posting,
    make_candidate,
    make_application,
    client,
    current,
    wanted,
    allowed,
):
    owner = make_employer("owner")
    application = make_application(
        make_candidate("sara"), make_posting(owner), status=current
    )
    client.force_login(owner.user)

    client.post(
        reverse("employer_application_status", args=[application.pk]),
        {"status": wanted},
    )

    application.refresh_from_db()
    assert application.status == (wanted if allowed else current)
    assert application.events.count() == (1 if allowed else 0)


def test_invalid_status_is_rejected(
    make_employer, make_posting, make_candidate, make_application, client
):
    owner = make_employer("owner")
    application = make_application(make_candidate("sara"), make_posting(owner))
    client.force_login(owner.user)

    client.post(
        reverse("employer_application_status", args=[application.pk]),
        {"status": "hired!!"},
    )
    application.refresh_from_db()
    assert application.status == Application.Status.PENDING


def test_settings_update_changes_the_existing_employer(make_employer, client):
    employer = make_employer("owner")
    client.force_login(employer.user)

    response = client.post(
        reverse("employer_settings"),
        {
            "name": "New name",
            "contact_email": employer.contact_email,
            "description": "new description",
            "website": "https://example.com",
            "industry": "Software",
            "size": "11-50",
            "city": "Tehran",
            "language": "de",
        },
    )

    assert response.status_code == 302
    assert Employer.objects.count() == 1
    employer.refresh_from_db()
    assert (employer.name, employer.language, employer.size) == (
        "New name",
        "de",
        "11-50",
    )


def test_posting_create_edit_delete_flow(make_employer, client):
    employer = make_employer("owner")
    client.force_login(employer.user)
    skill = Skill.objects.create(name="Python")

    client.post(
        reverse("employer_jobs"),
        posting_form(
            location="Tehran",
            salary_min="100",
            salary_max="200",
            deadline=(timezone.localdate() + timedelta(days=5)).isoformat(),
            skills=[skill.pk],
        ),
    )
    posting = JobPosting.objects.get(title="Designer")
    assert posting.employer == employer
    assert posting.location == "Tehran"
    assert list(posting.skills.all()) == [skill]
    assert posting.is_open

    client.post(
        reverse("employer_job_edit", args=[posting.pk]),
        posting_form(title="Lead designer"),
    )
    posting.refresh_from_db()
    assert posting.title == "Lead designer"

    delete_url = reverse("employer_job_delete", args=[posting.pk])
    assert client.get(delete_url).status_code == 405
    assert JobPosting.objects.filter(pk=posting.pk).exists()
    assert client.post(delete_url).status_code == 302
    assert not JobPosting.objects.filter(pk=posting.pk).exists()


def test_salary_range_must_be_ordered(make_employer, client):
    client.force_login(make_employer("owner").user)

    response = client.post(
        reverse("employer_jobs"), posting_form(salary_min="500", salary_max="100")
    )

    assert response.status_code == 200
    assert not JobPosting.objects.exists()


def test_closing_and_reopening_a_posting(make_employer, make_posting, client):
    owner = make_employer("owner")
    posting = make_posting(owner)
    client.force_login(owner.user)
    url = reverse("employer_job_toggle", args=[posting.pk])

    assert client.get(url).status_code == 405
    client.post(url)
    posting.refresh_from_db()
    assert not posting.is_active
    assert not JobPosting.objects.open().filter(pk=posting.pk).exists()

    client.post(url)
    posting.refresh_from_db()
    assert posting.is_active


def test_past_deadline_closes_a_posting(make_employer, make_posting):
    employer = make_employer("owner")
    expired = make_posting(
        employer, "old", deadline=timezone.localdate() - timedelta(days=1)
    )
    live = make_posting(employer, "new", deadline=timezone.localdate())

    assert not expired.is_open
    assert live.is_open
    assert list(JobPosting.objects.open()) == [live]


def test_dashboard_and_pages_render(
    make_employer, make_posting, make_candidate, make_application, client
):
    employer = make_employer("owner")
    posting = make_posting(employer)
    make_application(make_candidate("sara"), posting)
    client.force_login(employer.user)

    for name in ("employer_dashboard", "employer_jobs", "employer_settings"):
        assert client.get(reverse(name)).status_code == 200
    assert client.get(reverse("employer_job", args=[posting.pk])).status_code == 200
    filtered = client.get(
        reverse("employer_job", args=[posting.pk]), {"status": "pending"}
    )
    assert filtered.status_code == 200


def test_logout_requires_post(make_employer, client):
    employer = make_employer("owner")
    client.force_login(employer.user)

    assert client.get(reverse("employer_logout")).status_code == 405
    assert client.get(reverse("employer_dashboard")).status_code == 200

    assert client.post(reverse("employer_logout")).status_code == 302
    assert client.get(reverse("employer_dashboard")).status_code == 302


def test_candidate_account_cannot_use_the_employer_portal(make_candidate, client):
    candidate = make_candidate("sara")
    client.force_login(candidate.user)

    response = client.get(reverse("employer_dashboard"))
    assert response.status_code == 302
    assert response["Location"] == reverse("employer_login")
    # The login page must render for them instead of bouncing back (no redirect loop).
    assert client.get(reverse("employer_login")).status_code == 200


def test_registration_rejects_duplicate_company_email(make_employer, client):
    existing = make_employer("owner")
    response = client.post(
        reverse("employer_register"),
        {
            "username": "newbie",
            "email": "newbie@example.com",
            "password1": "pw-12345-xyz-long",
            "password2": "pw-12345-xyz-long",
            "name": "X",
            "contact_email": existing.contact_email,
            "description": "",
        },
    )
    assert response.status_code == 200
    assert Employer.objects.count() == 1


def test_report_request_is_a_post_that_queues_a_report_and_keeps_the_posting(
    make_employer, make_posting, client, monkeypatch
):
    queued: list[int] = []
    monkeypatch.setattr(views.send_posting_report, "delay", queued.append)
    employer = make_employer("owner")
    posting = make_posting(employer)
    client.force_login(employer.user)
    url = reverse("employer_job_report", args=[posting.pk])

    assert client.get(url).status_code == 405  # a link click must not queue anything
    assert queued == []

    assert client.post(url).status_code == 302
    assert queued == [posting.pk]
    assert JobPosting.objects.filter(pk=posting.pk).exists()


def test_duplicate_title_is_a_form_error_not_a_crash(
    make_employer, make_posting, client
):
    employer = make_employer("owner")
    make_posting(employer, "Designer")
    other = make_posting(employer, "Writer")
    client.force_login(employer.user)

    created = client.post(reverse("employer_jobs"), posting_form())
    renamed = client.post(reverse("employer_job_edit", args=[other.pk]), posting_form())

    assert created.status_code == 200
    assert renamed.status_code == 302
    assert JobPosting.objects.filter(employer=employer, title="Designer").count() == 1
    other.refresh_from_db()
    assert other.title == "Writer"


def test_tasks_use_the_projects_celery_app_and_run_inline_without_a_broker():
    from applications.tasks import send_posting_report  # noqa: PLC0415

    assert send_posting_report.app.main == "requester"
    assert send_posting_report.app.conf.task_always_eager is True


def test_employer_contact_email_is_unique_ignoring_case(make_employer):
    first = make_employer("acme")
    user = User.objects.create_user("other", "other@example.com", "pw-12345-xyz")
    with pytest.raises(IntegrityError), transaction.atomic():
        Employer.objects.create(
            user=user, name="Other", contact_email=first.contact_email.upper()
        )


def test_salary_check_constraint_is_enforced_by_the_database(
    make_employer, make_posting
):
    employer = make_employer("acme")
    with pytest.raises(IntegrityError), transaction.atomic():
        make_posting(employer, salary_min=10, salary_max=5)


def test_default_ordering_of_employers_skills_and_postings(make_employer, make_posting):
    zed, abe = make_employer("zed"), make_employer("abe")
    assert list(Employer.objects.all()) == [abe, zed]

    Skill.objects.create(name="python")
    Skill.objects.create(name="django")
    assert [s.name for s in Skill.objects.all()] == ["django", "python"]

    older = make_posting(abe, "older")
    newer = make_posting(abe, "newer")
    assert list(JobPosting.objects.all()) == [newer, older]


def test_old_urls_redirect_to_the_new_ones(client):
    response = client.get("/worker/jobs/3/")
    assert response.status_code == 301
    assert response["Location"] == "/candidates/jobs/3/"
    assert client.get("/offer/login/")["Location"] == "/employers/login/"


def test_search_filters_postings(make_employer, make_posting):
    employer = make_employer("acme", city="Tehran")
    python = Skill.objects.create(name="Python")
    cheap = make_posting(
        employer, "Cheap remote", work_mode="remote", salary_min=10, salary_max=20
    )
    rich = make_posting(
        employer,
        "Rich onsite",
        work_mode="onsite",
        location="Berlin",
        employment_type="contract",
        seniority="senior",
        salary_min=100,
        salary_max=200,
    )
    rich.skills.add(python)

    search = JobPosting.objects.search
    assert set(search("")) == {cheap, rich}
    assert list(search("rich")) == [rich]
    assert list(search("", location="berl")) == [rich]
    assert list(search("", remote_only=True)) == [cheap]
    assert list(search("", employment_type="contract")) == [rich]
    assert list(search("", seniority="senior")) == [rich]
    assert list(search("", min_salary=150)) == [rich]
    assert list(search("", skills=[python])) == [rich]
    assert list(search("acme")) and set(search("acme")) == {cheap, rich}
