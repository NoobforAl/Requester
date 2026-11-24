"""Candidates: the job-seeker side of the platform (profiles, search, alerts).

What it is
    Everything a candidate sees under ``/candidates/``: the job list with filters, a
    0-100 match score, saved postings, the profile, applying and withdrawing, and
    job alerts (saved searches e-mailed as a digest).

How it works
    models.py      ``Candidate`` (one-to-one with ``User``), ``SavedPosting``,
                   ``JobAlert``, ``JobSearch`` (a recorded search, for analytics).
    views.py       the portal pages; built on ``requester.portal`` (login, register,
                   access mixin shared with the employer side).
    form.py        login, registration, resume upload, profile, alert and job-filter
                   forms.
    matching.py    ``match_score``: explainable score from skills, work mode, salary.
    job_cache.py   caches the job list (search results and rendered cards). Card keys
                   include ``posting.updated_at``, which ``employers.signals`` keeps
                   moving, so edits show up without explicit invalidation.
    alerts.py      picks the new postings for an alert and e-mails the digest; called
                   by ``applications.tasks.send_job_alerts``.
    search_log.py  records searches, ``top_searches`` summary, nightly purge.
    tasks.py       ``purge_old_searches`` (beat, 02:15).
    urls.py        mounted at ``candidates/`` in requester/urls.py.
    management/    ``top_searches`` command.
    admin.py       Unfold admin.

Depends on (this app imports)
    employers.models                          models.py and everything that reads
                                              postings
    applications.models, applications.tasks   form.py and views.py (apply, withdraw,
                                              resume summaries)
    requester.portal, requester.forms, requester.unfold_admin
    Django cache (Redis in the stack) for job_cache.py; Celery, structlog.

Used by (imports this app)
    applications        models.py (FK to ``Candidate``), tasks.py (``alerts``), commands
    analytics.signals   tombstones for ``Candidate`` and ``JobSearch``
    requester.admin, tests/

Dependency direction
    ``candidates.models`` imports only ``employers.models``. ``applications.models``
    imports ``candidates.models``, so the models chain is
    employers <- candidates <- applications. Views and forms may reach "up" into
    ``applications``; models must not (see applications/__init__.py).
"""
