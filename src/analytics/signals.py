"""Leave a ``DeletedRow`` for every deleted row that has a copy in Elasticsearch.

``post_delete`` also fires for rows removed by a cascade (deleting a user deletes
its candidate or employer, their postings, applications...), so those leave
tombstones too. Deletes with raw SQL or ``QuerySet.update`` are not seen.
"""

from typing import Any

from django.db import models
from django.db.models.signals import post_delete

from applications.models import Application, ApplicationEvent
from candidates.models import Candidate, JobSearch
from employers.models import JobPosting

from .models import DeletedRow

#: Model -> the Elasticsearch index its rows are copied to (analytics/logstash).
INDEX_OF: dict[type[models.Model], str] = {
    JobPosting: "requester-postings",
    Application: "requester-applications",
    ApplicationEvent: "requester-application-events",
    Candidate: "requester-candidates",
    JobSearch: "requester-searches",
}


def record_deletion(sender: type[models.Model], instance: models.Model, **_: Any):
    DeletedRow.objects.create(index=INDEX_OF[sender], row_id=instance.pk)


for _model in INDEX_OF:
    post_delete.connect(
        record_deletion, sender=_model, dispatch_uid=f"analytics-{_model.__name__}"
    )
