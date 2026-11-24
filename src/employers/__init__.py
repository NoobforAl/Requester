"""Employers: the hiring side of the platform (employers, job postings, skills).

What it is
    Everything an employer sees under ``/employers/``: posting jobs, closing and
    reopening them, reviewing applications and requesting reports. It also owns the
    shared vocabulary of the whole project: ``Skill``, ``WorkMode``, ``Currency``.

How it works
    models.py    ``Employer`` (one-to-one with ``User``), ``Skill``, ``JobPosting``
                 (``JobPosting.objects.open()`` is "active and not past deadline").
                 Imports no other project app: this is the bottom of the chain.
    signals.py   moves ``JobPosting.updated_at`` when skills change, because cached
                 job cards (candidates/job_cache.py) are keyed by it; connected from
                 ``EmployersConfig.ready()``.
    views.py     the portal pages (posting CRUD, application review, resume download,
                 reports) on top of ``requester.portal``.
    form.py      login, registration, employer profile and posting forms.
    templatetags/filters.py   ``localdate`` and ``salary_label`` for templates.
    urls.py      mounted at ``employers/`` in requester/urls.py.
    admin.py     Unfold admin (labels, filters).

Depends on (this app imports)
    applications.models, applications.tasks   views.py (review, status change, reports)
    requester.portal, requester.forms, requester.localdates, requester.unfold_admin
    Django, structlog. models.py and signals.py import no other project app.

Used by (imports this app)
    candidates          models.py, form.py, matching.py, job_cache.py, search_log.py,
                        views.py
    applications        models.py (FK to ``JobPosting``), tasks.py, fake_data.py,
                        commands
    analytics.signals   tombstones for ``JobPosting``
    requester.admin, tests/

Dependency direction
    employers.models <- candidates.models <- applications.models. ``employers.models``
    must never import ``candidates`` or ``applications``: everything else depends on
    it, so a back-import is an instant circular import.
"""
