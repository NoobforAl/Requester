"""Recorded job searches (statistics) and the cached search results."""

from datetime import timedelta
from io import StringIO

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.db import DatabaseError, connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from candidates import job_cache, search_log
from candidates.models import JobSearch
from candidates.tasks import purge_old_searches
from employers.models import Skill

pytestmark = pytest.mark.django_db


@pytest.fixture
def signed_in(make_candidate, client):
    candidate = make_candidate("sara")
    client.force_login(candidate.user)
    return candidate


@pytest.fixture
def employer(make_employer):
    return make_employer("acme")


def jobs(client, headers=None, **params):
    response = client.get(reverse("candidate_jobs"), params, headers=headers)
    assert response.status_code == 200
    return response


# ---------------------------------------------------------------- search log
def test_a_search_is_recorded_normalized_with_its_filters(
    signed_in, employer, make_posting, client
):
    python = Skill.objects.create(name="Python")
    posting = make_posting(employer, "Python developer", location="Berlin")
    posting.skills.add(python)

    jobs(
        client,
        q="  PYTHON   Developer ",
        location=" Berlin",
        skills=[python.pk],
        work_mode="onsite",
        min_salary="10",
        headers={"accept-language": "de"},
    )

    search = JobSearch.objects.get()
    assert search.query == "python developer"
    assert search.location == "berlin"
    assert search.work_mode == "onsite"
    assert search.min_salary == 10
    assert list(search.skills.all()) == [python]
    assert search.results == 0  # no salary on the posting, so min_salary excludes it


def test_the_result_count_is_the_total_not_the_page(
    signed_in, employer, make_posting, client
):
    for n in range(8):  # more than one page (6 per page)
        make_posting(employer, f"Go developer {n}")
    jobs(client, q="go")
    assert JobSearch.objects.get().results == 8


@pytest.mark.parametrize(
    "params",
    [
        {},  # just opening the list
        {"sort": "salary"},  # sorting alone is not a search
        {"q": "go", "page": "2"},  # paging through the same search
        {"q": "go", "min_salary": "-5"},  # invalid form: filters are ignored
    ],
)
def test_not_a_new_search_is_not_recorded(signed_in, client, params):
    jobs(client, **params)
    assert not JobSearch.objects.exists()


def test_a_database_error_does_not_break_the_job_list(signed_in, client, monkeypatch):
    def broken(**_kwargs):
        raise DatabaseError("table is locked")

    monkeypatch.setattr(JobSearch.objects, "create", broken)
    jobs(client, q="go")  # still 200


def test_top_searches_command(signed_in, employer, make_posting, client):
    make_posting(employer, "Python developer", location="Berlin")
    for _ in range(3):
        jobs(client, q="python", location="berlin")
    jobs(client, q="cobol")

    out = StringIO()
    call_command("top_searches", "--days", "7", stdout=out)
    text = out.getvalue()

    assert "4 searches in the last 7 days." in text
    words = text.split("Searches with no results")[0]
    assert words.index("python") < words.index("cobol")  # most searched first
    assert "     3  python" in words
    no_results = text.split("Searches with no results")[1].split("Most searched")[0]
    assert "cobol" in no_results
    assert "python" not in no_results
    assert "     3  berlin" in text


def test_old_searches_are_purged(settings):
    settings.SEARCH_LOG_RETENTION_DAYS = 30
    old = JobSearch.objects.create(query="old", results=1)
    JobSearch.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(days=31)
    )
    recent = JobSearch.objects.create(query="recent", results=1)
    recent.skills.add(Skill.objects.create(name="Go"))

    assert purge_old_searches() == 1
    assert list(JobSearch.objects.values_list("query", flat=True)) == ["recent"]


def test_normalize():
    assert search_log.normalize("  Senior\tPython  DEV ") == "senior python dev"


# ---------------------------------------------------------------- result cache
@pytest.fixture
def search_cache(settings):
    settings.JOB_SEARCH_CACHE_SECONDS = 60
    cache.clear()
    yield
    cache.clear()


def titles(response):
    return [p.title for p in response.context["postings"]]


def test_a_cached_search_skips_the_search_queries(
    search_cache, signed_in, employer, make_posting, client
):
    for n in range(8):
        make_posting(employer, f"Go developer {n}")

    with CaptureQueriesContext(connection) as uncached:
        first = jobs(client, q="go", page="2")
    with CaptureQueriesContext(connection) as cached:
        second = jobs(client, q="go", page="2")

    # The second time there is no COUNT and no text search, only the rows by id.
    assert titles(second) == titles(first)
    assert len(titles(second)) == 2
    assert second.context["postings"].paginator.num_pages == 2
    assert len(cached) < len(uncached)
    assert not any("COUNT(" in q["sql"] for q in cached.captured_queries)


