"""Candidate-side background jobs."""

import structlog
from celery import shared_task
from django.conf import settings

from .search_log import purge_old_searches as _purge

logger = structlog.get_logger(__name__)


@shared_task
def purge_old_searches() -> int:
    """Nightly: delete recorded job searches past ``SEARCH_LOG_RETENTION_DAYS``."""
    deleted = _purge(settings.SEARCH_LOG_RETENTION_DAYS)
    logger.info("job_searches_purged", deleted=deleted)
    return deleted
