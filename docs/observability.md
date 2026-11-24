# Observability

How Requester produces logs, metrics, traces and error reports, how to run the
monitoring stack, and how to use it. Field-level details of the logs live in
[`log-schema.md`](log-schema.md); the load tests are described in
[`../loadtests/README.md`](../loadtests/README.md).

Code: `src/observability/` (logging, request IDs, metrics, tracing, Sentry).
Config: `monitoring/` (Prometheus, Vector, Loki, OTel Collector, Jaeger, Grafana).
Compose: `docker-compose.monitoring.yaml` (an overlay on `docker-compose.yaml`).

## 1. Overview

| Signal | Produced by | Shipped by | Stored in | Viewed in |
|---|---|---|---|---|
| Logs | structlog, one JSON object per line on stdout | Vector (`docker_logs` source) | Loki (7 days) | Grafana "Requester / Logs" |
| Metrics | django-prometheus at `/metrics` + mysqld, redis and celery exporters | Prometheus scrape (15 s) | Prometheus (15 days) | Grafana "Requester / Django", Prometheus alerts |
| Traces | OpenTelemetry SDK (Django, mysqlclient, redis, httpx, Celery) | OTLP/HTTP → OTel Collector | Jaeger (in memory) | Jaeger UI, Grafana Explore |
| Errors | sentry-sdk (optional) | HTTPS to Sentry | Sentry (external) | Sentry |

```
  Browser / Locust (loadgen)
          |  HTTP  (X-Request-ID, W3C traceparent)
          v
 +---------------------------------------------+        +---------------------------+
 | web: Django (gunicorn workers / runserver)  |        | tasks: Celery worker (-E) |
 |   RequestLogMiddleware  -> http_request log |  task  | scheduler: Celery beat    |
 |   django-prometheus     -> /metrics         |------->|   request_id + trace ctx  |
 |   OpenTelemetry SDK     -> spans            | Redis  |   in the task headers     |
 +---------------------------------------------+        +---------------------------+
     |  stdout JSON      |  /metrics          |  OTLP/HTTP :4318         |   |
     |                   |  (Bearer token)    |                          |   |
     |   +---------------|--------------------|--------------------------+   |
     |   |  stdout JSON  |                    |   +--------------------------+
     v   v               |                    v   v      OTLP/HTTP
 +------------------+    |              +------------------+
 | Vector           |    |              | OTel Collector   |
 | (docker.sock)    |    |              | memory_limiter,  |
 +------------------+    |              | batch            |
          | push         |              +------------------+
          v              |                       | OTLP/gRPC :4317
 +------------------+    |                       v
 | Loki :3100       |    |              +------------------+
 +------------------+    |              | Jaeger :16686    |
          ^              v              +------------------+
          |     +--------------------+           ^
          |     | Prometheus :9090   |<-- mysqld-exporter :9104 (MariaDB)
          |     | rules: alerts.yml  |<-- redis-exporter  :9121 (Redis)
          |     +--------------------+<-- celery-exporter :9808 (Celery events)
          |              ^                       |
          |              |                       |
 +-----------------------------------------------------------+
 | Grafana :3000   datasources: Prometheus, Loki, Jaeger      |
 |   Loki line trace_id --> Jaeger trace (derivedFields)      |
 |   Jaeger span        --> Loki lines   (tracesToLogsV2)     |
 +-----------------------------------------------------------+

 Sentry (optional, external SaaS): web, tasks and scheduler send errors when SENTRY_DSN is set.
```

Every UI is bound to `127.0.0.1` on the host. The OTel Collector (4317/4318),
the exporters and Vector have no host ports; they are reachable only on the
compose network.

## 2. Quick start

### Everything for local development: `make dev-all`

```bash
make dev-all
make dev-all-down   # stop it
```

It runs `docker compose` with `monitoring/dev-defaults.env` (then `.env` if it
exists, which wins), and the files `docker-compose.yaml`,
`docker-compose.dev.yaml` and `docker-compose.monitoring.yaml` with the
`loadgen` profile. That starts:

* the app: `web` (Django dev server, `DEBUG` on, via `make deploy-dev`), `tasks`
  (Celery worker), `scheduler` (Celery beat), MariaDB, Redis, MailHog
  (Elasticsearch is in the separate analytics overlay, docs/analytics.md);
