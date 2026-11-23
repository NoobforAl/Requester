from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.db import IntegrityError, models, transaction
from django.urls import reverse
from django.utils import timezone

from applications.models import Application
from candidates.alerts import alert_from_token, send_alerts, unsubscribe_token
from candidates.matching import match_score
from candidates.models import Candidate, JobAlert, SavedPosting
from conftest import PDF_BYTES, make_pdf
from employers.models import JobPosting, Skill

pytestmark = pytest.mark.django_db


@pytest.fixture
def signed_in_candidate(make_candidate, client):
    candidate = make_candidate("sara")
    client.force_login(candidate.user)
    return candidate


@pytest.fixture
def posting(make_employer, make_posting):
    return make_posting(make_employer("acme"))


def apply(client, posting, **files):
    return client.post(
        reverse("candidate_job", args=[posting.pk]),
        {"cover_letter": "hello", **files},
    )


def test_valid_pdf_is_stored_under_a_generated_name(
    signed_in_candidate, posting, client
):
    response = apply(client, posting, resume=make_pdf("../../evil name.pdf"))

    assert response.status_code == 302
    application = Application.objects.get()
    assert application.candidate == signed_in_candidate
    name = application.resume.name or ""
    assert name.startswith(f"resumes/{posting.pk}__")
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
def test_bad_uploads_are_rejected(signed_in_candidate, posting, client, name, content):
    apply(client, posting, resume=make_pdf(name, content))
    assert Application.objects.count() == 0


def test_uppercase_pdf_extension_is_accepted(signed_in_candidate, posting, client):
    apply(client, posting, resume=make_pdf("CV.PDF"))
    assert Application.objects.count() == 1


def test_second_application_for_same_posting_is_refused(
    signed_in_candidate, posting, client
):
    apply(client, posting, resume=make_pdf())
    apply(client, posting, resume=make_pdf())
    assert Application.objects.count() == 1


def test_cannot_apply_to_a_closed_posting(
    signed_in_candidate, make_employer, make_posting, client
):
    employer = make_employer("acme")
    closed = make_posting(employer, "closed", is_active=False)
    expired = make_posting(
        employer, "expired", deadline=timezone.localdate() - timedelta(days=1)
    )

    apply(client, closed, resume=make_pdf())
    apply(client, expired, resume=make_pdf())

    assert Application.objects.count() == 0


def test_dashboard_counts_each_status(
    signed_in_candidate, make_employer, make_posting, make_application, client
):
    employer = make_employer("acme")
    statuses = ["pending", "in_review", "accepted", "accepted", "rejected", "withdrawn"]
    for index, status in enumerate(statuses):
        make_application(
            signed_in_candidate, make_posting(employer, f"job {index}"), status
        )

    response = client.get(reverse("candidate_dashboard"))

    assert response.status_code == 200
    assert response.context["total"] == 6
    assert response.context["accepted"] == 2
    assert response.context["rejected"] == 1
    assert response.context["in_progress"] == 2


def test_job_list_only_shows_open_postings_and_pages_render(
    signed_in_candidate, make_employer, make_posting, client
):
    employer = make_employer("acme")
    live = make_posting(employer, "live")
    make_posting(employer, "closed", is_active=False)

    listing = client.get(reverse("candidate_jobs"))
    assert listing.status_code == 200
    assert list(listing.context["postings"]) == [live]
    assert client.get(reverse("candidate_job", args=[live.pk])).status_code == 200
    assert client.get(reverse("candidate_job", args=[9999])).status_code == 302
    for name in ("candidate_settings", "candidate_saved", "candidate_applications"):
        assert client.get(reverse(name)).status_code == 200


def test_job_list_filters_and_sorting(
    signed_in_candidate, make_employer, make_posting, client
):
    employer = make_employer("acme")
    remote = make_posting(employer, "remote one", work_mode="remote", salary_max=50)
    onsite = make_posting(employer, "onsite one", location="Berlin", salary_max=500)

    def titles(**params):
        response = client.get(reverse("candidate_jobs"), params)
        assert response.status_code == 200
        return [p.title for p in response.context["postings"]]

    assert titles(remote_only="on") == ["remote one"]
    assert titles(location="berlin") == ["onsite one"]
    assert titles(q="one", sort="salary") == ["onsite one", "remote one"]
    assert titles(q="one", sort="newest") == ["onsite one", "remote one"]
    assert titles(min_salary="100") == ["onsite one"]
    assert titles(work_mode="bogus") == ["onsite one", "remote one"]  # invalid: ignored
    assert {remote.title, onsite.title} == set(titles())


