# Log schema

This file is the single source of truth for Requester's structured logs. The code
lives in `src/observability/logging_config.py` (processors, redaction),
`src/observability/middleware.py` (request lines) and
`src/observability/celery_signals.py` (task context).

Every process (gunicorn `web`, Celery `tasks`, Celery beat `scheduler`) writes
**one JSON object per line to stdout**. structlog calls and plain stdlib loggers
(Django, Celery, gunicorn, httpx, Elasticsearch, ...) go through the same
processor chain, so they share every field below. With `LOG_FORMAT=console`
(the default when `DEBUG` is on) the same fields are rendered for humans
instead; JSON and plain text are never mixed in one stream.

Example:

```json
{"event": "http_request", "method": "GET", "path": "candidates/jobs/<int:pk>/", "status_code": 200, "duration_ms": 12.48, "user_id": 7, "client_ip": "172.18.0.1", "request_id": "verify-123", "level": "info", "logger": "observability.middleware", "timestamp": "2026-11-23T09:15:02.481Z", "service": "web", "environment": "production", "version": "0.1.0", "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736", "span_id": "00f067aa0ba902b7"}
```

## Fields

| Field | Type | When present | Example |
|---|---|---|---|
| `timestamp` | string, ISO-8601 UTC, milliseconds, `Z` | always | `"2026-11-23T09:15:02.481Z"` |
| `level` | string: `debug`, `info`, `warning`, `error`, `critical` | always | `"warning"` |
| `event` | string, snake_case for our own events; the formatted message for third-party stdlib records | always | `"job_report_sent"` |
| `service` | string, env `SERVICE_NAME` (default `web`) | always | `"tasks"` |
| `environment` | string, env `APP_ENVIRONMENT` (default `development`) | always | `"production"` |
| `version` | string, env `APP_VERSION` (default `0.1.0`) | always | `"0.1.0"` |
| `logger` | string, logger name | always | `"applications.tasks"` |
| `request_id` | string or null | always; set inside a request and inside a Celery task (propagated from the request that queued it) | `"9f1c0d6e2b8a4f7e9d3c5b1a0e2f4d6c"` |
| `trace_id` | string (32 hex) or null | always; null when OTel is off or there is no active span | `"4bf92f3577b34da6a3ce929d0e0e4736"` |
| `span_id` | string (16 hex) or null | always; null like `trace_id` | `"00f067aa0ba902b7"` |
| `user_id` | int or null | `http_request` lines, and any line logged inside a view after authentication | `7` |
| `method` | string | `http_request`, `http_request_failed` | `"POST"` |
| `path` | string, the **route template** (`resolver_match.route`), never the raw URL; `"<unmatched>"` when no route matched (404) | `http_request`, `http_request_failed` | `"candidates/jobs/<int:pk>/"` |
| `status_code` | int | `http_request`; also `django.request` 4xx/5xx records | `404` |
| `duration_ms` | float, rounded to 2 decimals | `http_request` | `12.48` |
| `client_ip` | string or null | `http_request` | `"172.18.0.1"` |
| `task_id` | string | lines logged inside a Celery task | `"5b6f..."` |
| `task_name` | string | lines logged inside a Celery task | `"applications.tasks.send_posting_report"` |
| `exc_type` | string, exception class name | lines logged with an exception | `"ValueError"` |
| `exc_message` | string | lines logged with an exception | `"boom"` |
| `stack` | string, the formatted traceback | lines logged with an exception (or `stack_info=True`) | `"Traceback (most recent call last): ..."` |
| `application_id` | int | application task events | `42` |
| `posting_id` | int | posting task events | `3` |
| `alert_id` | int | job-alert events | `11` |
| `contact_email` | string, hashed (see redaction) | `job_report_sent` | `"sha256:d46cf9ecef95"` |
| `reason` | string | `resume_summary_skipped` | `"no_ai_provider"` |

Other keyword arguments passed to a structlog call, and stdlib `extra={...}`
values, appear as top-level fields too. Add them to this table when you add one.
The `request` object that Django attaches to `django.request`/`django.server`
records is dropped (its repr holds the raw URL).

Types are enforced by a processor: `status_code` is always an int,
`duration_ms` always a float, `user_id` always an int or null.

## Client IP

`client_ip` is `REMOTE_ADDR`. The first `X-Forwarded-For` entry is used instead
only when the setting `LOG_TRUST_FORWARDED_FOR` is true. If that setting is not
defined, it follows `SECURE_PROXY_SSL_HEADER` (set by `BEHIND_PROXY=true`), as
then a trusted reverse proxy sets the header. Never enable it when clients can
reach gunicorn directly: the header is trivial to spoof.

## Request IDs

