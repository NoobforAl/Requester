"""Applications: a candidate applies to a posting; status history; background work.

What it is
    The link between the two sides of the platform. An ``Application`` ties one
    candidate to one posting, carries a PDF resume and a status, and every status
    change leaves an ``ApplicationEvent`` (who, from, to, note). The Celery tasks
    that touch applications or send e-mail live here too.

How it works
    models.py    ``Application`` (rules for allowed status changes, ``change_status``)
                 and ``ApplicationEvent`` (the timeline).
    signals.py   ``post_delete`` removes the stored resume file once the row is gone
                 (cascades included); connected from ``ApplicationsConfig.ready()``.
    tasks.py     Celery: ``summarize_application`` (resume text via pdfplumber, then
                 ai.py), ``send_posting_report`` (PDF via WeasyPrint),
                 ``notify_status_change`` (e-mail the candidate), ``send_job_alerts``
                 (daily and weekly digests, beat at 04:30).
    ai.py        AI resume summaries through OpenRouter (httpx); skipped silently
                 without ``OPENROUTER_API_KEY``.
    fake_data.py Faker data generator behind ``seed_fake_data`` and tests/factories.
    management/  seed_demo_data, seed_fake_data, import_legacy_data, ensure_superuser.
    admin.py     Unfold admin (status labels, filters).

Depends on (this app imports)
    candidates.models, employers.models   models.py, fake_data.py, commands, tasks.py
    candidates.alerts                     tasks.py (``send_job_alerts`` builds digests)
    requester.unfold_admin                admin.py
    pdfplumber, WeasyPrint, httpx, Celery, structlog.

Used by (imports this app)
    candidates.form, candidates.views   Application model, ``summarize_application``
    employers.views                     Application model, report and status tasks
    analytics.signals                   tombstones for Application and its events
    requester.admin                     sidebar badge (pending applications)
    tests/                              factories, fixtures, perf and benchmark data

Dependency direction
    employers.models <- candidates.models <- applications.models. Models only import
    "down" this chain, never views, forms or tasks, so the apps may import each
    other's views and tasks without a cycle. Keep it that way: a model module that
    imports ``candidates.views`` or ``applications.tasks`` would create one.
"""
