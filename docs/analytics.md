# Analytics: Elasticsearch, Logstash and Kibana

A read-only copy of the site's business data for the data team. It answers questions like "which jobs do people search for?", "which skills are in demand?" and "how fast do employers answer?". The web app never reads it, and does not even need it to run.

```
MariaDB ──(Logstash, every minute, read-only user)──> Elasticsearch ──> Kibana (dashboard)
   ▲
   └─ Django writes the data, plus one "deleted" row per delete (analytics.DeletedRow)
```

## Run it

```bash
make docker-up        # or perf-up / your server stack: the app with MariaDB
make analytics-up     # Elasticsearch + Logstash + Kibana on top of it
```

| What | Where |
|---|---|
| Dashboard | http://localhost:5601 → Dashboards → **Requester: jobs and searches** |
| Explore raw documents | Kibana → Discover (pick a data view) |
| Elasticsearch API | http://localhost:9200 |
| Documents per index | `make analytics-status` |
| Stop | `make analytics-down` (the app keeps running) |
| Copy everything again | `make analytics-resync` |

- **Bound to the host only:** both UIs are on 127.0.0.1, and security is off in Elasticsearch and Kibana. Don't expose them as they are.
- **Matching the running stack:** `make analytics-up` assumes the dev stack is running. For another stack, pass the same compose files that stack was started with, or its containers get recreated:
  - `ANALYTICS_BASE="-f docker-compose.yaml"` on a server
  - `ANALYTICS_BASE="-f docker-compose.yaml -f docker-compose.perf.yaml"` for `perf-up`

## How fresh is it?

| Data | Updated |
|---|---|
| New and changed rows | Within about a minute |
| Deleted rows | Within about a minute |
| Counts on a posting (`applications`, `saves`), `is_open` after a deadline passes, candidate skill changes | Every night at 03:00 UTC (full refresh) |
| `requester-daily-stats` | Every 15 minutes, one document per UTC day |

- **Rows Django doesn't timestamp:** bulk inserts with backdated timestamps (`seed_fake_data`), or raw SQL edits, can be missed by the minute sync. The nightly run catches them, or run `make analytics-resync`.
- **History starts when analytics starts:** `requester-daily-stats` can't be rebuilt for the past.

## Privacy

Logstash connects as a MariaDB user that can only `SELECT` the columns the copy needs (`elastic/db/create_analytics_user.sh`). It **cannot read**:

- names, e-mails, phone numbers, addresses or birth dates
- resumes, cover letters or employer notes
- AI summaries
- password hashes or sessions

Candidates are copied without any identity: only city, experience, education, work mode, language and skills.

## Indices and fields

Every index is named `requester-*`. Its field types are in `elastic/logstash/templates/`, and the SQL that fills it is in `elastic/logstash/sql/`.

### `requester-postings`: one document per job posting (now)

| Field | Type | Meaning |
|---|---|---|
| `id` | long | Posting id (same as in the app and the admin) |
| `title`, `employer_name` | keyword (+ `.text`) | Exact values to group by; `.text` for full-text search |
| `description` | text | |
| `location`, `country`, `work_mode`, `employment_type`, `seniority` | keyword | |
| `salary_min`, `salary_max`, `salary_currency` | long / keyword | |
| `deadline`, `created_at`, `changed_at` | date | |
| `is_active`, `is_open` | boolean | `is_open`: active and deadline not passed (UTC) |
| `employer_id`, `employer_industry`, `employer_size`, `employer_city` | | |
| `skills` | keyword (array) | |
| `applications`, `saves` | integer | Counts, refreshed nightly |

### `requester-searches`: every search on the candidate job list

| Field | Type | Meaning |
|---|---|---|
| `query` | keyword (+ `.text`) | Lower-cased, spaces collapsed |
| `location`, `work_mode`, `employment_type`, `seniority`, `language` | keyword | Filters used, and the site language |
| `skills` | keyword (array) | Skills filtered on |
| `min_salary` | long | |
| `remote_only` | boolean | |
| `results` | integer | Jobs found |
| `zero_results` | boolean | Nothing found: a job people want that the site doesn't have |
| `created_at` | date | |

Who searched is not stored. Paging through results and changing only the sort order don't count as new searches.

### `requester-applications`: one document per application (current status)

| Field | Type |
|---|---|
| `status` | keyword: `pending`, `in_review`, `shortlisted`, `accepted`, `rejected`, `withdrawn` |
| `applied_at`, `changed_at` | date |
| `posting_id`, `posting_title`, `work_mode`, `employment_type`, `seniority`, `posting_city` | |
| `employer_id`, `employer_name` | |
| `candidate_city`, `candidate_experience_years`, `candidate_education` | No identity |
| `has_ai_summary` | boolean |
| `status_changes` | integer |

### `requester-application-events`: every status change

`application_id`, `posting_id`, `employer_name`, `from_status`, `to_status`, `created_at`, `hours_since_applied` (float), and `actor` (`employer`, `candidate`, `system` or `staff`).

### `requester-candidates`: the supply side (now, no identity)

`city`, `experience_years`, `education_level`, `preferred_work_mode`, `is_open_to_work`, `language`, `skills`, `created_at`, `changed_at`.

### `requester-daily-stats`: totals per UTC day

`day`, `measured_at`, `postings`, `open_postings`, `hiring_employers`, `employers`, `candidates`, `open_to_work_candidates`, `applications_in_progress`.

## Example questions

In Kibana → Discover, with KQL:

| Question | Data view | KQL |
|---|---|---|
| Searches that found nothing | Job searches | `zero_results : true` |
| Remote jobs that ask for Python | Job postings | `is_open : true and work_mode : "remote" and skills : "Python"` |
| Rejections by employers | Application status changes | `to_status : "rejected" and actor : "employer"` |

With ES|QL (Kibana → Discover → ES|QL, or the `_query` API):

```esql
// The 20 most searched words in the last 7 days, and how often they found nothing
FROM requester-searches
| WHERE created_at > NOW() - 7 days AND query IS NOT NULL
| STATS searches = COUNT(*), no_results = COUNT(CASE(zero_results, 1, null)) BY query
| SORT searches DESC
| LIMIT 20
```

```esql
// Skills: open jobs that ask for them vs. candidates who have them
FROM requester-postings
| WHERE is_open
| MV_EXPAND skills
| STATS jobs = COUNT(*) BY skills
| SORT jobs DESC
| LIMIT 15
```

```esql
// Median hours until an employer first answers, per company
FROM requester-application-events
| WHERE from_status == "pending" AND actor == "employer"
| STATS median_hours = MEDIAN(hours_since_applied), answers = COUNT(*) BY employer_name
| WHERE answers >= 10
| SORT median_hours
```

## Change something

- **Add a field:**
  1. Add it to the SQL in `elastic/logstash/sql/` and to the index's template in `elastic/logstash/templates/`. If it holds personal data, think twice; it may also need a column grant in `elastic/db/create_analytics_user.sh`.
  2. Rebuild with `make analytics-up`, then run `make analytics-resync`.
  3. A field whose type changes needs the index deleted first: `curl -X DELETE localhost:9200/requester-<name>`, then resync.
- **Change the dashboard:** edit `elastic/kibana/build_saved_objects.py`, run it, then run `make analytics-up`. That imports the dashboard again and overwrites changes made in the Kibana UI, so save your own dashboards under a different name.
- **Add an index:** a new SQL file, pipeline and template, an entry in `elastic/logstash/config/pipelines.yml`, and, if its rows can be deleted, its model in `INDEX_OF` in `src/analytics/signals.py`.