* the monitoring stack: Prometheus, Grafana, Loki, Vector, OTel Collector,
  Jaeger, mysqld-, redis- and celery-exporter;
* `loadgen`: a headless Locust (`locustio/locust:2.47.0`, `LOADGEN_USERS`
  users, 5 by default) that starts once `web` is healthy and keeps traffic
  flowing so the dashboards have data.

`make dev-all-with-load` starts the same stack with a busier generator: 30
virtual users instead of 5 (`make dev-all-with-load LOADGEN_USERS=100` for more).
Use it when you want the dashboards, alerts, logs and traces to move: watch the
generator with `docker logs -f requester_loadgen`. `make dev-all-down` stops both.

On the first start `deploy-dev` migrates, runs `seed_demo_data` (fixed demo
accounts) and `seed_fake_data` (Faker volume data) and creates the admin. That can take several minutes; the `web` healthcheck has
a 10 minute start period.

| What | URL | Login |
|---|---|---|
| App | http://localhost:8000 | Django admin `admin` / `admin` (from `docker-compose.dev.yaml`) |
| Grafana | http://localhost:3000 | `admin` / `admin` (`GRAFANA_ADMIN_PASSWORD` in `monitoring/dev-defaults.env`) |
| Prometheus | http://localhost:9090 | none |
| Loki API | http://localhost:3100 | none (use Grafana Explore) |
| Jaeger | http://localhost:16686 | none |
| MailHog | http://localhost:8025 | none |

Demo users from `seed_demo_data` all use the password `password123`: employers
`alice`, `frank`, `grace`, `heidi`, `ivan`, `judy`, `karen`, `leo`, `mia`, `nick`;
candidates `worker1` to `worker12`. The load generator logs in as `worker1` and
`alice`. The command refuses to run unless `DJANGO_DEBUG` is on.

The demo world is small but lived-in. Ten employers in seven languages and about
thirty postings (open, past the deadline, closed by the employer, with and without
salary or deadline, Persian and French titles for right-to-left and accent
checks). Twelve candidates: complete profiles, one not looking for work
(`worker11`) and an empty one (`worker12`, profile 0%). Each candidate has
applications in all six statuses, with a status history, employer notes and AI
summaries, plus saved postings and job alerts (`worker1` has an extra paused one).
New rows are backdated over the last weeks, so charts show a timeline. Running it
again changes nothing.

`seed_fake_data` (also `make seed-fake` for the SQLite dev database) adds about
20 employers, 200 postings, 300 candidates and 1500 applications with usernames
`fake_s<seed>_...`. Fake accounts cannot log in, except the first fake employer
and candidate when `FAKE_DATA_PASSWORD` is set. Options go through `FAKE_ARGS`,
for example `FAKE_ARGS="--seed 7 --wipe-fake"`. It also fills the search log
(`manage.py top_searches`, admin "Job searches") with about half as many searches
as applications over the last 45 days, popular roles most often and a few words
with no results; `--searches N` sets the number. The log is only seeded while it
is empty.

The dev token for `/metrics` is `dev-metrics-token` (`monitoring/dev-defaults.env`).

### Production-like: `make monitoring-up`

```bash
make monitoring-up     # docker compose -f docker-compose.yaml -f docker-compose.monitoring.yaml up -d --build
make monitoring-down
```

This is the base (production-like) stack, gunicorn with 4 workers, plus the
monitoring overlay, without the dev overrides and without `loadgen`. It needs in
`.env`:

* `METRICS_TOKEN`: compose stops with `set METRICS_TOKEN in .env` otherwise.
  It is given to `web` and written into a compose secret that Prometheus reads
  from `/etc/prometheus/metrics_token`, so it never appears in a config file.
* `GRAFANA_ADMIN_PASSWORD`: the Grafana `admin` password.
* `SECRET_KEY` (the base stack needs it with `DEBUG` off).

Generate a token with, for example, `python -c "import secrets;print(secrets.token_urlsafe(32))"`.

## 3. Configuration

Every variable is optional; the defaults are off or safe. The monitoring
overlay sets the ones marked "overlay" for the containers itself.

