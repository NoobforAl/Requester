"""Every admin page renders with the Unfold theme, its filters and columns."""

import pytest
from django.contrib import admin
from django.contrib.auth.models import User
from django.urls import reverse

from applications.models import Application
from candidates.models import JobSearch
from conftest import make_pdf
from employers.models import Skill

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_client(client):
    client.force_login(User.objects.create_superuser("root", "root@example.com", "pw"))
    return client


@pytest.fixture
def some_data(make_employer, make_candidate, make_posting):
    posting = make_posting(make_employer("acme"), deadline="2000-01-01")
    posting.skills.add(Skill.objects.create(name="Go"))
    candidate = make_candidate("sara", is_open_to_work=False)
    application = Application.objects.create(
        candidate=candidate, posting=posting, resume=make_pdf()
    )
    application.change_status(Application.Status.ACCEPTED)
    JobSearch.objects.create(query="go", results=0)
    return application


def admin_url(model, view: str, *args) -> str:
    meta = model._meta
    return reverse(f"admin:{meta.app_label}_{meta.model_name}_{view}", args=args)


def test_every_changelist_renders(staff_client, some_data):
    for model in admin.site._registry:
        response = staff_client.get(admin_url(model, "changelist"))
        assert response.status_code == 200, model


def test_filters_and_change_pages_render(staff_client, some_data):
    posting = some_data.posting
    pages = [
        admin_url(Application, "changelist") + "?status=accepted",
        admin_url(type(posting), "changelist")
        + "?created_at_from_0=2000-01-01&created_at_from_1=00:00:00&salary_max_from=0",
        admin_url(Application, "change", some_data.pk),
        admin_url(type(posting), "change", posting.pk),
        admin_url(type(posting), "add"),
        admin_url(User, "change", some_data.candidate.user.pk),
        reverse("admin:index"),
    ]
    for url in pages:
        response = staff_client.get(url)
        assert response.status_code == 200, url


def test_labels_show_status_and_state(staff_client, some_data):
    jobs = staff_client.get(admin_url(type(some_data.posting), "changelist"))
    assert "Past deadline" in jobs.content.decode()
    applications = staff_client.get(admin_url(Application, "changelist"))
    assert some_data.get_status_display() in applications.content.decode()


def test_job_searches_are_read_only(staff_client, some_data):
    url = admin_url(JobSearch, "add")
    assert staff_client.get(url).status_code == 403
