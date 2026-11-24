"""Analytics bookkeeping: delete tombstones so deletions reach Elasticsearch.

What it is
    Logstash copies new and changed MariaDB rows into Elasticsearch every minute
    (docs/analytics.md). A query cannot see a row that no longer exists, so this app
    records every delete of a copied row in ``DeletedRow``; Logstash turns each
    tombstone into a delete in the index.

How it works
    models.py   ``DeletedRow`` (index name, row id, deleted_at).
    signals.py  ``post_delete`` receivers for the models in ``INDEX_OF`` (postings,
                applications, application events, candidates, job searches), cascade
                deletes included. Connected from ``AnalyticsConfig.ready()``
                (apps.py), never at import time of this package.
    tasks.py    ``purge_deleted_rows``: nightly Celery beat task (02:30) that drops
                tombstones older than ``DELETED_ROW_RETENTION_DAYS``.

Depends on (this app imports)
    employers.models, candidates.models, applications.models   signals.py only,
        to know which models to watch.
    Django, Celery, structlog; the setting ``DELETED_ROW_RETENTION_DAYS``.

Used by (imports this app)
    Nothing in Python: it is a leaf. It is listed in INSTALLED_APPS and its task in
    CELERY_BEAT_SCHEDULE (requester/settings.py); the Logstash pipelines read its
    table through SQL.

Rules
    * Adding a model to Elasticsearch means adding it to ``INDEX_OF`` and to a
      Logstash pipeline, or its deletions are never mirrored.
    * Keep this file free of imports: Django loads it before the app registry is
      ready, so importing models here raises ``AppRegistryNotReady``.
"""
