"""Language support: complete catalogs, text direction, switching, calendars."""

import re
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import polib
import pytest
from django.conf import settings
from django.template import Context, Template
from django.urls import reverse
from django.utils import translation
from django.utils.translation import to_locale

from requester.localdates import format_day, month_starts

pytestmark = pytest.mark.django_db

LANGUAGE_CODES = [code for code, _name in settings.LANGUAGES]
RTL_LANGUAGES = {"fa", "ar"}
PLACEHOLDER = re.compile(r"%\(\w+\)[sd]")
SOURCE_LOCALE_DIR = Path(settings.BASE_DIR) / "locale"


def po_path(code: str, root: Path = SOURCE_LOCALE_DIR) -> Path:
    return root / to_locale(code) / "LC_MESSAGES" / "django.po"


@pytest.fixture(scope="session")
def compiled_locales(tmp_path_factory) -> Path:
    """The .po files compiled to .mo in a temp folder (no GNU gettext needed)."""
    root = tmp_path_factory.mktemp("locale")
    for code in LANGUAGE_CODES:
        target = po_path(code, root)
        target.parent.mkdir(parents=True)
        shutil.copy(po_path(code), target)
        polib.pofile(str(target)).save_as_mofile(str(target.with_suffix(".mo")))
    return root


@pytest.fixture
def translated(settings, compiled_locales):
    settings.LOCALE_PATHS = [compiled_locales]


def test_seven_languages_with_persian_as_default():
    assert settings.LANGUAGE_CODE == "fa"
    assert LANGUAGE_CODES == ["fa", "en", "ar", "de", "fr", "ru", "zh-hans"]


@pytest.mark.parametrize("code", LANGUAGE_CODES)
def test_catalog_is_complete_and_keeps_placeholders(code):
    catalog = polib.pofile(str(po_path(code)))
    assert len(catalog) > 250
    assert not catalog.fuzzy_entries()
    assert not catalog.untranslated_entries()

    plural_forms = re.search(r"nplurals=(\d+)", catalog.metadata["Plural-Forms"])
    assert plural_forms
    for entry in catalog:
        if entry.msgid_plural:
            assert len(entry.msgstr_plural) == int(plural_forms.group(1)), entry.msgid
            assert all(entry.msgstr_plural.values()), entry.msgid
            continue
        assert entry.msgstr.strip(), entry.msgid
        assert set(PLACEHOLDER.findall(entry.msgid)) == set(
            PLACEHOLDER.findall(entry.msgstr)
        ), (code, entry.msgid)


def test_catalogs_cover_the_same_messages():
    reference = {e.msgid for e in polib.pofile(str(po_path("en")))}
    for code in LANGUAGE_CODES:
        assert {e.msgid for e in polib.pofile(str(po_path(code)))} == reference, code


@pytest.mark.parametrize("code", LANGUAGE_CODES)
def test_switching_language_sets_text_and_direction(client, translated, code):
    response = client.post(reverse("set_language"), {"language": code, "next": "/"})
    assert response.status_code == 302
    assert client.cookies[settings.LANGUAGE_COOKIE_NAME].value == code

    home = client.get("/")
    assert home.status_code == 200
    html = home.content.decode()
    direction = "rtl" if code in RTL_LANGUAGES else "ltr"
    assert f'<html lang="{code}" dir="{direction}">' in html

    heading = polib.pofile(str(po_path(code))).find("I am looking for a job")
    assert heading is not None
    assert heading.msgstr in html
    # The switcher lists every language, each in its own name.
    for language_code, name in settings.LANGUAGES:
        assert f'value="{language_code}"' in html
        assert name in html


def test_switcher_cannot_redirect_to_another_site(client):
    response = client.post(
        reverse("set_language"), {"language": "de", "next": "https://evil.example/"}
    )
    assert response["Location"] == "/"


def test_browser_language_is_used_until_the_visitor_chooses(client):
    html = client.get("/", headers={"accept-language": "ru"}).content.decode()
    assert '<html lang="ru" dir="ltr">' in html
    html = client.get("/", headers={"accept-language": "xx"}).content.decode()
    assert '<html lang="fa" dir="rtl">' in html  # unknown -> project default


def test_portal_pages_render_in_every_language(client, make_candidate, translated):
    candidate = make_candidate("sara")
    for code in LANGUAGE_CODES:
        client.post(reverse("set_language"), {"language": code, "next": "/"})
        assert client.get(reverse("employer_login")).status_code == 200
        assert client.get(reverse("candidate_register")).status_code == 200
        client.force_login(candidate.user)
        for name in ("candidate_dashboard", "candidate_jobs", "candidate_alerts"):
            assert client.get(reverse(name)).status_code == 200, (code, name)
        client.logout()


def test_enum_labels_follow_the_active_language(translated):
    from applications.models import Application  # noqa: PLC0415

    with translation.override("de"):
        assert str(Application.Status.WITHDRAWN.label) == "Zurückgezogen"
    with translation.override("zh-hans"):
        assert str(Application.Status.WITHDRAWN.label) == "已撤回"
    with translation.override("fa"):
        assert str(Application.Status.ACCEPTED.label) == "پذیرفته شده"


def test_persian_uses_the_jalali_calendar_and_others_the_gregorian():
    day = date(2024, 3, 20)  # 1 Farvardin 1403
    assert format_day(day, "fa") == "1403-01-01"
    assert format_day(day, "en") == "2024-03-20"
    assert format_day(day, "zh-hans") == "2024-03-20"

    this_month, last_month = month_starts(date(2024, 5, 10), "en")
    assert (this_month, last_month) == (date(2024, 5, 1), date(2024, 4, 1))
    this_month, last_month = month_starts(date(2024, 5, 10), "fa")
    assert (this_month, last_month) == (date(2024, 4, 20), date(2024, 3, 20))


@pytest.mark.parametrize(
    ("code", "expected"), [("fa", "1403-01-01"), ("de", "2024-03-20")]
)
def test_localdate_template_filter(code, expected):
    template = Template("{% load filters %}{{ value|localdate }}")
    moment = datetime(2024, 3, 20, 12, 0, tzinfo=UTC)
    with translation.override(code):
        assert template.render(Context({"value": moment})) == expected
