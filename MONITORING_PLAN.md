# Plan: Observability, structured logging, perf tests & benchmarks for Requester

## Context
Requester (Django 6.1.3, Python 3.12, uv) has no observability: one plain-text `LOGGING` dict in `src/requester/settings.py`, about 10 `logging.getLogger` call sites with free-text messages, and no metrics, tracing, error reporting, benchmarks, load tests or CI. The goal is production-grade observability (JSON logs → Loki, Prometheus/Grafana, OTel → Jaeger, Sentry) plus perf and load testing, built by sub-agents with strictly separate file ownership, committed phase by phase on `main`.

## Findings from Step 1 (they set the scope)
| Item | Reality | Effect on the plan |
|---|---|---|
| Server | gunicorn `-w 4` sync workers, no preload (`Makefile` `deploy`) | Prometheus **multiprocess mode** (`PROMETHEUS_MULTIPROC_DIR`). Init OTel at import time in `wsgi.py`; each worker imports it after fork. |
| DB | **MariaDB 11.4** (mysqlclient), SQLite in dev and tests | `mysqld-exporter`, not postgres-exporter. `opentelemetry-instrumentation-mysqlclient`. |
| Cache/broker | Redis 7 (cache + Celery broker). The app never calls `cache.*` itself | redis-exporter. The cache hit-ratio panel will be close to empty. Say so, don't fake it. |
| Celery | Yes: worker (`tasks`) and beat (`scheduler`) | celery-exporter (needs `-E` task events), request_id over task headers, OTel Celery instrumentation. |
| Elasticsearch 9 | Yes | No exporter and no OTel instrumentation (not asked for, ES 9 support unclear). Listed as a next step. |
| HTTP out | `httpx` in `applications/ai.py` | `opentelemetry-instrumentation-httpx`. No `requests`. |
| API | **No DRF**, only server-rendered views (`candidates/`, `employers/` urls) | Query-count tests and Locust target HTML views. Login flows need a CSRF token. |
| Existing N+1 care | Views already use `select_related`/`prefetch_related` widely | D measures first and fixes only proven N+1 issues. |
| Tests | pytest + pytest-django, `requester.settings_test`, fixtures in `src/conftest.py` | Reuse the `make_employer/candidate/posting/application` fixtures. |
| CI | None | Add `.github/workflows/ci.yml` (user approved). |
| Compose | `docker-compose.yaml` (prod-like) + `docker-compose.dev.yaml` overlay | New overlay **`docker-compose.monitoring.yaml`** (`.yaml` to match the existing files). |
| Promtail | EOL since 2026-03 | Use **Vector** → Loki. |
| Git | On `main`, tree clean. A **pre-existing local branch `original-version`** exists | Don't touch it. Report it, because the "only `main`" check will list it. |

## Decisions
- Code lives in a new plain package **`src/observability/`** (no models, so not in INSTALLED_APPS). One file per owner.
- **Dependencies are added up front by the Orchestrator in Phase 0** (`uv add pkg==X.Y.Z`, exact pins, latest at execution time), so no agent touches `pyproject.toml`/`uv.lock`. Runtime: `structlog`, `django-prometheus`, `sentry-sdk`, `opentelemetry-{api,sdk,exporter-otlp-proto-http}`, `opentelemetry-instrumentation-{django,mysqlclient,redis,httpx,celery}`. Dev group: `pytest-benchmark`, `django-debug-toolbar`, `django-silk`. New `loadtest` group: `locust`.
- Risk: **django-prometheus may not officially support Django 6.1**. B checks this first. If the DB/cache backend wrappers break, keep the middleware and `/metrics`, drop the wrappers, and get DB timing from OTel spans plus mysqld-exporter. Report which path was taken.
- Sentry: SDK only, off when `SENTRY_DSN` is empty, `send_default_pii=False`, `traces_sample_rate=0` by default (OTel does tracing), `request_id` set as a tag. Tested with a mocked transport (user approved).
- Tracing backend: **Jaeger** (all-in-one, OTLP in) behind an **OTel Collector**. Grafana gets Jaeger and Loki datasources, and a Loki `derivedFields` link `trace_id` → Jaeger.
- Alerts: Prometheus rule files only. No Alertmanager (no receiver to send to); listed as a next step.
- Benchmark gate in CI: the same job runs the benchmarks on the base commit (saved as the baseline), then on HEAD with `--benchmark-compare-fail=mean:20%`. Same runner, so the comparison is fair, and no machine-specific baseline is committed. `pyproject` addopts gets `--benchmark-disable`, so `make test` runs benchmark tests once without timing. `make bench` / `make bench-check` run them for real.
- debug-toolbar and silk are imported only when `DEBUG` **and** `DEBUG_TOOLBAR=true` / `SILK_ENABLED=true`, guarded by `try: import`. They are in the dev group, so the Docker image (`--no-dev`) never has them.

