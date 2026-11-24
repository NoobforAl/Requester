"""Management commands of the applications app: data set-up and migration chores.

Run as ``cd src && python manage.py <name>`` (``make`` wraps most of them).

    seed_demo_data      small hand-written demo set; refused unless DEBUG is on
                        (``make seed``). Demo accounts use the password
                        ``password123``.
    seed_fake_data      lots of Faker data, ``fake_*`` users, ``--seed`` and
                        ``--wipe-fake`` (``make seed-fake``). Uses ``fake_data.py``.
    import_legacy_data  copies rows of the old ``offer_*``/``worker_*`` tables into
                        the renamed apps; idempotent (runs after ``migrate``).
    ensure_superuser    creates the admin from ``DJANGO_SUPERUSER_*`` if missing;
                        never resets an existing password (Docker start-up).

Depends on: candidates.models, employers.models, applications.models and
applications.fake_data. They live in this app, not in ``employers``/``candidates``,
because they need all three apps' models and ``applications`` is the last link in
the model dependency chain (see applications/__init__.py).
"""
