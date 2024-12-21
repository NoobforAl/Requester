from __future__ import absolute_import, unicode_literals

from celery import Celery

import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'requester.settings')

app = Celery('requester')

app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks()