| Variable | Default | Effect |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Root log level (Django settings and `gunicorn.conf.py`). |
| `LOG_FORMAT` | `console` when `DJANGO_DEBUG` is on, else `json` (gunicorn: `json`) | `json`: one JSON object per line. `console`: `key=value` text for humans. |
| `SERVICE_NAME` | `web` | `service` log field, OTel `service.name`, Sentry tag. Compose sets `web`, `tasks`, `scheduler`. |
| `APP_ENVIRONMENT` | `development` | `environment` log field and Loki label, OTel `deployment.environment.name`, Sentry environment fallback. |
| `APP_VERSION` | version from `pyproject.toml` (`0.1.0`) | `version` log field, OTel `service.version`, Sentry release. |
| `LOG_TRUST_FORWARDED_FOR` (setting) | follows `BEHIND_PROXY` | Use the first `X-Forwarded-For` entry as `client_ip`. Only behind a trusted proxy. |
| `PROMETHEUS_ENABLED` | `false` (overlay: `true` on `web`) | Adds django-prometheus middleware, DB backend wrapper and the `/metrics` route. |
| `METRICS_TOKEN` | empty (dev: `dev-metrics-token`) | Bearer token for `/metrics`. Empty means `/metrics` returns 404. |
| `METRICS_ALLOWED_IPS` | empty | Optional comma-separated CIDRs that `REMOTE_ADDR` must be in, in addition to the token. |
| `PROMETHEUS_MULTIPROC_DIR` | empty (overlay: `/tmp/prometheus-multiproc`, a tmpfs) | Turns on prometheus_client multiprocess mode. Needed with several gunicorn workers. An empty value is treated as unset. |
| `OTEL_ENABLED` | `false` (overlay: `true` on web, tasks, scheduler) | Turns tracing on. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4318` | OTLP/HTTP endpoint; `/v1/traces` is appended. |
| `OTEL_TRACES_SAMPLER_ARG` | `0.1` (overlay: `1.0`) | Ratio for `ParentBased(TraceIdRatioBased(...))`. |
| `OTEL_TRACES_SAMPLER` | empty | Standard OTel override, e.g. `always_on`, `parentbased_always_off`. When set, the SDK's own env handling is used. |
| `OTEL_PYTHON_DJANGO_EXCLUDED_URLS` | `/metrics/?$,/static/,/favicon\.ico$` | Comma-separated URL regexes that are not traced. |
| `SENTRY_DSN` | empty | Sentry is off while empty. |
| `SENTRY_TRACES_SAMPLE_RATE` | `0` | Sentry performance monitoring; 0 turns it off (OTel does tracing). |
| `SENTRY_ENVIRONMENT` | `APP_ENVIRONMENT` | Sentry environment. |
| `DEBUG_TOOLBAR` | `false` | django-debug-toolbar at `/__debug__/` (needs `DJANGO_DEBUG=true` and the dev group). |
| `SILK_ENABLED` | `false` | django-silk at `/silk/`, staff only (needs `DJANGO_DEBUG=true`, the dev group and `migrate`). |
| `GRAFANA_ADMIN_PASSWORD` | none (dev: `admin`) | Grafana `admin` password; required by the overlay. |
| `LOADGEN_USERS` | `5` | Number of Locust users in the `loadgen` container. |
| `FAKE_DATA_PASSWORD` | empty | Lets the first fake employer and candidate from `seed_fake_data` log in. |

Note: the base compose file passes only a fixed list of variables into the
containers (`x-app-env`). Setting `LOG_FORMAT`, `LOG_LEVEL`, `APP_ENVIRONMENT`,
`APP_VERSION`, `SENTRY_*`, `METRICS_ALLOWED_IPS` or `OTEL_TRACES_SAMPLER` in
`.env` does not reach the app containers today; see Open issues.

## 4. Logs

**Format.** Every process (gunicorn/runserver `web`, Celery `tasks`, Celery beat
`scheduler`) writes one JSON object per line to stdout. structlog loggers and
plain stdlib loggers (Django, Celery, gunicorn, httpx, ...) go through the same
processor chain. gunicorn's access log is off (`accesslog = None` in
`src/gunicorn.conf.py`) because `RequestLogMiddleware` logs every request as
`http_request`; `gunicorn.error` goes through the same JSON formatter. The field
list, event names and LogQL examples are in [`log-schema.md`](log-schema.md).

**Redaction** (applied to every field, recursively):
keys containing `password`, `passwd`, `secret`, `token`, `api_key`,
`authorization`, `cookie`, `sessionid`, `csrftoken`, `card_number`, `cvv` become
`"[REDACTED]"`; e-mail addresses (keys containing `email`, and addresses inside
any string) become `sha256:` plus the first 12 hex characters of the hash; runs
of 13 to 19 digits become `"[REDACTED_CARD]"`. Bodies, headers and cookies are
never logged.

**request_id propagation.**

1. HTTP: `RequestLogMiddleware` keeps an incoming `X-Request-ID` matching
   `^[A-Za-z0-9._-]{1,128}$`, otherwise generates `uuid4().hex`. It sets
   `request.request_id`, binds it to structlog contextvars and returns it in the
   `X-Request-ID` response header. `user_id` is bound in `process_view`.
2. Celery publish: `before_task_publish` copies the current `request_id` into
   the task message header `request_id`.
3. Celery run: `task_prerun` binds `request_id` (from the header, or a new one
   for beat-scheduled tasks), `task_id` and `task_name`; `task_postrun` clears it.

**Loki labels** are only `level`, `service` and `environment`. `request_id`,
`user_id`, `trace_id` and `path` are not labels: each distinct value would
create a new Loki stream (high cardinality), which bloats the index and slows
every query. They stay in the line; filter them after `| json`.

**LogQL recipes** (Grafana → Explore → Loki):

```logql
# Errors by service (lines per second)
sum by (service) (rate({level=~"error|critical"}[5m]))

