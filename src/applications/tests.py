import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

import httpx
import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection

from applications import ai, tasks
from applications.models import Application
from candidates.models import Candidate
from employers.models import Employer, JobPosting, Skill

pytestmark = pytest.mark.django_db


# --------------------------------------------------------------------- reports


def test_report_base_url_points_at_a_folder_that_holds_the_font():
    url = tasks.report_base_url()
    folder = Path(url2pathname(unquote(urlparse(url).path)))

    assert url.endswith("/")
    assert (folder / "fonts" / "Vazirmatn-variable.woff2").is_file()


def test_report_pdf_is_built_with_the_font_and_emailed_in_the_employer_language(
    make_employer, make_posting, make_candidate, make_application, monkeypatch
):
    seen: dict[str, str | None] = {}

    class FakeHTML:
        def __init__(self, string: str, base_url: str | None = None):
            seen["html"], seen["base_url"] = string, base_url

        def write_pdf(self) -> bytes:
            return b"%PDF-fake"

    # The real WeasyPrint needs Pango, which CI machines may not have.
    monkeypatch.setitem(sys.modules, "weasyprint", SimpleNamespace(HTML=FakeHTML))
    employer = make_employer("acme", language="de")
    posting = make_posting(employer)
    make_application(make_candidate("sara"), posting)

    tasks.send_posting_report(posting.pk)

    html = str(seen["html"])
    assert 'url("fonts/Vazirmatn-variable.woff2")' in html
    assert '<html lang="de" dir="ltr">' in html
    assert seen["base_url"] == tasks.report_base_url()
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [employer.contact_email]
    assert mail.outbox[0].attachments[0][1] == b"%PDF-fake"


def test_report_for_a_persian_employer_is_right_to_left(
    make_employer, make_posting, monkeypatch
):
    seen: dict[str, str] = {}

    class FakeHTML:
        def __init__(self, string: str, base_url: str | None = None):
            seen["html"] = string

        def write_pdf(self) -> bytes:
            return b"%PDF-fake"

    monkeypatch.setitem(sys.modules, "weasyprint", SimpleNamespace(HTML=FakeHTML))
    posting = make_posting(make_employer("acme", language="fa"))

    tasks.send_posting_report(posting.pk)

    assert '<html lang="fa" dir="rtl">' in seen["html"]


# -------------------------------------------------------------------------- AI


