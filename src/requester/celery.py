import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "requester.settings")

app = Celery("requester")

app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()