# Errors of one service
{service="tasks", level=~"error|critical"}

# Slow requests
{service="web"} | json | event="http_request" | duration_ms > 500

# Follow one request across web and Celery
{service=~".+"} | json | request_id="verify-123"

# Load-test traffic (Locust sends X-Request-ID: loadtest-<uuid>)
{service="web"} | json | request_id=~"loadtest-.*"

# p95 latency per route
quantile_over_time(0.95, {service="web"} | json | event="http_request" | unwrap duration_ms | __error__="" [5m]) by (path)

# Lines Vector could not parse as JSON
{level="unknown"}
```

Try it end to end: `curl -H "X-Request-ID: verify-123" http://localhost:8000/`,
then run the "follow one request" query.

**Dashboard "Requester / Logs"** (variables `service`, `environment`,
`request_id`): Error rate by service (lines/s); Top error events; Request
latency p95 by route (ms); Slow requests (duration_ms > 500); Follow one request
(request_id = $request_id); Errors.

## 5. Metrics

**What is exported.**

* Django (`web:8000/metrics`, job `django`): django-prometheus request counts
  and latency histograms by view, method and status, exceptions by type, DB
  query counts, errors and durations (DB backend wrapper for MySQL/SQLite), and
  the LocMem cache wrapper when no Redis is configured.
* `mysqld-exporter:9104` (job `mysqld`): MariaDB server status.
* `redis-exporter:9121` (job `redis`): Redis memory, keyspace hits/misses.
* `celery-exporter:9808` (job `celery`): workers online, tasks sent, received,
  succeeded, failed, runtime. Needs task events, so the worker runs with `-E`.
* Prometheus itself (job `prometheus`).

**Protection of `/metrics`.** The route exists only with `PROMETHEUS_ENABLED`.
`observability.metrics.metrics_view` answers 404 unless the request sends
`Authorization: Bearer $METRICS_TOKEN` (and, if `METRICS_ALLOWED_IPS` is set,
`REMOTE_ADDR` is inside one of the CIDRs; `X-Forwarded-For` is ignored). Every
refusal is a plain 404 so the endpoint is not discoverable. Never expose it
publicly.

```bash
curl -H "Authorization: Bearer dev-metrics-token" http://localhost:8000/metrics
```

**gunicorn multiprocess mode.** `make deploy` runs `gunicorn -w 4` (sync
workers, no preload). Each worker has its own registry, so with
`PROMETHEUS_MULTIPROC_DIR` set, prometheus_client writes per-process files there
and `/metrics` aggregates them. `make deploy` empties the directory before
gunicorn starts (the overlay also mounts it as a tmpfs), and the `child_exit`
hook in `src/gunicorn.conf.py` calls `multiprocess.mark_process_dead(pid)` for a
dead worker. An empty `PROMETHEUS_MULTIPROC_DIR` is removed from the environment
so it does not switch multiprocess mode on by accident.