class FakeResponse:
    def __init__(self, status_code: int = 200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


@pytest.fixture
def no_ai(settings):
    settings.OPENROUTER_API_KEY = ""


@pytest.mark.parametrize(("key", "expected"), [("", ""), ("sk-x", "openrouter")])
def test_ai_is_on_only_with_an_openrouter_key(settings, key, expected):
    settings.OPENROUTER_API_KEY = key
    assert ai.active_provider() == expected


def test_openrouter_request_has_key_model_language_and_truncated_text(
    settings, monkeypatch
):
    settings.OPENROUTER_API_KEY = "sk-test-123"
    settings.OPENROUTER_MODEL = "some/model"
    settings.AI_MAX_INPUT_CHARS = 10
    seen: dict = {}

    def fake_post(url, **kwargs):
        seen["url"] = url
        seen.update(kwargs)
        return FakeResponse(
            payload={"choices": [{"message": {"content": "  a summary \n"}}]}
        )

    monkeypatch.setattr(ai.httpx, "post", fake_post)

    summary, provider = ai.summarize("x" * 100, language="de")

    assert (summary, provider) == ("a summary", "openrouter")
    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer sk-test-123"
    assert seen["json"]["model"] == "some/model"
    system, user = seen["json"]["messages"]
    assert "German" in system["content"]
    assert user["content"] == "x" * 10


@pytest.mark.parametrize(
    ("status", "error"),
    [(429, ai.RetryableAIError), (503, ai.RetryableAIError), (401, ai.AIError)],
)
def test_openrouter_errors_are_classified(settings, monkeypatch, status, error):
    settings.OPENROUTER_API_KEY = "sk-test-123"
    monkeypatch.setattr(ai.httpx, "post", lambda *a, **k: FakeResponse(status))

    with pytest.raises(error) as caught:
        ai.summarize("cv")
    assert "sk-test-123" not in str(caught.value)
    assert caught.type is error


def test_unexpected_provider_answer_is_an_error(settings, monkeypatch):
    settings.OPENROUTER_API_KEY = "sk-test-123"
    monkeypatch.setattr(
        ai.httpx, "post", lambda *a, **k: FakeResponse(payload={"oops": 1})
    )
    with pytest.raises(ai.AIError):
        ai.summarize("cv")


def test_summarize_without_a_provider_raises(no_ai):
    with pytest.raises(ai.AIError):
        ai.summarize("cv")


def test_summary_task_stores_summary_and_provider(
    settings,
    make_employer,
    make_posting,
    make_candidate,
    make_application,
    monkeypatch,
):
    settings.OPENROUTER_API_KEY = "sk-test-123"
    application = make_application(
        make_candidate("sara"), make_posting(make_employer("acme", language="fr"))
    )
    monkeypatch.setattr(tasks, "pdf_to_markdown", lambda path: "resume text")
    seen: dict = {}

    def fake_summarize(text, language="en"):
        seen.update(text=text, language=language)
        return "great candidate", "openrouter"

    monkeypatch.setattr(tasks.ai, "summarize", fake_summarize)

    tasks.summarize_application(application.pk)

    application.refresh_from_db()
    assert application.ai_summary == "great candidate"
    assert application.ai_provider == "openrouter"
    assert seen == {"text": "resume text", "language": "fr"}


def test_summary_task_does_nothing_without_a_provider(
    no_ai, make_employer, make_posting, make_candidate, make_application, monkeypatch
):
    application = make_application(
        make_candidate("sara"), make_posting(make_employer("acme"))
    )

    def boom(path):
        raise AssertionError("must not read the resume")

    monkeypatch.setattr(tasks, "pdf_to_markdown", boom)
    tasks.summarize_application(application.pk)
    application.refresh_from_db()
    assert application.ai_summary == ""


def test_summary_task_retries_rate_limits_but_drops_hard_failures(
    settings,
    make_employer,
    make_posting,
    make_candidate,
    make_application,
    monkeypatch,
):
    settings.OPENROUTER_API_KEY = "sk-test-123"
    application = make_application(
        make_candidate("sara"), make_posting(make_employer("acme"))
    )
    monkeypatch.setattr(tasks, "pdf_to_markdown", lambda path: "resume text")

    def limited(text, language="en"):
        raise ai.RetryableAIError("429")

    monkeypatch.setattr(tasks.ai, "summarize", limited)
    with pytest.raises(ai.RetryableAIError):
        tasks.summarize_application.run(application.pk)

    def refused(text, language="en"):
        raise ai.AIError("401")

    monkeypatch.setattr(tasks.ai, "summarize", refused)
    tasks.summarize_application.run(application.pk)  # logged, not raised
    application.refresh_from_db()
    assert application.ai_summary == ""
    # Set by @shared_task(autoretry_for=...) at runtime; not in the Task stubs.
    task = tasks.summarize_application
    assert httpx.TransportError in task.autoretry_for  # type: ignore[attr-defined]


# ------------------------------------------------------------------ app logic


def test_status_change_email_goes_to_the_candidate_in_their_language(
    make_employer, make_posting, make_candidate, make_application
):
    candidate = make_candidate("sara", language="de")
    application = make_application(candidate, make_posting(make_employer("acme")))
    application.change_status("accepted")

    tasks.notify_status_change(application.pk)

    assert [m.to for m in mail.outbox] == [[candidate.email]]
    assert "acme" in mail.outbox[0].body


def test_withdrawn_is_final_for_employers():
    allowed = Application.EMPLOYER_TRANSITIONS
    assert allowed["withdrawn"] == frozenset()
    assert set(allowed) == set(Application.Status.values)


# --------------------------------------------------------------------- admin


def test_ensure_superuser_needs_a_password_and_never_resets_one(monkeypatch):
    monkeypatch.delenv("DJANGO_SUPERUSER_PASSWORD", raising=False)
    call_command("ensure_superuser")
    assert not User.objects.exists()

    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "first-pass-123")
    call_command("ensure_superuser")
    admin = User.objects.get(username="admin")
    assert admin.is_superuser and admin.check_password("first-pass-123")

    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "second-pass-456")
    call_command("ensure_superuser")
    admin.refresh_from_db()
    assert admin.check_password("first-pass-123")


def test_demo_data_is_refused_when_debug_is_off(settings):
    settings.DEBUG = False

    with pytest.raises(CommandError):
        call_command("seed_demo_data")
    assert not User.objects.exists()


