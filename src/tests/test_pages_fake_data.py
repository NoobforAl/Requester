"""Every main page renders real-looking data from a ``seed_fake_data`` site.

The site (medium preset) is built once for this module; each test logs in as the
busiest fake candidate or employer and checks that the page shows rows from it.
"""

import math

import pytest
from django.urls import reverse
from django.utils.html import escape

from applications.models import Application
from candidates.models import JobAlert, SavedPosting
from candidates.views import JOBS_PER_PAGE
from employers.models import JobPosting, WorkMode

pytestmark = [pytest.mark.fakedata, pytest.mark.django_db]

PAGE_SIZE = 10  # saved postings, applications, employer lists


def html(response) -> str:
    assert response.status_code == 200
    return response.content.decode()


def assert_shows(content: str, *texts: str) -> None:
    for text in texts:
        assert escape(text) in content, text


@pytest.fixture
def as_candidate(client, fake_site):
    client.force_login(fake_site.candidate.user)
    return client


@pytest.fixture
def as_employer(client, fake_site):
    client.force_login(fake_site.employer.user)
    return client


def newest_open(**filters):
    return JobPosting.objects.open().filter(**filters).order_by("-created_at", "-id")


def test_fake_site_has_lived_in_accounts(fake_site):
    candidate, employer = fake_site.candidate, fake_site.employer
    assert candidate.applications.count() >= PAGE_SIZE + 1
    assert candidate.saved_postings.count() >= PAGE_SIZE + 1
    assert candidate.job_alerts.count() >= 2
    assert employer.postings.count() >= PAGE_SIZE + 1


def test_home(client, fake_site):
    html(client.get(reverse("home")))


# ------------------------------------------------------------------ candidate
def test_candidate_dashboard(as_candidate, fake_site):
    content = html(as_candidate.get(reverse("candidate_dashboard")))
    assert str(fake_site.candidate.applications.count()) in content


def test_candidate_jobs_first_page(as_candidate):
    content = html(as_candidate.get(reverse("candidate_jobs")))
    expected = list(newest_open()[:JOBS_PER_PAGE])
    assert len(expected) == JOBS_PER_PAGE
    assert_shows(content, *(p.title for p in expected))


def test_candidate_job_detail(as_candidate, fake_site):
    application = fake_site.candidate.applications.select_related(
        "posting__employer"
    ).first()
    posting = application.posting
    content = html(as_candidate.get(reverse("candidate_job", args=[posting.pk])))
    assert_shows(content, posting.title, posting.employer.name)


def test_candidate_saved(as_candidate, fake_site):
    content = html(as_candidate.get(reverse("candidate_saved")))
    newest = SavedPosting.objects.filter(candidate=fake_site.candidate)[0]
    assert_shows(content, newest.posting.title)


def test_candidate_applications(as_candidate, fake_site):
    content = html(as_candidate.get(reverse("candidate_applications")))
    newest = Application.objects.filter(candidate=fake_site.candidate).order_by(
        "-applied_at"
    )[0]
    assert_shows(content, newest.posting.title, newest.posting.employer.name)


def test_candidate_alerts(as_candidate, fake_site):
    content = html(as_candidate.get(reverse("candidate_alerts")))
    names = JobAlert.objects.filter(candidate=fake_site.candidate)
    assert_shows(content, *(alert.name for alert in names))


def test_candidate_settings(as_candidate, fake_site):
    content = html(as_candidate.get(reverse("candidate_settings")))
    assert_shows(content, fake_site.candidate.email)


@pytest.mark.parametrize("sort", ["", "newest", "salary", "deadline"])
def test_candidate_job_search_with_filters_and_sort(as_candidate, sort):
    # Filter on the most common work mode and skill so the result is not empty.
    posting = newest_open(work_mode=WorkMode.ONSITE, skills__isnull=False).first()
    skill = posting.skills.first()
    params = {
        "q": posting.title.split()[-1],
        "work_mode": WorkMode.ONSITE,
        "skills": skill.pk,
        "sort": sort,
    }
    content = html(as_candidate.get(reverse("candidate_jobs"), params))

    expected = (
        JobPosting.objects.open()
        .search(params["q"], work_mode=WorkMode.ONSITE, skills=[skill])
        .order_by("-created_at", "-id")
    )
    assert expected.exists()
    if sort in ("", "newest"):
        assert_shows(content, expected.first().title)
    else:  # another order: some match must be on the first page
        titles = [escape(p.title) for p in expected]
        assert any(title in content for title in titles)


def test_candidate_job_search_without_results(as_candidate):
    content = html(
        as_candidate.get(reverse("candidate_jobs"), {"q": "no-such-job-zzz"})
    )
    assert escape(newest_open().first().title) not in content


