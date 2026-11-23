"""Bookkeeping for the analytics copy in Elasticsearch (see docs/analytics.md).

Logstash copies new and changed rows from MariaDB into Elasticsearch every minute
(``analytics/logstash``). A deleted row cannot be found by such a query, so each
delete leaves a ``DeletedRow`` behind, which Logstash turns into a delete in the
index. Rows older than ``DELETED_ROW_RETENTION_DAYS`` are removed every night.
"""

from django.db import models


class DeletedRow(models.Model):
    #: Elasticsearch index the deleted row was copied to, e.g. ``requester-postings``.
    index = models.CharField(max_length=50)
    row_id = models.BigIntegerField()
    deleted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = (models.Index(fields=["deleted_at"], name="deletedrow_deleted_idx"),)

    def __str__(self):
        return f"{self.index}/{self.row_id}"
