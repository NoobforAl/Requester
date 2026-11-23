"""Nightly cleanup of the delete tombstones Logstash has long since read."""

from datetime import timedelta

import structlog
from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import DeletedRow

logger = structlog.get_logger(__name__)


@shared_task
def purge_deleted_rows() -> int:
    cutoff = timezone.now() - timedelta(days=settings.DELETED_ROW_RETENTION_DAYS)
    deleted, _ = DeletedRow.objects.filter(deleted_at__lt=cutoff).delete()
    logger.info("deleted_rows_purged", deleted=deleted)
    return deleted