def test_cached_results_never_show_a_closed_or_changed_posting(
    search_cache, signed_in, employer, make_posting, client
):
    keep = make_posting(employer, "Go developer A")
    close = make_posting(employer, "Go developer B")
    assert set(titles(jobs(client, q="go"))) == {keep.title, close.title}

    close.is_active = False
    close.save()
    keep.title = "Go developer A (renamed)"
    keep.save()

    assert titles(jobs(client, q="go")) == ["Go developer A (renamed)"]


def test_different_filters_are_different_cache_entries(
    search_cache, signed_in, employer, make_posting, client
):
    make_posting(employer, "Remote Go", work_mode="remote")
    make_posting(employer, "Office Go", work_mode="onsite")

    assert len(titles(jobs(client, q="go"))) == 2
    assert titles(jobs(client, q="go", work_mode="remote")) == ["Remote Go"]
    assert titles(jobs(client, q="go", work_mode="onsite")) == ["Office Go"]


def test_a_new_posting_shows_up_once_the_cache_entry_expires(
    search_cache, settings, signed_in, employer, make_posting, client
):
    make_posting(employer, "Go developer A")
    assert len(titles(jobs(client, q="go"))) == 1
    make_posting(employer, "Go developer B")
    assert len(titles(jobs(client, q="go"))) == 1  # cached: up to 60 s late

    cache.clear()  # what the expiry does
    assert len(titles(jobs(client, q="go"))) == 2


def test_match_and_saved_state_stay_per_user_on_a_cached_page(
    search_cache, signed_in, make_candidate, employer, make_posting, client
):
    posting = make_posting(employer, "Go developer")
    client.post(reverse("candidate_job_save", args=[posting.pk]))
    assert jobs(client, q="go").context["postings"][0].is_saved

    other = make_candidate("omid")
    client.force_login(other.user)
    page = jobs(client, q="go")  # a cache hit now
    assert not page.context["postings"][0].is_saved


# ------------------------------------------------------------------ job cards
@pytest.fixture
def clean_cache():
    cache.clear()
    yield
    cache.clear()


def card_html(client, **params) -> str:
    return jobs(client, **params).content.decode()


def test_job_cards_come_from_the_cache_the_second_time(
    clean_cache, signed_in, employer, make_posting, client, monkeypatch
):
    make_posting(employer, "Go developer")
    first = jobs(client).context["postings"][0].card_body
    assert "Go developer" in first

    renders = []
    real = job_cache.render_to_string

    def counting(*args, **kwargs):
        renders.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(job_cache, "render_to_string", counting)
    assert jobs(client).context["postings"][0].card_body == first
    assert renders == []  # served from the cache


@pytest.mark.usefixtures("clean_cache", "signed_in")
@pytest.mark.parametrize(
    "change",
    ["title", "employer name", "skill added", "skill renamed", "skill deleted"],
)
def test_a_card_is_never_stale_after_an_edit(employer, make_posting, client, change):
    posting = make_posting(employer, "Go developer")
    go = Skill.objects.create(name="Golang")
    posting.skills.add(go)
    assert "Golang" in card_html(client)

    if change == "title":
        posting.title = "Rust developer"
        posting.save()
        expected, gone = "Rust developer", "Go developer"
    elif change == "employer name":
        employer.name = "Globex"
        employer.save()
        expected, gone = "Globex", None
    elif change == "skill added":
        posting.skills.add(Skill.objects.create(name="Kubernetes"))
        expected, gone = "Kubernetes", None
    elif change == "skill renamed":
        go.name = "Go (language)"
        go.save()
        expected, gone = "Go (language)", "Golang"
    else:
        go.delete()
        expected, gone = "Go developer", "Golang"

    html = card_html(client)
    assert expected in html
    if gone:
        assert gone not in html


@pytest.mark.usefixtures("clean_cache", "signed_in")
def test_cards_are_cached_per_language(employer, make_posting, client):
    make_posting(employer, "Go developer", work_mode="onsite")
    for _ in range(2):  # the second round is served from the cache
        assert "On-site" in card_html(client, headers={"accept-language": "en"})
        german = card_html(client, headers={"accept-language": "de"})
        assert "Vor Ort" in german
        assert "On-site" not in german
