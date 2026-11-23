#!/bin/sh
# Creates (or updates) the read-only MariaDB user Logstash reads with.
#
# Least privilege: SELECT on the tables the pipelines read, and on sensitive
# tables only the columns they need. Names, e-mails, phone numbers, resumes,
# cover letters, notes, password hashes and sessions cannot be read at all.
# Runs as root in the one-shot `analytics-db-user` service (docker-compose.analytics.yaml).
set -eu
: "${DB_NAME:?}" "${ANALYTICS_DB_USER:?}" "${ANALYTICS_DB_PASSWORD:?}" "${MARIADB_ROOT_PASSWORD:?}"

# Both values are written into SQL: allow only safe characters.
case "$ANALYTICS_DB_USER$ANALYTICS_DB_PASSWORD$DB_NAME" in
    *[!A-Za-z0-9_.-]*) echo "ANALYTICS_DB_USER, ANALYTICS_DB_PASSWORD and DB_NAME may only use A-Z a-z 0-9 _ . -" >&2; exit 1 ;;
esac

u="'$ANALYTICS_DB_USER'@'%'"
mariadb -h "${DB_HOST:-db}" -u root -p"$MARIADB_ROOT_PASSWORD" "$DB_NAME" <<SQL
CREATE USER IF NOT EXISTS $u IDENTIFIED BY '$ANALYTICS_DB_PASSWORD';
ALTER USER $u IDENTIFIED BY '$ANALYTICS_DB_PASSWORD';
REVOKE ALL PRIVILEGES, GRANT OPTION FROM $u;
GRANT SELECT ON employers_jobposting TO $u;
GRANT SELECT ON employers_jobposting_skills TO $u;
GRANT SELECT ON employers_skill TO $u;
GRANT SELECT ON candidates_candidate_skills TO $u;
GRANT SELECT ON candidates_jobsearch TO $u;
GRANT SELECT ON candidates_jobsearch_skills TO $u;
GRANT SELECT ON candidates_savedposting TO $u;
GRANT SELECT ON analytics_deletedrow TO $u;
GRANT SELECT (id, user_id, name, industry, size, city, created_at, updated_at)
    ON employers_employer TO $u;
GRANT SELECT (id, user_id, city, experience_years, education_level, preferred_work_mode,
              is_open_to_work, language, created_at, updated_at)
    ON candidates_candidate TO $u;
GRANT SELECT (id, candidate_id, posting_id, status, ai_provider, applied_at, updated_at)
    ON applications_application TO $u;
GRANT SELECT (id, application_id, from_status, to_status, actor_id, created_at)
    ON applications_applicationevent TO $u;
SQL
echo "Read-only user $ANALYTICS_DB_USER is ready."