def test_demo_data_is_created_once_when_debug_is_on(settings):
    settings.DEBUG = True

    call_command("seed_demo_data")
    counts = (
        Employer.objects.count(),
        JobPosting.objects.count(),
        Candidate.objects.count(),
        Application.objects.count(),
    )
    assert all(counts)

    call_command("seed_demo_data")  # idempotent
    assert counts == (
        Employer.objects.count(),
        JobPosting.objects.count(),
        Candidate.objects.count(),
        Application.objects.count(),
    )
    assert JobPosting.objects.filter(work_mode="remote").exists()
    assert Skill.objects.exists()


# -------------------------------------------------------------- legacy import

LEGACY_SCHEMA = [
    "CREATE TABLE offer_offer (id integer PRIMARY KEY, user_id integer, "
    "company_name varchar(30), company_email varchar(254), detail text, "
    "created_at datetime, updated_at datetime)",
    "CREATE TABLE offer_tag (id integer PRIMARY KEY, name varchar(50), "
    "created_at datetime, updated_at datetime)",
    "CREATE TABLE offer_job (id integer PRIMARY KEY, job_name varchar(100), "
    "detail text, offer_id integer, created_at datetime, updated_at datetime)",
    "CREATE TABLE offer_job_tags (id integer PRIMARY KEY, job_id integer, "
    "tag_id integer)",
    "CREATE TABLE worker_worker (id integer PRIMARY KEY, user_id integer, "
    "first_name varchar(30), last_name varchar(30), email varchar(254), "
    "phone_number varchar(15), address text, date_of_birth date, "
    "created_at datetime, updated_at datetime)",
    "CREATE TABLE worker_jobrequest (id integer PRIMARY KEY, worker_id integer, "
    "job_id integer, resume varchar(100), cover_letter text, status varchar(20), "
    "ai_summary text, applied_at datetime, updated_at datetime)",
]


@pytest.fixture
def legacy_tables():
    boss = User.objects.create_user("boss", "boss@example.com", "pw-12345-xyz")
    sara = User.objects.create_user("sara", "sara@example.com", "pw-12345-xyz")
    stamp = "2024-03-01 10:30:00"
    with connection.cursor() as cursor:
        for statement in LEGACY_SCHEMA:
            cursor.execute(statement)
        cursor.execute(
            "INSERT INTO offer_offer VALUES (7, %s, 'Acme', 'hr@acme.example', "
            "'About', %s, %s)",
            [boss.pk, stamp, stamp],
        )
        cursor.execute(
            "INSERT INTO offer_tag VALUES (3, 'python', %s, %s)", [stamp, stamp]
        )
        cursor.execute(
            "INSERT INTO offer_job VALUES (5, 'Developer', 'Build', 7, %s, %s)",
            [stamp, stamp],
        )
        cursor.execute("INSERT INTO offer_job_tags VALUES (1, 5, 3)")
        cursor.execute(
            "INSERT INTO worker_worker VALUES (9, %s, 'Sara', 'T', 'sara@example.com', "
            "'', '', '1990-01-02', %s, %s)",
            [sara.pk, stamp, stamp],
        )
        cursor.execute(
            "INSERT INTO worker_jobrequest VALUES (11, 9, 5, 'resumes/5__abc.pdf', "
            "'hi', 'accepted', 'summary', %s, %s)",
            [stamp, stamp],
        )


def test_legacy_data_is_copied_into_the_renamed_apps(legacy_tables):
    call_command("import_legacy_data")

    employer = Employer.objects.get(pk=7)
    assert (employer.name, employer.contact_email) == ("Acme", "hr@acme.example")
    assert employer.created_at.year == 2024
    posting = JobPosting.objects.get(pk=5)
    assert (posting.title, posting.employer_id) == ("Developer", 7)
    assert [s.name for s in posting.skills.all()] == ["python"]
    candidate = Candidate.objects.get(pk=9)
    assert str(candidate.date_of_birth) == "1990-01-02"
    application = Application.objects.get(pk=11)
    assert (application.candidate_id, application.posting_id) == (9, 5)
    assert (application.status, application.ai_summary) == ("accepted", "summary")
    assert application.resume.name == "resumes/5__abc.pdf"
    assert application.applied_at.year == 2024


def test_legacy_import_is_idempotent_and_a_noop_on_a_fresh_database(legacy_tables):
    call_command("import_legacy_data")
    call_command("import_legacy_data")
    assert Employer.objects.count() == 1
    assert JobPosting.skills.through.objects.count() == 1


def test_legacy_import_without_old_tables_does_nothing():
    call_command("import_legacy_data")
    assert not Employer.objects.exists()
