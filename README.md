# Requester

Requester is a job platform built with Django. **Candidates** find jobs, apply with a PDF resume and follow every application. **Employers** post jobs, review applications and move them through a hiring pipeline. The interface speaks **7 languages**: Persian (default), English, Arabic, German, French, Russian and Simplified Chinese.

## Contents

- [Features](#features)
- [Quick start](#quick-start)
- [Tech stack](#tech-stack)
- [Project layout](#project-layout)
- [Development](#development) · [Makefile commands](#makefile-commands)
- [Configuration](#configuration)
- [Docker: development and production](#docker-development-and-production)
- [Observability, performance and analytics](#observability-performance-and-analytics)
- [Languages](#languages) · [AI summaries](#ai-summaries) · [Admin](#admin)
- [Diagrams](#diagrams) · [Names and upgrading an old database](#names-and-upgrading-an-old-database)

## Features

**Candidates** (`/candidates/`)

- Browse open jobs with filters (city, work mode, employment type, seniority, minimum salary, skills, remote only) and sorting (newest, highest salary, closing soon).
- A **match score** (0-100) compares each job with the candidate's skills, preferred work mode and expected salary.
- Save jobs for later, apply with a PDF resume and cover letter, **withdraw** an application, and see the **status timeline** of each application.
- A full profile: headline, city, skills, experience, education, expected salary, work-mode preference, LinkedIn, language; a completeness bar on the dashboard.
- **Job alerts**: saved searches that e-mail a daily or weekly digest of new matching jobs, in the candidate's language, with a signed one-click unsubscribe link.

**Employers** (`/employers/`)

- Post jobs with location, work mode, employment type, seniority, salary range and currency, deadline and skills; close, reopen, edit or delete them.
- Review applications (search and status filter), download resumes, read an **AI summary** of each resume, and change the status with an optional note. Allowed changes follow fixed rules and every change is logged and e-mailed to the candidate.
- Request a PDF report of all applications for a job by e-mail, in the employer's language.

**Everyone**: seven languages with right-to-left support, the Jalali calendar for Persian, and a themed admin site at `/admin/`.

## Quick start

You need **Python 3.12** and **[uv](https://docs.astral.sh/uv/)**. No Docker, database or other service is required for local development: it runs on SQLite and executes background tasks inline.

```bash
uv sync        # install everything from pyproject.toml / uv.lock
make dev       # migrate, build translations, serve on http://127.0.0.1:8181
make seed      # (second terminal) demo employers, jobs, candidates, applications
```

Demo accounts use the password `password123`, for example `worker1` (candidate) and `alice` (employer). `make seed` is refused unless debug is on, and `make dev` turns debug on. Use `make seed-fake` for a lot more (Faker) data, and `make superuser` to create an admin.

Before pushing, run `make fix`: it formats, lints, type checks, checks for deprecated API, runs the tests and the Django checks.

## Tech stack

| Area | Tools |
|---|---|
| Web | Django 6.1, server-rendered templates, Jinja2 form widgets, Unfold admin, WhiteNoise, gunicorn |
| Data | MariaDB in the stack, SQLite for local development, Redis (cache and Celery broker) |
| Background work | Celery worker (`tasks`) and beat (`scheduler`): e-mails, job alerts, PDF reports, AI summaries |
| PDF | WeasyPrint (reports), pdfplumber (resume text) |
| AI | [OpenRouter](https://openrouter.ai), optional |
| Observability | structlog, Prometheus + Grafana, Loki, OpenTelemetry + Jaeger, Sentry |
| Analytics | Logstash, Elasticsearch 9, Kibana (optional overlay) |
| Quality | pytest, pytest-benchmark, ruff, flake8, djlint, bandit, vulture, mypy + django-stubs, pip-audit |
| Load testing | Locust |

## Project layout

```text
src/
  requester/       project package: settings, URLs, portal views, admin setup, forms
  employers/       employers, job postings, skills
  candidates/      candidates, saved jobs, job alerts, job search
  applications/    applications, status history, AI summaries, Celery tasks
  analytics/       delete tombstones so Logstash can mirror deletions into Elasticsearch
  observability/   logging, request IDs, metrics, tracing, Sentry
  templates/       HTML templates          static/   CSS and JS
  locale/          translations (.po)      tests/    cross-app, perf and benchmark tests
docs/              observability, log schema, analytics
monitoring/        Prometheus, Grafana, Loki, Vector, OpenTelemetry configs
loadtests/         Locust scenarios        diagram/  PlantUML sources and PNGs
scripts/           cross-platform helpers used by the Makefile
```

## Development

- **Tests** live next to the code (`tests.py`, `test_*.py`) and run with `make test`. `make test-mariadb` runs them against a real MariaDB.
- **Deprecations are errors.** `make deprecated` runs mypy's deprecated-call check, and `make test` turns every `DeprecationWarning` (Django's `RemovedInDjango*` included, whether our code or a dependency raises it) and naive-datetime warning into a failure. Fix the call, or ignore one specific message in `pyproject.toml` if a dependency cannot be fixed.
- **Benchmarks**: `make bench` saves a run under `.benchmarks/`; `make bench-check` fails if a median is 20% slower than the last run.
- **Dependencies**: `make audit` scans for known vulnerabilities (needs network).
- **Windows**: the Makefile runs under `cmd.exe` too; file chores go through `scripts/mk.py`.

### Makefile commands

Run `make help` for the full list. The ones you will use most:

| Command | What it does |
|---|---|
| `make dev` | dev server on SQLite (`PORT=8001 HOST=0.0.0.0` to change); migrates, imports legacy data, builds translations |
| `make seed` / `make seed-fake` | demo data / lots of Faker data |
| `make fix` | format, lint, type check, deprecation check, tests, Django checks |
| `make format` · `lint` · `typecheck` · `deprecated` · `test` · `check` | the individual steps of `make fix` |
| `make migrations` · `migrate` · `shell` · `superuser` | Django chores |
| `make i18n` · `i18n-compile` · `i18n-check` | translations (see [Languages](#languages)) |
| `make docker-up` · `docker-down` | the dev stack |
| `make dev-all` | dev stack + Faker data + monitoring + live load |
| `make monitoring-up` · `perf-up` · `analytics-up` | optional stacks, see below |
| `make diagrams` | redraw `diagram/*.png` (runs in Docker) |
| `make clean` · `clean-all` | remove caches / also the virtualenv and the SQLite database |

## Configuration

Settings come from environment variables. Copy `.env.example` to `.env` to set them; nothing secret is written in the compose files.

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | required when `DJANGO_DEBUG` is off |
| `DJANGO_DEBUG` | debug mode; the dev override turns it on |
| `ALLOWED_HOSTS`, `SITE_URL` | your domain, and the public address used for links in e-mails |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | MariaDB; without `DB_NAME` the app uses SQLite |
| `REDIS_PASSWORD` | Redis (cache and Celery broker) |
| `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` | AI summaries, see [AI summaries](#ai-summaries) |
| `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_PASSWORD` | create an admin on start-up |
| `LOG_LEVEL`, `LOG_FORMAT`, `APP_ENVIRONMENT`, `SENTRY_DSN`, `OTEL_*`, `METRICS_TOKEN` | observability, see [docs/observability.md](docs/observability.md) |

## Docker: development and production

Services in the stack: **MariaDB** (`db`), **Redis** (`cache`), **MailHog** (`mailhog`), the web app (`web`), a **Celery** worker (`tasks`) and beat (`scheduler`).

`docker-compose.dev.yaml` is a development override (`make docker-up` uses it): `DJANGO_DEBUG` on, the Django dev server, demo data and an admin login `admin` / `admin`. Never use it for a real deployment.

`docker compose up -d --build` with only `docker-compose.yaml` is production-like:

- `DJANGO_DEBUG` is off, so Django refuses to start unless `SECRET_KEY` is set.
- `ALLOWED_HOSTS` defaults to `localhost,127.0.0.1`; set it to your domain. Set `SITE_URL` to the public address.
- It runs gunicorn after `collectstatic`; no demo data is created.
- An admin user is created only if `DJANGO_SUPERUSER_PASSWORD` is set. An existing admin's password is never reset.
- Session and CSRF cookies are `Secure` when debug is off: serve the site over HTTPS (set `BEHIND_PROXY=true` behind a TLS proxy), or set `SECURE_COOKIES=false` for a plain-HTTP test.
- Database passwords come from `DB_PASSWORD`, `DB_ROOT_PASSWORD` and `REDIS_PASSWORD`; the defaults are for local development only.

## Observability, performance and analytics

Three optional overlays sit on top of the main stack. Each has its own guide.

| Overlay | Start | What you get | Guide |
|---|---|---|---|
| Monitoring | `make monitoring-up` (needs `METRICS_TOKEN`, `GRAFANA_ADMIN_PASSWORD`) | structured JSON logs, Prometheus metrics, Grafana dashboards, Loki, Jaeger traces, Sentry | [docs/observability.md](docs/observability.md), [docs/log-schema.md](docs/log-schema.md) |
| Performance | `make perf-up`, then `make perf-load` | a CPU/memory-capped production-like stack on `:8001`, Locust load tests, soak and benchmark runs | [loadtests/README.md](loadtests/README.md) |
| Analytics | `make analytics-up` | a copy of the business data in Elasticsearch 9 for the data team, with a ready Kibana dashboard | [docs/analytics.md](docs/analytics.md) |

`make dev-all` starts the dev stack with monitoring and live traffic in one command (Grafana on `:3000`, Jaeger on `:16686`). **Never run the load tests against production.**

The app itself does not use Elasticsearch. Logstash reads MariaDB every minute with a read-only user that cannot see personal data. An `es_data` folder from Elasticsearch 8 must be deleted first (Elasticsearch 9 only upgrades data from 8.19); `make analytics-resync` fills it again.

## Languages

Persian is the default. A visitor picks a language with the dropdown at the top of every page (stored in a cookie, no language in the URL); otherwise the browser's language is used. Persian and Arabic render right-to-left, the others left-to-right, from the same stylesheet (CSS logical properties). Persian pages use the Jalali calendar, the other languages the Gregorian one. Candidates and employers also have a preferred language that is used for e-mails and reports.

- Messages live in `src/locale/<language>/LC_MESSAGES/django.po` (`zh-hans` is the folder `zh_Hans`). The source language of the code is English.
- After changing text in a template or Python file run `make i18n` (extracts into every `.po`; runs in Docker because it needs GNU gettext), translate the new empty entries, then `make i18n-check` (fails on missing, fuzzy or placeholder-breaking translations).
- `.mo` files are not committed. `make dev` builds them with a pure-Python script (`make i18n-compile`); the Docker services run Django's `compilemessages`.

## AI summaries

Resume summaries run in the background (Celery) in the employer's language, through [OpenRouter](https://openrouter.ai) only:

- `OPENROUTER_API_KEY` set: summaries are on.
- No key: the feature is skipped silently (applications work as usual, no summary is shown).

Settings: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` (default `google/gemma-3-4b-it`, a very light multilingual model; any OpenRouter model id works), `AI_TIMEOUT_SECONDS`, `AI_MAX_INPUT_CHARS` (resume text is cut to this length, default 12000). The key is read from the environment only and is never logged or shown.

> **Privacy:** the text of uploaded resumes is sent to OpenRouter and the model provider behind it.

## Admin

`/admin/` uses the [Unfold](https://unfoldadmin.com) theme, configured in Python only (`UNFOLD` in `settings.py`, callbacks in `src/requester/admin.py`): a grouped menu with live counts (open jobs, pending applications), colored status labels, dropdown and date-range filters, and the environment name in the header (`APP_ENVIRONMENT`).

Admin classes import `ModelAdmin` and `RangeDateTimeFilter` from `requester/unfold_admin.py`, not from `unfold`: it fixes a deprecated signature and naive datetimes in Unfold 0.110 (see the module docstring).

## Diagrams

The PlantUML sources are in `diagram/`; `make diagrams` redraws the PNGs (PlantUML runs in Docker).

| Class diagram | Use cases |
|---|---|
| ![Class Diagram](diagram/class_diagram.png) | ![Use Case Diagram](diagram/use_case_diagram.png) |

![Sequence Diagram](diagram/sequence_diagram.png)

![Activity Diagram](diagram/activity_diagram.png)

## Names and upgrading an old database

The project was renamed so that the code says what things are:

| Before | Now |
|---|---|
| app `offer`, model `Offer` | app `employers`, model `Employer` |
| `Job`, `Tag` | `JobPosting`, `Skill` (in `employers`) |
| app `worker`, model `Worker` | app `candidates`, model `Candidate` |
| `JobRequest` | `Application` (app `applications`, with `ApplicationEvent` for the status history) |
| app `requester_handler` | merged into `applications` (`tasks.py`, `ai.py`) |
| `/offer/…`, `/worker/…` | `/employers/…`, `/candidates/…` (old URLs redirect permanently) |
| compose services `web, celery, ollama, elasticsearch, mailserver, mariadb, redis` | `web, tasks, scheduler, search, mailhog, db, cache` (the local Ollama service was removed) |

`make dev` and `make deploy` run `manage.py migrate` and then `manage.py import_legacy_data`. It copies the rows of the old `offer_*` / `worker_*` tables into the new ones, keeping IDs and timestamps (so uploaded resumes still match), does nothing on a fresh database and nothing the second time. The old tables are left in place as a backup; drop them when you are satisfied.
