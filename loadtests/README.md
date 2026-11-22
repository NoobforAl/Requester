# Load tests (Locust)

Locust scenarios that drive the server-rendered candidate and employer portals the way real users do: sign in, browse and search jobs, open a job, save a job, and publish a posting. Use them to find slow views and regressions before a release, and to check the Prometheus, Grafana and Loki pipeline under load.

> **WARNING: NEVER run these load tests against production.** They sign in as real accounts, write data (save toggles, postings that are created and then deleted) and can overload the site. The locustfile refuses any host other than `localhost`, `127.0.0.1`, `::1` or a host whose name contains `staging`, unless `LOADTEST_ALLOW_HOST` is set to that exact host name. Never set `LOADTEST_ALLOW_HOST` to a production host.

## Scenarios

| User class | Weight | What it does |
|---|---|---|
| `CandidateUser` | 3 | Logs in at `/candidates/login/`, then lists jobs (with and without `?q=`), opens job details, toggles "save job" (POST), and opens saved jobs, applications and the dashboard. Save toggles that are left over are undone in `on_stop`. |
| `EmployerUser` | 1 | Logs in at `/employers/login/`, then opens the dashboard, the jobs list and job details. A low-weight write task publishes a `Loadtest <hex>` posting and deletes it again. |
| `AnonymousUser` | 1 | Opens the home page and both login pages. |

- Request names use templates (`/candidates/jobs/[id]/`, `/candidates/jobs/?q=[q]`), so stats are not split by id.
- Every request sends `X-Request-ID: loadtest-<uuid>`. The request-ID middleware keeps it, so the run can be found in Loki.
- A request fails when it returns HTTP 4xx/5xx, when it lands on the login page (a session was lost), or when a form POST does not redirect (the form was rejected).
- Timings for a POST include the redirect that follows it, because Locust follows redirects. A login takes about 0.7 s on a dev machine because of the password hash. That is expected.

## Configuration (environment variables)

| Variable | Purpose |
|---|---|
| `LOADTEST_CANDIDATE_USERNAME`, `LOADTEST_CANDIDATE_PASSWORD` | Candidate account. If either is missing, `CandidateUser` stops with a clear error. |
| `LOADTEST_EMPLOYER_USERNAME`, `LOADTEST_EMPLOYER_PASSWORD` | Employer account. If either is missing, `EmployerUser` stops with a clear error. |
| `LOADTEST_ALLOW_HOST` | An exact host name (for example `perf.example.net`) to allow besides the defaults. |
| `LOADTEST_READ_ONLY=1` | Skips every task that writes (save toggles, create and delete posting). |

When a user class stops, Locust also logs a `StopUser` traceback after the error message. That traceback is expected.

## Seed demo accounts (local only)

`seed_demo_data` creates demo employers (`alice`, `frank`, `grace`, `heidi`, `ivan`, `judy`), candidates (`worker1`, ...), postings and applications. All demo accounts share the password `password123`. Because that password is well known, **the command refuses to run unless `DJANGO_DEBUG` is on**. It is idempotent.

```bash
make seed
# same as:
cd src && DJANGO_DEBUG=true uv run python manage.py migrate --noinput
cd src && DJANGO_DEBUG=true PYTHONUTF8=1 uv run python manage.py seed_demo_data
```

Start the dev server (SQLite, `src/db.sqlite3`) on port 8181:

```bash
cd src && DJANGO_DEBUG=true uv run python manage.py runserver 127.0.0.1:8181
```

On staging, create dedicated load-test accounts (one candidate, one employer) with strong passwords. Do not use the demo accounts there.

## Run

Locust is in the `loadtest` dependency group. Run every command from the repository root.

### Local headless smoke test

```bash
export LOADTEST_CANDIDATE_USERNAME=worker1 LOADTEST_CANDIDATE_PASSWORD=password123
export LOADTEST_EMPLOYER_USERNAME=alice LOADTEST_EMPLOYER_PASSWORD=password123
uv run --group loadtest locust -f loadtests/locustfile.py --host http://127.0.0.1:8181 --headless -u 10 -r 2 -t 1m --csv loadtests/results/local
```

This writes `loadtests/results/local_stats.csv`, `_stats_history.csv`, `_failures.csv` and `_exceptions.csv`. The exit code is non-zero when any request failed.

### Staging, with the web UI on port 8089

```bash
export LOADTEST_CANDIDATE_USERNAME=... LOADTEST_CANDIDATE_PASSWORD=...
export LOADTEST_EMPLOYER_USERNAME=... LOADTEST_EMPLOYER_PASSWORD=...
uv run --group loadtest locust -f loadtests/locustfile.py --host https://staging.requester.example --web-port 8089
# open http://localhost:8089, choose users and spawn rate, then start
```

A host that does not contain `staging` needs `LOADTEST_ALLOW_HOST=<that exact host>`. The guard checks the host again when the test starts, so a host typed into the web UI is checked as well. On a staging server that runs over plain HTTP with `SECURE_COOKIES` on (the default when `DEBUG` is off), the session and CSRF cookies are never sent back, so every login fails. Use HTTPS on staging.

### Distributed (one master, N workers)

```bash
# master (holds the web UI or runs headless and collects the stats)
uv run --group loadtest locust -f loadtests/locustfile.py --master --host https://staging.requester.example \
    --headless -u 200 -r 10 -t 10m --expect-workers 4 --csv loadtests/results/staging

# each worker (same machine or others; the LOADTEST_* variables must be set on every worker)
uv run --group loadtest locust -f loadtests/locustfile.py --worker --master-host <master-ip>
```

## Read the results in Grafana and Loki

- **Prometheus/Grafana**: watch the Django dashboards (request rate, latency percentiles by view, 5xx rate, DB query time) for the time window of the run.
- **Loki** (Grafana, Explore): `request_id` is a field inside the JSON log line, not a label, so filter it after `| json`:

  ```logql
  {service="web"} | json | request_id=~"loadtest-.*"
  ```

  The slowest load-test requests:

  ```logql
  {service="web"} | json | request_id=~"loadtest-.*" | duration_ms > 500
  ```

  p95 latency by route:

  ```logql
  quantile_over_time(0.95, {service="web"} | json | request_id=~"loadtest-.*" | unwrap duration_ms [1m]) by (path)
  ```

- Compare these numbers with Locust's `*_stats.csv` (client-side timings, which include network and redirects).

## Results directory

`loadtests/results/` holds local run output and must not be committed. Add this to the root `.gitignore`:

```gitignore
# Locust load test output
loadtests/results/
```