# ------------------------------------------------------------------- employer
def test_employer_dashboard(as_employer, fake_site):
    content = html(as_employer.get(reverse("employer_dashboard")))
    assert str(fake_site.employer.postings.count()) in content


def test_employer_jobs(as_employer, fake_site):
    content = html(as_employer.get(reverse("employer_jobs")))
    newest = fake_site.employer.postings.order_by("-created_at", "-id")[:PAGE_SIZE]
    assert_shows(content, *(p.title for p in newest))


def test_employer_job_detail(as_employer, fake_site):
    posting = (
        fake_site.employer.postings.filter(applications__isnull=False)
        .distinct()
        .first()
    )
    content = html(as_employer.get(reverse("employer_job", args=[posting.pk])))
    first = posting.applications.select_related("candidate").order_by("applied_at")[0]
    assert_shows(content, posting.title, first.candidate.email)


def test_employer_job_detail_status_filter(as_employer, fake_site):
    application = Application.objects.filter(
        posting__employer=fake_site.employer, status="rejected"
    ).select_related("candidate", "posting")[0]
    url = reverse("employer_job", args=[application.posting_id])
    content = html(as_employer.get(url, {"status": "rejected"}))
    rejected = application.posting.applications.filter(status="rejected")
    pending = application.posting.applications.filter(status="pending")
    assert_shows(content, rejected.order_by("applied_at")[0].candidate.email)
    for other in pending[:3]:
        assert escape(other.candidate.email) not in content


def test_employer_settings(as_employer, fake_site):
    content = html(as_employer.get(reverse("employer_settings")))
    assert_shows(content, fake_site.employer.name)


# ----------------------------------------------------------------- pagination
def _pages(total: int, size: int) -> int:
    return max(1, math.ceil(total / size))


def test_candidate_jobs_pagination_edges(as_candidate):
    postings = list(newest_open())
    last = _pages(len(postings), JOBS_PER_PAGE)
    url = reverse("candidate_jobs")
    last_titles = [p.title for p in postings[(last - 1) * JOBS_PER_PAGE :]]

    assert_shows(html(as_candidate.get(url, {"page": last})), *last_titles)
    # Past the end and garbage both fall back (Paginator.get_page).
    assert_shows(html(as_candidate.get(url, {"page": last + 50})), *last_titles)
    assert_shows(html(as_candidate.get(url, {"page": "abc"})), postings[0].title)
    assert_shows(html(as_candidate.get(url, {"page": 0})), *last_titles)


def test_candidate_jobs_pagination_keeps_filters(as_candidate):
    url = reverse("candidate_jobs")
    content = html(as_candidate.get(url, {"work_mode": "remote", "page": 2}))
    assert "work_mode=remote" in content
    remote = list(newest_open(work_mode="remote"))
    second = remote[JOBS_PER_PAGE : 2 * JOBS_PER_PAGE]
    assert second
    assert_shows(content, *(p.title for p in second))


@pytest.mark.parametrize(
    ("name", "rows"),
    [
        (
            "candidate_saved",
            lambda site: [
                s.posting.title
                for s in SavedPosting.objects.filter(
                    candidate=site.candidate
                ).select_related("posting")
            ],
        ),
        (
            "candidate_applications",
            lambda site: [
                a.posting.title
                for a in site.candidate.applications.select_related("posting").order_by(
                    "-applied_at"
                )
            ],
        ),
    ],
)
def test_candidate_list_last_page(as_candidate, fake_site, name, rows):
    titles = rows(fake_site)
    last = _pages(len(titles), PAGE_SIZE)
    assert last >= 2
    content = html(as_candidate.get(reverse(name), {"page": last}))
    assert_shows(content, *titles[(last - 1) * PAGE_SIZE :])


def test_employer_jobs_last_page(as_employer, fake_site):
    postings = list(fake_site.employer.postings.order_by("-created_at", "-id"))
    last = _pages(len(postings), PAGE_SIZE)
    content = html(as_employer.get(reverse("employer_jobs"), {"page": last}))
    assert_shows(content, *(p.title for p in postings[(last - 1) * PAGE_SIZE :]))
    assert escape(postings[0].title) not in content or last == 1


def test_employer_job_applicants_last_page(as_employer, fake_site):
    posting = max(
        fake_site.employer.postings.all(), key=lambda p: p.applications.count()
    )
    applications = list(
        posting.applications.select_related("candidate").order_by("applied_at")
    )
    last = _pages(len(applications), PAGE_SIZE)
    assert last >= 2
    url = reverse("employer_job", args=[posting.pk])
    content = html(as_employer.get(url, {"page": last}))
    tail = applications[(last - 1) * PAGE_SIZE :]
    assert_shows(content, *(a.candidate.email for a in tail))
    assert escape(applications[0].candidate.email) not in content
