import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError

from requester_handler import tasks

pytestmark = pytest.mark.django_db


def test_report_base_url_points_at_a_folder_that_holds_the_font():
    url = tasks.report_base_url()
    folder = Path(url2pathname(unquote(urlparse(url).path)))

    assert url.endswith("/")
    assert (folder / "fonts" / "Vazirmatn-variable.woff2").is_file()


def test_report_pdf_is_built_with_the_font_and_emailed(
    make_offer, make_job, make_worker, make_application, monkeypatch
):
    seen: dict[str, str | None] = {}

    class FakeHTML:
        def __init__(self, string: str, base_url: str | None = None):
            seen["html"], seen["base_url"] = string, base_url

        def write_pdf(self) -> bytes:
            return b"%PDF-fake"

    # The real WeasyPrint needs Pango, which CI machines may not have.
    monkeypatch.setitem(sys.modules, "weasyprint", SimpleNamespace(HTML=FakeHTML))
    offer = make_offer("acme")
    job = make_job(offer)
    make_application(make_worker("sara"), job)

    tasks.get_report(job.pk)

    assert 'url("fonts/Vazirmatn-variable.woff2")' in str(seen["html"])
    assert seen["base_url"] == tasks.report_base_url()
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [offer.company_email]
    assert mail.outbox[0].attachments[0][1] == b"%PDF-fake"


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


@pytest.mark.parametrize("command", ["insert_offers", "insert_workers"])
def test_demo_accounts_are_refused_when_debug_is_off(command, settings):
    settings.DEBUG = False

    with pytest.raises(CommandError):
        call_command(command)
    assert not User.objects.exists()


@pytest.mark.parametrize("command", ["insert_offers", "insert_workers"])
def test_demo_accounts_are_created_when_debug_is_on(command, settings):
    settings.DEBUG = True

    call_command(command)
    assert User.objects.exists()