def test_save_and_unsave_a_posting(signed_in_candidate, posting, client):
    url = reverse("candidate_job_save", args=[posting.pk])

    assert client.get(url).status_code == 405
    client.post(url)
    assert SavedPosting.objects.filter(
        candidate=signed_in_candidate, posting=posting
    ).exists()
    assert posting.title in client.get(reverse("candidate_saved")).content.decode()

    response = client.post(url, {"next": "candidate_saved"})
    assert response["Location"] == reverse("candidate_saved")
    assert not SavedPosting.objects.exists()


def test_saving_a_posting_deleted_meanwhile_is_not_a_server_error(
    signed_in_candidate, posting, client, monkeypatch
):
    # The posting is deleted after the view looked it up, so the insert fails on
    # the foreign key. SQLite defers FK checks to the commit (never reached in a
    # test transaction), so the MariaDB error is simulated.
    def deleted_meanwhile(**_kwargs):
        raise IntegrityError("foreign key constraint fails")

    monkeypatch.setattr(SavedPosting.objects, "get_or_create", deleted_meanwhile)
    response = client.post(reverse("candidate_job_save", args=[posting.pk]))

    assert response.status_code == 302
    assert response["Location"] == reverse("candidate_jobs")


def test_save_ignores_an_external_next_url(signed_in_candidate, posting, client):
    response = client.post(
        reverse("candidate_job_save", args=[posting.pk]),
        {"next": "https://evil.example/"},
    )
    assert response["Location"] == reverse("candidate_job", args=[posting.pk])


def test_withdraw_an_application_is_logged_and_scoped(
    signed_in_candidate, make_candidate, posting, make_application, client
):
    application = make_application(signed_in_candidate, posting)
    other = make_candidate("mallory")
    url = reverse("candidate_application_withdraw", args=[application.pk])

    assert client.get(url).status_code == 405
    client.force_login(other.user)
    client.post(url)
    application.refresh_from_db()
    assert application.status == "pending"

    client.force_login(signed_in_candidate.user)
    client.post(url)
    application.refresh_from_db()
    assert application.status == "withdrawn"
    assert application.events.get().to_status == "withdrawn"
    # A withdrawn application cannot be withdrawn again, and the timeline renders.
    client.post(url)
    assert application.events.count() == 1
    page = client.get(reverse("candidate_job", args=[posting.pk]))
    assert page.status_code == 200


def test_logout_requires_post(signed_in_candidate, client):
    assert client.get(reverse("candidate_logout")).status_code == 405
    assert client.post(reverse("candidate_logout")).status_code == 302
    assert client.get(reverse("candidate_dashboard")).status_code == 302


