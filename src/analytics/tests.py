from datetime import timedelta

import pytest
from django.utils import timezone

from analytics.models import DeletedRow
from analytics.tasks import purge_deleted_rows
from applications.models import Application
from candidates.models import JobSearch
from conftest import make_pdf

pytestmark = pytest.mark.django_db


def tombstones():
    return sorted(DeletedRow.objects.values_list("index", "row_id"))


def test_deleting_a_posting_leaves_tombstones_for_it_and_its_cascade(
    make_employer, make_candidate, make_posting
):
    posting = make_posting(make_employer("acme"))
    application = Application.objects.create(
        candidate=make_candidate("sara"), posting=posting, resume=make_pdf()
    )
    event = application.change_status(Application.Status.IN_REVIEW)
    ids = posting.pk, application.pk, event.pk

    posting.delete()

    assert tombstones() == sorted(
        [
            ("requester-postings", ids[0]),
            ("requester-applications", ids[1]),
            ("requester-application-events", ids[2]),
        ]
    )


def test_deleting_a_user_cascades_to_the_candidate_tombstone(make_candidate):
    candidate = make_candidate("sara")
    candidate.user.delete()
    assert tombstones() == [("requester-candidates", candidate.pk)]


def test_purged_searches_leave_tombstones():
    search = JobSearch.objects.create(query="go", results=0)
    JobSearch.objects.all().delete()
    assert tombstones() == [("requester-searches", search.pk)]


def test_old_tombstones_are_purged(settings):
    settings.DELETED_ROW_RETENTION_DAYS = 7
    old = DeletedRow.objects.create(index="requester-postings", row_id=1)
    DeletedRow.objects.filter(pk=old.pk).update(
        deleted_at=timezone.now() - timedelta(days=8)
    )
    DeletedRow.objects.create(index="requester-postings", row_id=2)

    assert purge_deleted_rows() == 1
    assert tombstones() == [("requester-postings", 2)]