**Dashboard "Requester / Django"** (folder Requester):

* Health: Django /metrics; MariaDB; Redis; Celery workers online; Request rate; 5xx ratio (5m)
* HTTP: Requests per second by status; Latency p50 / p95 / p99 (all views); 5xx rate; p95 latency by view (top 10); Requests per second by view (top 10); Exceptions by type
* Database: Django queries per second; Django query duration p50 / p95; MariaDB server
* Cache: Django cache hit ratio; Redis keyspace hit ratio; Redis memory used
* Celery: Tasks per second; Task runtime p95; Tasks sent vs received

**Alert rules** (`monitoring/prometheus/alerts.yml`). There is no Alertmanager
yet: alerts are visible on the Prometheus "Alerts" page and in Grafana only.

| Alert | Condition | For | Severity |
|---|---|---|---|
| `HighHttp5xxRate` | more than 5% of HTTP responses are 5xx | 5m | critical |
| `HighP95Latency` | p95 latency over all views above 1 s | 10m | warning |
| `TargetDown` | `up == 0` for any scrape target | 2m | critical |

**Known gaps.**

* "Django cache hit ratio" is mostly empty: the app barely calls `cache.*`
  itself, and with Redis configured the cache stays on Django's `RedisCache`
  (the django-prometheus Redis wrapper needs django-redis), so no
  `django_cache_*` metrics are produced. Use "Redis keyspace hit ratio" (which
  also counts Celery broker traffic) instead.
* No Elasticsearch exporter and no Elasticsearch tracing.
* No Alertmanager, so no notifications.

## 6. Tracing and errors

**Instrumented** (`src/observability/tracing.py`): Django server spans (with
`http.route`), mysqlclient, redis, httpx (AI calls to OpenRouter), and Celery
publish and run spans; the trace context travels in the task headers, so a
request and the task it queued share one trace. `/metrics`, `/static/` and
`/favicon.ico` are not traced by default.

**Where it starts.** `requester/wsgi.py` calls `setup_tracing(celery=True)`
before the WSGI app is created. gunicorn forks the workers before importing it
(no `--preload`), so each worker gets its own exporter. Celery calls it in
`worker_process_init` (each pool child) and `beat_init`. `setup_tracing()` is
idempotent and never raises; a failure logs `tracing_setup_failed`.

**Sampling.** `ParentBased(TraceIdRatioBased(OTEL_TRACES_SAMPLER_ARG))`: 10% by
default, 100% in the monitoring overlay (`${OTEL_TRACES_SAMPLER_ARG:-1.0}`). An
incoming W3C `traceparent` decides for its own trace. Lower the ratio for real
traffic.

**Logs to traces and back.**

* Every log line carries `trace_id` and `span_id` (null when tracing is off or
  there is no span). In Grafana Explore on Loki, expand a line: the `trace_id`
  derived field has an "Open trace in Jaeger" link.
* In a Jaeger trace in Grafana, a span's "Logs for this span" button runs
  `{service=~".+"} | json | trace_id="<trace id>"` in Loki (span time -5m/+5m).
