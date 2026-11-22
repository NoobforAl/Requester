"""Requester project."""

# Load the Celery app with Django so `.delay()` uses our broker settings.
from .celery import app as celery_app

__all__ = ("celery_app",)