## Shared contracts (written in Phase 0, before any agent starts)
**Env vars** (all added to `.env.example`; defaults are off or safe):
`LOG_LEVEL=INFO`, `LOG_FORMAT` (`console` when DEBUG else `json`), `SERVICE_NAME` (`web`/`tasks`/`scheduler`, matching the compose service names), `APP_ENVIRONMENT=development`, `APP_VERSION` (defaults to the pyproject version), `PROMETHEUS_ENABLED=false`, `PROMETHEUS_MULTIPROC_DIR`, `METRICS_TOKEN` (empty → `/metrics` returns 404), `OTEL_ENABLED=false`, `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318`, `OTEL_TRACES_SAMPLER_ARG=0.1` (ratio, parent-based), `SENTRY_DSN=`, `SENTRY_TRACES_SAMPLE_RATE=0`, `DEBUG_TOOLBAR=false`, `SILK_ENABLED=false`, `GRAFANA_ADMIN_PASSWORD`.

**Ports** (host side bound to `127.0.0.1`): Grafana 3000, Prometheus 9090, Loki 3100, Jaeger UI 16686, OTel Collector 4317/4318 (internal only), mysqld-exporter 9104, redis-exporter 9121, celery-exporter 9808, Vector (internal). Prometheus scrapes `web:8000/metrics` with `Authorization: Bearer $METRICS_TOKEN`.

**Log schema** (`docs/log-schema.md`, by A): the required fields from the brief (`timestamp` ISO-8601 UTC with ms and `Z`, `level`, `event` snake_case, `service`, `environment`, `version`, `logger`, `request_id`, `trace_id`, `span_id`). Request fields: `method`, `path` (= `resolver_match.route`, `"<unmatched>"` for 404s), `status_code:int`, `duration_ms:float`, `user_id:int`, `client_ip`. Error fields: `exc_type`, `exc_message`, `stack:str`. One table of every field and its type is the single source of truth. Redaction denylist: `password, passwd, secret, token, api_key, authorization, cookie, sessionid, csrftoken, card_number, cvv` (masked as `"[REDACTED]"`). Fields with email values are hashed (`sha256:` + first 12 hex characters).

## Agents, owned files, order
| Agent | Owns (only these) | Phase |
|---|---|---|
| **A Logging** | `src/observability/__init__.py`, `logging_config.py` (structlog + `ProcessorFormatter`, redaction, trace-id processor that is a no-op when OTel is absent), `middleware.py` (request-ID: accepts a valid incoming `X-Request-ID` or uses uuid4, echoes it in the response header, binds contextvars, binds `user_id` in `process_view`, emits `http_request` with timing), `celery_signals.py` (`before_task_publish` header, `task_prerun/postrun` bind/clear, `setup_logging` no-op), `src/observability/tests/test_logging.py`, `docs/log-schema.md`, `monitoring/vector/*`, `monitoring/loki/*`, `monitoring/grafana/dashboards/logs.json` | 1 |
| **B Metrics** | `src/observability/metrics.py` (token/IP-protected wrapper around django-prometheus `ExportToDjangoView`, multiprocess aware), `src/observability/tests/test_metrics.py`, `monitoring/prometheus/*` (scrape config, `alerts.yml`: 5xx rate, p95 latency, target down), `monitoring/grafana/provisioning/*`, `monitoring/grafana/dashboards/django.json` | 1 |
| **D Perf** | `src/tests/perf/*`, `src/tests/benchmarks/*` (with `__init__.py`), N+1 fixes only in `src/candidates/views.py`, `src/employers/views.py` and model/queryset files, if a fix is proven | 1 |
| **C Tracing+Errors** | `src/observability/tracing.py` (`setup_tracing()`, idempotent, off unless `OTEL_ENABLED`), `src/observability/sentry.py`, `src/observability/tests/test_tracing.py`, `test_sentry.py`, `monitoring/otel/*`, `monitoring/grafana/provisioning/datasources/jaeger.yaml` (coordinate this file name with B up front) | 2 (after A) |
| **E Load** | `loadtests/locustfile.py` (candidate login → browse jobs → job detail → save posting; employer login → dashboard → create posting), `loadtests/README.md` (staging commands, "never production" warning) | 2 (after B) |
| **F Reviewer** | read-only | 3 |
| **G Docs** | `docs/observability.md` (ASCII architecture diagram, how to run, queries) | 3 |