def test_registration_rejects_duplicate_email(make_candidate, client):
    existing = make_candidate("sara")
    response = client.post(
        reverse("candidate_register"),
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
    assert Candidate.objects.count() == 1


def test_registration_remembers_the_visitors_language(client):
    client.post(
        reverse("candidate_register"),
        {
            "username": "hans",
            "first_name": "Hans",
            "last_name": "Meier",
            "email": "hans@example.com",
            "password1": "pw-12345-xyz-long",
            "password2": "pw-12345-xyz-long",
        },
        headers={"accept-language": "de"},
    )
    assert Candidate.objects.get().language == "de"


def test_candidate_email_is_unique_ignoring_case(make_candidate):
    first = make_candidate("sara")
    user = User.objects.create_user("other", "other@example.com", "pw-12345-xyz")
    with pytest.raises(IntegrityError), transaction.atomic():
        Candidate.objects.create(
            user=user, first_name="o", last_name="t", email=first.email.upper()
        )


def test_applications_default_to_newest_first(
    make_candidate, make_employer, make_posting, make_application
):
    candidate = make_candidate("sara")
    employer = make_employer("acme")
    first = make_application(candidate, make_posting(employer, "one"))
    second = make_application(candidate, make_posting(employer, "two"))
    assert list(Application.objects.all()) == [second, first]


def _resume_exists(application: Application) -> bool:
    return application.resume.storage.exists(application.resume.name or "")


def test_resume_file_is_removed_when_the_application_is_deleted(
    make_candidate,
    make_employer,
    make_posting,
    make_application,
    django_capture_on_commit_callbacks,
):
    application = make_application(
        make_candidate("sara"), make_posting(make_employer("acme"))
    )
    assert _resume_exists(application)

    with django_capture_on_commit_callbacks(execute=True):
        application.delete()

    assert not application.resume.storage.exists(application.resume.name or "")


def test_resume_file_is_removed_when_the_posting_is_deleted(
    make_candidate,
    make_employer,
    make_posting,
    make_application,
    django_capture_on_commit_callbacks,
):
    posting = make_posting(make_employer("acme"))
    application = make_application(make_candidate("sara"), posting)
    name = application.resume.name

    with django_capture_on_commit_callbacks(execute=True):
        posting.delete()  # cascades to the application

    assert not application.resume.storage.exists(name)


def test_failed_insert_does_not_leave_a_resume_file(
    signed_in_candidate, posting, client, monkeypatch
):
    resume_field = Application._meta.get_field("resume")
    assert isinstance(resume_field, models.FileField)
    storage = resume_field.storage
    before = set(storage.listdir("resumes")[1]) if storage.exists("resumes") else set()

    def boom(self, *args, **kwargs):
        # let the FileField write the file (pre_save), then fail the INSERT
        self._meta.get_field("resume").pre_save(self, True)
        raise IntegrityError("simulated race")

    monkeypatch.setattr(Application, "save", boom)
    response = apply(client, posting, resume=make_pdf())

    assert response.status_code == 302
    assert Application.objects.count() == 0
    after = set(storage.listdir("resumes")[1]) if storage.exists("resumes") else set()
    assert after == before


def test_settings_update_keeps_the_user_row_in_sync_and_saves_the_profile(
    make_candidate, client
):
    candidate = make_candidate("sara")
    skill = Skill.objects.create(name="Python")
    client.force_login(candidate.user)

    response = client.post(
        reverse("candidate_settings"),
        {
            "first_name": "Sarah",
            "last_name": "New",
            "email": "sarah.new@example.com",
            "headline": "Backend developer",
            "city": "Tehran",
            "skills": [skill.pk],
            "experience_years": "4",
            "expected_salary": "1000",
            "expected_salary_currency": "USD",
            "preferred_work_mode": "remote",
            "language": "fr",
            "is_open_to_work": "on",
        },
    )

    assert response.status_code == 302
    candidate.refresh_from_db()
    candidate.user.refresh_from_db()
    assert candidate.email == candidate.user.email == "sarah.new@example.com"
    assert (candidate.user.first_name, candidate.user.last_name) == ("Sarah", "New")
    assert list(candidate.skills.all()) == [skill]
    assert (candidate.experience_years, candidate.language) == (4, "fr")
    assert candidate.profile_completeness > 0


@pytest.mark.parametrize(
    "overrides",
    [{"date_of_birth": "2999-01-01"}, {"phone_number": "call me"}],
    ids=["future-birth-date", "bad-phone"],
)
def test_profile_validators(make_candidate, client, overrides):
    candidate = make_candidate("sara")
    client.force_login(candidate.user)
    data = {
        "first_name": "S",
        "last_name": "T",
        "email": candidate.email,
        "language": "fa",
        "expected_salary_currency": "IRR",
        **overrides,
    }
    response = client.post(reverse("candidate_settings"), data)
    assert response.status_code == 200


def test_match_score_explains_itself(make_candidate, make_employer, make_posting):
    python, sql, go = (Skill.objects.create(name=n) for n in ("Python", "SQL", "Go"))
    candidate = make_candidate(
        "sara",
        preferred_work_mode="remote",
        expected_salary=100,
        expected_salary_currency="USD",
    )
    candidate.skills.set([python, sql])
    employer = make_employer("acme")

    perfect = make_posting(
        employer, "perfect", work_mode="remote", salary_max=150, salary_currency="USD"
    )
    perfect.skills.set([python, sql])
    partial = make_posting(
        employer, "partial", work_mode="onsite", salary_max=50, salary_currency="USD"
    )
    partial.skills.set([python, go])
    bare = make_posting(employer, "bare")

    assert match_score(candidate, perfect) == 100
    assert match_score(candidate, partial) == 30  # half the skills, mode and pay miss
    assert match_score(candidate, bare) == 40  # neutral skills, no mode match, no pay


def test_alert_form_creates_and_manages_alerts(signed_in_candidate, client):
    python = Skill.objects.create(name="Python")
    response = client.post(
        reverse("candidate_alerts"),
        {
            "name": "Remote python",
            "keywords": "developer",
            "work_mode": "remote",
            "skills": [python.pk],
            "frequency": "daily",
        },
    )
    assert response.status_code == 302
    alert = JobAlert.objects.get()
    assert alert.candidate == signed_in_candidate

    client.post(reverse("candidate_alert_toggle", args=[alert.pk]))
    alert.refresh_from_db()
    assert not alert.is_active
    assert client.get(reverse("candidate_alerts")).status_code == 200

    client.post(reverse("candidate_alert_delete", args=[alert.pk]))
    assert not JobAlert.objects.exists()


def test_job_alert_digest_only_lists_new_matching_postings(
    make_candidate, make_employer, make_posting
):
    candidate = make_candidate("sara", language="de")
    employer = make_employer("acme")
    alert = JobAlert.objects.create(
        candidate=candidate, name="Remote", work_mode="remote", frequency="daily"
    )
    JobAlert.objects.filter(pk=alert.pk).update(
        created_at=timezone.now() - timedelta(days=2)
    )
    make_posting(employer, "On-site job")
    match = make_posting(employer, "Remote job", work_mode="remote")
    make_posting(employer, "Closed remote", work_mode="remote", is_active=False)

    assert send_alerts("weekly") == 0  # other frequency
    assert send_alerts("daily") == 1
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == [candidate.email]
    assert match.title in message.body
    assert "On-site job" not in message.body
    assert "Closed remote" not in message.body
    assert "/candidates/alerts/unsubscribe/" in message.body

    assert send_alerts("daily") == 0  # nothing new since the last digest
    assert len(mail.outbox) == 1


def test_unsubscribe_link_needs_a_post_and_a_valid_signature(make_candidate, client):
    alert = JobAlert.objects.create(candidate=make_candidate("sara"), name="x")
    token = unsubscribe_token(alert)
    url = reverse("candidate_alert_unsubscribe", args=[token])

    assert alert_from_token(token) == alert
    assert alert_from_token(token + "tampered") is None

    assert client.get(url).status_code == 200  # confirmation page only
    alert.refresh_from_db()
    assert alert.is_active

    assert client.post(url).status_code == 200
    assert not JobAlert.objects.get(pk=alert.pk).is_active

    bad = reverse("candidate_alert_unsubscribe", args=["nonsense"])
    assert client.get(bad).status_code == 404
    assert client.post(bad).status_code == 404


def test_candidate_cannot_touch_another_candidates_alert(
    signed_in_candidate, make_candidate, client
):
    alert = JobAlert.objects.create(candidate=make_candidate("mallory"), name="x")

    client.post(reverse("candidate_alert_toggle", args=[alert.pk]))
    client.post(reverse("candidate_alert_delete", args=[alert.pk]))

    alert.refresh_from_db()
    assert alert.is_active


def test_open_postings_queryset_is_what_alerts_search(
    make_candidate, make_employer, make_posting
):
    employer = make_employer("acme")
    make_posting(employer, "open")
    make_posting(employer, "closed", is_active=False)
    alert = JobAlert.objects.create(candidate=make_candidate("sara"), name="all")
    assert [p.title for p in alert.matching_postings()] == ["open"]
    assert JobPosting.objects.count() == 2