* Without Grafana: copy the `trace_id` into the Jaeger UI search
  (http://localhost:16686); the `X-Request-ID` of a response finds the logs.
* Sentry events are tagged with `request_id`, `trace_id` and `service`.

**Sentry.** Set only `SENTRY_DSN` to turn it on (optional:
`SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE`). The Django and Celery
integrations report unhandled exceptions; ERROR log records become events and
INFO records breadcrumbs; duplicates are dropped by the dedupe integration. The
release is `APP_VERSION`.

**PII policy.** `send_default_pii=False`; the SDK's default scrubber masks
denylisted keys in frame variables; `before_send` also strips cookies, auth
headers and request bodies. Logs are redacted as in section 4. OTel spans hold
route templates and DB statements, not request bodies.

**Image versions** (`docker-compose.monitoring.yaml`):

| Component | Image |
|---|---|
| Prometheus | `prom/prometheus:v3.16.0` |
| Grafana | `grafana/grafana:13.3.1` |
| Loki | `grafana/loki:3.7.10` |
| Vector | `timberio/vector:0.62.0-alpine` |
| OTel Collector | `otel/opentelemetry-collector:0.165.0` |
| Jaeger | `jaegertracing/jaeger:2.20.0` |
| mysqld-exporter | `prom/mysqld-exporter:v0.21.0` |
| redis-exporter | `oliver006/redis_exporter:v1.98.0` |
| celery-exporter | `danihodovic/celery-exporter:0.12.2` |
| Locust (loadgen) | `locustio/locust:2.47.0` |

Jaeger is pinned to 2.20.0 on purpose: Grafana 13's Jaeger datasource uses the
`/api/services` API, which Jaeger 2.21+ removed. Jaeger keeps traces in memory
(at most 50000); they are lost on restart.

## 7. Performance

**Query-count tests** (`src/tests/perf/test_query_counts.py`). Each test
renders a page with N=2 objects, grows the data to N=10 and renders it again.
Both counts must be equal (no N+1) and equal to the number in `PINNED`, so a
missing `select_related`/`prefetch_related` fails the test. When a view
legitimately changes its query count, update its entry in `PINNED` (the count
includes the session and user lookups of the auth middleware). They run with
`make test`.

**Benchmarks** (`src/tests/benchmarks/`, pytest-benchmark): log rendering and
redaction, match scores, and the candidate jobs list/search, employer dashboard
and job detail views. `pyproject.toml` adds `--benchmark-disable`, so
`make test` runs them once, untimed.

```bash
make bench         # time them and save the run under .benchmarks/
make bench-check   # compare with the last saved run; fail if any median is 20% slower
```

**CI gate** (`.github/workflows/ci.yml`, job `benchmarks`, pull requests only):
on the same runner it checks out the base commit, saves a baseline
(`--benchmark-save=baseline`, at least 20 rounds, GC off), then checks out HEAD
and runs with `--benchmark-compare=0001 --benchmark-compare-fail=median:20%`.
If the base commit has no benchmarks the gate is skipped. No machine-specific
baseline is committed (`.benchmarks/` is git-ignored).

**Dev profilers** (only with `DJANGO_DEBUG=true` and the dev dependency group;
the Docker production image is built without it):

* `DEBUG_TOOLBAR=true`: django-debug-toolbar on every page (`INTERNAL_IPS`
  127.0.0.1 and ::1).
* `SILK_ENABLED=true`: django-silk at `/silk/` (staff only). Run `migrate`
  after turning it on.

```bash
cd src && DJANGO_DEBUG=true DEBUG_TOOLBAR=true uv run python manage.py runserver
```

## 8. Load testing

Locust scenarios in `loadtests/locustfile.py`: `CandidateUser` (login, list and
search jobs, job detail, save toggle, saved jobs, applications, dashboard),
`EmployerUser` (login, dashboard, jobs, job detail, create and delete a
posting) and `AnonymousUser`. Every request sends `X-Request-ID:
loadtest-<uuid>`, so a run is easy to find in Loki.

**Never run them against production.** The locustfile refuses any host other
than localhost or a host with a DNS label starting with `staging`, unless `LOADTEST_ALLOW_HOST` is
set to that exact host.

```bash
make loadtest   # headless smoke against the local dev server (needs LOADTEST_* env vars)
```

`make dev-all` runs the same file continuously in the `loadgen` container.
Accounts, staging and distributed runs, and the Grafana/Loki queries for a run:
[`loadtests/README.md`](../loadtests/README.md).

## 9. Troubleshooting

| Symptom | Likely cause | Check / fix |
|---|---|---|
| No logs in Loki | Vector cannot read the Docker socket | `docker compose logs vector`. It needs `/var/run/docker.sock` mounted (read-only). On Docker Desktop for Windows/macOS the socket path is provided by the VM; on rootless Docker or Podman adjust the mount. Vector only reads containers named `requester_web`, `requester_tasks`, `requester_scheduler`. |
| Logs in Loki, but `\| json` fails and `level="unknown"` | the app logs in `console` format (the default with `DEBUG` on) | Lines are stored as `event="unparsed_line"`. JSON needs `LOG_FORMAT=json` in the container environment (see Open issues for `make dev-all`). |
| Prometheus target `django` down | token mismatch, or `/metrics` not enabled | `curl -H "Authorization: Bearer <token>" http://localhost:8000/metrics` must return data; 404 means the token differs from Prometheus' secret, `PROMETHEUS_ENABLED` is off, or `METRICS_ALLOWED_IPS` excludes Prometheus. After changing `METRICS_TOKEN`, recreate both `web` and `prometheus`. |
| Exporter target down | DB/Redis not healthy yet, or wrong password | `docker compose logs mysqld-exporter` / `redis-exporter`; passwords come from `DB_PASSWORD` / `REDIS_PASSWORD`. |
| No traces in Jaeger | `OTEL_ENABLED` off or sampling too low | Check the container env (`docker compose exec web env | grep OTEL`); `OTEL_TRACES_SAMPLER_ARG=0.1` keeps 1 trace in 10; look for `tracing_setup_failed` in the logs; `docker compose logs otel-collector`. |
| Jaeger datasource errors in Grafana | Jaeger 2.21+ | Keep `jaegertracing/jaeger:2.20.0` (see section 6). |
| `/metrics` errors or numbers jump | `PROMETHEUS_MULTIPROC_DIR` missing, not writable, or holding stale files | With several workers it must be set and writable. `make deploy` empties it at start; the overlay mounts a tmpfs. An empty value is ignored on purpose. |
| Celery panels empty | worker started without task events | The worker must run with `-E` (`make setup_celery` does). |
| "Django cache hit ratio" empty | expected | See Known gaps in section 5. |
| `loadgen` never starts | `web` is not healthy yet (first-start seeding) | `docker compose ps`; the healthcheck allows 10 minutes. |

## Open issues

Found while writing this page; not fixed here.

1. **`make dev-all` logs are not JSON.** `docker-compose.dev.yaml` sets
   `DJANGO_DEBUG=true`, so `LOG_FORMAT` defaults to `console`
   (`src/requester/settings.py`), and `x-app-env` does not pass `LOG_FORMAT` into
   the containers. Vector then stores every app line as `unparsed_line` with
   `level="unknown"`: the "Requester / Logs" panels, `| json` queries and the
   `trace_id` → Jaeger link do not work on the dev-all stack. Setting
   `LOG_FORMAT=json` in `.env` has no effect for the same reason. A fix would be
   `LOG_FORMAT: "json"` for web/tasks/scheduler in the monitoring overlay.
2. **`.env` variables that never reach the containers.** `.env.example` lists
   `LOG_LEVEL`, `LOG_FORMAT`, `APP_ENVIRONMENT`, `APP_VERSION`,
   `METRICS_ALLOWED_IPS`, `OTEL_TRACES_SAMPLER`,
   `OTEL_PYTHON_DJANGO_EXCLUDED_URLS`, `SENTRY_DSN`,
   `SENTRY_TRACES_SAMPLE_RATE`, `SENTRY_ENVIRONMENT`, but `docker-compose.yaml`
   passes only `x-app-env` into the app containers. In Docker, Sentry cannot be
   turned on and `environment` is always `development`.
3. **`make dev-all` serves with `runserver`, not gunicorn**, while the overlay
   sets `PROMETHEUS_MULTIPROC_DIR`. It works (one serving process), but
   `deploy-dev` does not empty the directory and autoreload restarts leave files
   of dead PIDs behind until the container restarts. Multiprocess behaviour is
   only exercised by `make monitoring-up`.
4. **CI comment vs command.** `.github/workflows/ci.yml` says the gate fails
   when "a benchmark mean gets more than 20% slower", and `MONITORING_PLAN.md`
   says `mean:20%`, but the command (and `make bench-check`) uses
   `median:20%`.
5. **Plan vs compose ports.** `MONITORING_PLAN.md` lists host ports 9104, 9121,
   9808 for the exporters; `docker-compose.monitoring.yaml` publishes none of
   them (internal only, which is the safer choice). The `make dev-all` banner
   also omits Loki (3100) and MailHog (8025), which are published.
6. **`loadtests/README.md`** asks to add `loadtests/results/` to `.gitignore`;
   it is already there.
7. **mysqld-exporter privileges.** It connects as the app user (`DB_USER`),
   which has no `PROCESS`/`REPLICATION CLIENT` grants, so some collectors may
   log errors; `mysql_up` and global status still work. Not verified on a
   running stack.