A converts the existing log call sites in `applications/tasks.py`, `applications/ai.py` and `candidates/alerts.py` to structlog `event` names with fields. Each view file has one log line, and D owns those files, so A sends those two lines to the Orchestrator as snippets.

**Orchestrator-only shared files:** `MONITORING_PLAN.md`, `pyproject.toml`, `uv.lock`, `.env.example`, `src/requester/settings.py`, `settings_test.py`, `urls.py`, `wsgi.py`, `asgi.py`, `celery.py`, `src/manage.py`, `gunicorn.conf.py` (new: `logconfig_dict` through our formatter, access log off because the middleware logs requests, `child_exit` → `multiprocess.mark_process_dead`), `Makefile` (deploy uses `-c gunicorn.conf.py`, multiproc dir reset, celery `-E`, `bench`/`bench-check`/`monitoring-up` targets), `docker-compose.yaml` (add `SERVICE_NAME` per service only), `docker-compose.monitoring.yaml`, `.github/workflows/ci.yml`, `.gitignore` (`.benchmarks/`).

Each brief contains: goal, owned files, contracts above, acceptance criteria, "never edit other files, never run git write commands or `uv add`", and the return format (changes, files, verification, shared-file snippets, open issues).

## Execution & commits (all on `main`, explicit `git add <paths>`, `uv run pytest` before each)
0. Pre-flight `git status` / `git branch --show-current`. Write `MONITORING_PLAN.md`, add pinned deps, `.env.example` contract → commit `chore(observability): add plan, pinned deps and env contract`.
1. Spawn A, B, D in parallel (one message). Review each result, apply its snippets → commits `feat(logging): structlog JSON logging, request IDs, Vector/Loki pipeline`, `feat(metrics): django-prometheus, protected /metrics, Prometheus/Grafana`, `test(perf): query-count tests, benchmarks[, N+1 fixes]`.
2. Spawn C and E in parallel → `feat(tracing): OpenTelemetry + Jaeger, Sentry errors`, `test(load): Locust scenarios`, then `ci: GitHub Actions tests + benchmark gate`.
3. Spawn F and G in parallel. Fix what F finds in new commits → `docs(observability): architecture and runbook`, plus any `fix(...)` commits. Work that fails its acceptance criteria goes back to the agent (SendMessage) before the commit.

## Verification
- `uv run pytest` (whole suite, including the new log, metrics, tracing, sentry, perf and benchmark tests), `make lint`, `make typecheck`, `make check`.
- `docker compose -f docker-compose.yaml -f docker-compose.monitoring.yaml up -d --build`, then:
  - `docker compose logs web | python -c` check that every line parses as JSON and has the required fields.
  - `curl -H "Authorization: Bearer $METRICS_TOKEN" localhost:8000/metrics` returns data. Without the token it returns 404. Prometheus `/api/v1/targets` shows everything UP.
  - Send a request with `X-Request-ID: verify-123`. Loki `{service="web"} | json | request_id="verify-123"` finds it. Its `trace_id` opens the same trace in Jaeger (directly or through the Grafana link).
  - Sentry: unit test with a mocked transport. A live check needs the user's DSN (noted).
- `git branch --list` → `main` plus the pre-existing `original-version` (reported), and `git worktree list` shows only one.
- The final report lists each agent's deliverables, commits (hash + message), changed files, new env vars, run commands, N+1/slow spots, skipped items (postgres exporter, ES exporter/instrumentation, Alertmanager, live Sentry check, empty cache-hit panel) with reasons, and next steps.