* `RequestLogMiddleware` accepts an incoming `X-Request-ID` that matches
  `^[A-Za-z0-9._-]{1,128}$`; anything else is replaced by a new `uuid4().hex`.
* The ID is set as `request.request_id`, bound to the log context and returned in
  the `X-Request-ID` response header.
* When a task is queued during a request, `before_task_publish` copies the ID into
  the Celery message header `request_id`; the worker binds it in `task_prerun`.
  Tasks queued outside a request (beat) get a fresh ID per run.

## Event naming rules

* `snake_case`, past tense or noun phrase, `<object>_<what happened>`:
  `job_report_sent`, `resume_read_failed`.
* The event name is a **constant**. Variable data goes in fields, never in the
  event string (`logger.info("job_report_sent", posting_id=p.id)`, not
  `f"report {p.id} sent"`).
* Failures end in `_failed` and are logged with `logger.exception(...)` (inside
  `except`) so `exc_type`, `exc_message` and `stack` are filled.
* Use `structlog.get_logger(__name__)`; the module path becomes `logger`.
* Never log request/response bodies, headers, cookies, passwords or tokens.

## Events

| Event | Level | Logger | Fields |
|---|---|---|---|
| `http_request` | info; warning for 4xx; error for 5xx | `observability.middleware` | `method`, `path`, `status_code`, `duration_ms`, `user_id`, `client_ip` |
| `http_request_failed` | error | `observability.middleware` | `method`, `path`, exception fields |
| `resume_summary_skipped` | info | `applications.tasks` | `reason` |
| `application_not_found` | warning | `applications.tasks` | `application_id` |
| `resume_read_failed` | error | `applications.tasks` | `application_id`, exception fields |
| `resume_summary_failed` | error | `applications.tasks` | `application_id`, exception fields |
| `posting_not_found` | warning | `applications.tasks` | `posting_id` |
| `job_report_sent` | info | `applications.tasks` | `posting_id`, `contact_email` (hashed) |
| `job_alert_send_failed` | error | `candidates.alerts` | `alert_id`, exception fields |
| `resume_summary_queue_failed` | error | `candidates.views` | `application_id`, exception fields |
| `status_email_queue_failed` | error | `employers.views` | `application_id`, exception fields |

## Redaction

Applied to every field, recursively into nested dicts and lists, for structlog
and stdlib records alike:

* **Keys** containing (case-insensitive substring) `password`, `passwd`,
  `secret`, `token`, `api_key`, `authorization`, `cookie`, `sessionid`,
  `csrftoken`, `card_number`, `cvv`: the value becomes `"[REDACTED]"`.
* **Keys** containing `email`: the value becomes
  `"sha256:" + sha256(lower(value))[:12]`. The same hash is used for e-mail
  addresses found inside any string value (including `event`), so one address
  always maps to the same token and can still be searched for.
* **Card-like numbers**: runs of 13 to 19 digits (single spaces or dashes allowed
  between digits) inside string values become `"[REDACTED_CARD]"`.

To search for one user's address: compute the hash locally,
`python -c "import hashlib;print(hashlib.sha256(b'sara@example.com').hexdigest()[:12])"`,
then query `|= "sha256:<hash>"`.

## Loki labels

Vector (`monitoring/vector/vector.yaml`) sends the lines of `requester_web`,
`requester_tasks` and `requester_scheduler` to Loki with **only** these labels:
`level`, `service`, `environment`. Lines that are not JSON are kept with
`level="unknown"` and `event="unparsed_line"`. High-cardinality fields
(`request_id`, `user_id`, `trace_id`, `path`, ...) stay in the line; use `| json`.

## LogQL examples

```logql
# Everything for one request, across web and Celery
{service=~".+"} | json | request_id="verify-123"

# Errors of the web service in production
{service="web", environment="production", level="error"}

# Error rate per service
sum by (service) (rate({level=~"error|critical"}[5m]))

# Top error events in the last hour
topk(10, sum by (event) (count_over_time({level=~"error|critical"} | json event="event" [1h])))

# Slow requests
{service="web"} | json | event="http_request" | duration_ms > 500

# p95 latency per route
quantile_over_time(0.95, {service="web"} | json | event="http_request" | unwrap duration_ms | __error__="" [5m]) by (path)

# 5xx responses per route
sum by (path) (count_over_time({service="web"} | json | event="http_request" | status_code >= 500 [15m]))

# Everything one user did (user_id is only on request lines)
{service="web"} | json | user_id=7

# Lines Vector could not parse as JSON
{level="unknown"}
```

In Grafana, the `trace_id` value of a line links to the trace in Jaeger (Loki
datasource `derivedFields`). The "Requester / Logs" dashboard has a
`request_id` text box that drives the "Follow one request" panel.
