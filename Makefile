# Requester: developer and deploy commands.
#
#   make dev     run the dev server on SQLite (no Docker, no services)
#   make fix     format everything, run every linter, type check and the tests
#   make seed    fill the dev database with demo employers, jobs and candidates
#   make i18n    extract translatable text into src/locale (runs in Docker: needs gettext)
#   make diagrams  redraw the PlantUML diagrams in diagram/ (runs in Docker)
#   make clean   remove caches and build artifacts
#   make help    list every command
#
# RUN is how Python tools are started. Locally that is `uv run`; the Docker image
# already has the virtualenv on PATH, so docker compose passes `RUN=`.
RUN    ?= uv run
PYTHON ?= $(RUN) python
CELERY ?= $(RUN) celery
SRC    := src
HOST   ?= 127.0.0.1
PORT   ?= 8181
MANAGE := cd $(SRC) && $(PYTHON) manage.py

export PYTHON

# Docker: the base file is production-like, the dev file adds DEBUG, mock data and
# a known admin login. `make docker-up` uses both.
COMPOSE     := docker compose
COMPOSE_DEV := docker compose -f docker-compose.yaml -f docker-compose.dev.yaml
COMPOSE_MON := docker compose -f docker-compose.yaml -f docker-compose.monitoring.yaml
# Everything for local development: dev overrides + monitoring + traffic generator.
# monitoring/dev-defaults.env gives dev-only METRICS_TOKEN / GRAFANA_ADMIN_PASSWORD;
# .env (if present) is loaded after it and wins.
COMPOSE_ALL := docker compose --env-file monitoring/dev-defaults.env $(if $(wildcard .env),--env-file .env) 	-f docker-compose.yaml -f docker-compose.dev.yaml -f docker-compose.monitoring.yaml --profile loadgen
# Production-like stack with a CPU/memory cap on every service (benchmarks, load tests).
COMPOSE_PERF := docker compose -f docker-compose.yaml -f docker-compose.perf.yaml

.DEFAULT_GOAL := help
.PHONY: help install dev seed seed-fake insert_fake_data migrate migrations superuser shell check \
        format lint typecheck test bench bench-check loadtest audit fix \
        clean clean-all docker-up docker-down docker-clean monitoring-up monitoring-down docker-bench docker-bench-check docker-pull dev-all dev-all-down \
        perf-up perf-down perf-load perf-bench deploy-perf \
        deploy deploy-dev setup_celery setup_scheduler ensure_superuser collectstatic \
        compilemessages import_legacy_data insert_mock_data test-mariadb database_diagram \
        i18n i18n-compile i18n-check diagrams

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  make %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ---------------------------------------------------------------- setup
install: ## Install dependencies (runtime + dev tools)
	uv sync

# ---------------------------------------------------------- development
dev: ## Run the dev server on SQLite (change with PORT=8001 HOST=0.0.0.0)
	@echo "Dev server on SQLite (src/db.sqlite3) at http://$(HOST):$(PORT), tasks run inline, no services needed"
	cd $(SRC) && DJANGO_DEBUG=true $(PYTHON) manage.py migrate --noinput
	cd $(SRC) && DJANGO_DEBUG=true $(PYTHON) manage.py import_legacy_data
	$(PYTHON) scripts/compile_messages.py
	cd $(SRC) && DJANGO_DEBUG=true $(PYTHON) manage.py runserver $(HOST):$(PORT)

seed: ## Fill the SQLite dev database with demo employers, jobs, candidates and applications
	cd $(SRC) && DJANGO_DEBUG=true PYTHONUTF8=1 $(PYTHON) manage.py seed_demo_data

seed-fake: ## Fill the SQLite dev database with lots of Faker data (fake_* users; FAKE_ARGS="--seed 7 --wipe-fake")
	cd $(SRC) && DJANGO_DEBUG=true PYTHONUTF8=1 $(PYTHON) manage.py seed_fake_data $(FAKE_ARGS)

migrate: ## Apply database migrations
	$(MANAGE) migrate --noinput

migrations: ## Create new migrations after a model change
	$(MANAGE) makemigrations

superuser: ## Create an admin user (interactive)
	$(MANAGE) createsuperuser

shell: ## Open the Django shell
	$(MANAGE) shell_plus

import_legacy_data: ## Copy data from the pre-rename offer_*/worker_* tables (no-op on a fresh database)
	$(MANAGE) import_legacy_data

check: ## Django system checks and "are migrations missing?"
	cd $(SRC) && DJANGO_DEBUG=true $(PYTHON) manage.py check
	cd $(SRC) && DJANGO_DEBUG=true $(PYTHON) manage.py makemigrations --check --dry-run

# -------------------------------------------------- quality: lint, test
format: ## Format all Python code (ruff, import order, unused imports)
	$(RUN) ruff check --select I,UP,F401 --fix .
	$(RUN) ruff format .

lint: ## Run every linter (ruff, flake8, djlint, bandit, vulture)
	$(RUN) ruff check . --fix
	$(RUN) flake8 $(SRC)
	$(RUN) djlint $(SRC)/templates --lint
	PYTHONUTF8=1 $(RUN) bandit -c pyproject.toml -r $(SRC) -ll -q
	$(RUN) vulture

typecheck: ## Static type check (mypy + django-stubs)
	cd $(SRC) && $(RUN) mypy .

test: ## Run the test suite
	$(RUN) pytest

bench: ## Run the benchmarks for real and save the result under .benchmarks/
	$(RUN) pytest src/tests/benchmarks --benchmark-enable --benchmark-only --benchmark-autosave

bench-check: ## Compare with the last saved run; fail if any median is 20% slower
	$(RUN) pytest src/tests/benchmarks --benchmark-enable --benchmark-only --benchmark-compare --benchmark-compare-fail=median:20%

loadtest: ## Headless Locust smoke against the local dev server (needs LOADTEST_* env vars; never production)
	uv run --group loadtest locust -f loadtests/locustfile.py --host http://$(HOST):$(PORT) --headless -u 10 -r 2 -t 1m --csv loadtests/results/local

audit: ## Scan dependencies for known vulnerabilities (needs network)
	$(RUN) pip-audit

fix: format lint typecheck test check ## Format everything, then run all linters, type check, tests and Django checks
	@echo "All good."

# --------------------------------------------------------------- cleaning
clean: ## Remove caches, bytecode and build artifacts
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache \
	  -o -name .ruff_cache -o -name htmlcov \) -not -path "./.venv/*" -prune -exec rm -rf {} +
	rm -rf $(SRC)/staticfiles .coverage coverage.xml test.png
	@echo "Clean."

clean-all: clean ## clean + remove the virtualenv and the SQLite dev database
	rm -rf .venv $(SRC)/db.sqlite3

# ------------------------------------------------------- docker / deploy
docker-up: ## Build and start the dev stack
	mkdir -p es_data mariadb_data redis_data
	$(COMPOSE_DEV) down
	$(COMPOSE_DEV) up -d --build

docker-down: ## Stop the dev stack
	$(COMPOSE_DEV) down

docker-clean: ## Stop the stack and delete its data folders (asks sudo)
	$(COMPOSE_DEV) down
	sudo rm -rf es_data mariadb_data redis_data

docker-bench: ## Run the benchmarks inside the dev image; results are saved to ./.benchmarks on the host
	$(COMPOSE_ALL) run --rm --no-deps --build web make RUN= bench

docker-bench-check: ## Same, and fail if a median is 20% slower than the last saved Docker run
	$(COMPOSE_ALL) run --rm --no-deps web make RUN= bench-check

docker-pull: ## Pull every image used by the full stack (base, dev, monitoring, loadgen) ahead of time
	$(COMPOSE_ALL) pull --ignore-buildable

dev-all: ## Dev stack + Faker data + monitoring + live load (Grafana :3000 admin/admin, Jaeger :16686)
	mkdir -p es_data mariadb_data redis_data
	$(COMPOSE_ALL) up -d --build
	@echo "App http://localhost:8000  Grafana http://localhost:3000  Prometheus http://localhost:9090"
	@echo "Jaeger http://localhost:16686  Loki http://localhost:3100  MailHog http://localhost:8025"
	@echo "Seeding runs on first start; the load generator starts once web is healthy. Stop with: make dev-all-down"

dev-all-down: ## Stop the dev-all stack
	$(COMPOSE_ALL) down

perf-up: ## Start the capped, production-like stack (gunicorn, DEBUG off, demo data) on :8001
	mkdir -p es_data mariadb_data redis_data
	$(COMPOSE_PERF) up -d --build --wait

perf-load: ## Locust load test against perf-up (PERF_USERS=150 PERF_RUN_TIME=3m); CSV in loadtests/results/
	mkdir -p loadtests/results
	$(COMPOSE_PERF) --profile perf-load run --rm loadtest

perf-bench: ## Run the benchmarks inside the capped web container; saved to ./.benchmarks
	$(COMPOSE_PERF) run --rm --no-deps --build web make RUN= bench

perf-down: ## Stop the perf stack
	$(COMPOSE_PERF) --profile perf-load down

monitoring-up: ## Start the stack with Prometheus, Grafana, Loki and exporters (needs METRICS_TOKEN, GRAFANA_ADMIN_PASSWORD)
	mkdir -p es_data mariadb_data redis_data
	$(COMPOSE_MON) up -d --build

monitoring-down: ## Stop the monitoring stack
	$(COMPOSE_MON) down

test-mariadb: ## Run the tests against a real MariaDB (starts and stops the compose service)
	$(COMPOSE) up -d --wait db
	DB_HOST=127.0.0.1 $(RUN) pytest --ds=requester.settings_mariadb_test --create-db; 	  status=$$?; $(COMPOSE) stop db; exit $$status

# These run INSIDE the containers (see docker-compose.yaml / docker-compose.dev.yaml).
# deploy: production-like (gunicorn, SECRET_KEY and ALLOWED_HOSTS required, no demo data).
deploy: migrate import_legacy_data compilemessages create_es_fields ensure_superuser collectstatic
	@echo "Starting gunicorn"
	@# Prometheus multiprocess mode: start every run with an empty metrics directory
	@# (emptied, not removed: in compose it is a tmpfs mount point).
	if [ -n "$$PROMETHEUS_MULTIPROC_DIR" ]; then mkdir -p "$$PROMETHEUS_MULTIPROC_DIR" && find "$$PROMETHEUS_MULTIPROC_DIR" -mindepth 1 -delete; fi
	@# Workers, bind address and recycling live in src/gunicorn.conf.py.
	cd $(SRC) && $(RUN) gunicorn requester.wsgi:application

# deploy-perf: `deploy` (gunicorn, DEBUG off) on top of the demo and Faker data, which
# can only be seeded with DEBUG on. Used by docker-compose.perf.yaml only.
deploy-perf:
	DJANGO_DEBUG=true $(MAKE) insert_mock_data insert_fake_data
	$(MAKE) deploy

# deploy-dev: Django dev server, mock data, and an admin from DJANGO_SUPERUSER_*.
# Seed first, then rebuild the search index, so bulk-inserted rows are always indexed.
deploy-dev: migrate import_legacy_data compilemessages insert_mock_data insert_fake_data create_es_fields ensure_superuser
	@echo "Starting the dev server"
	if [ -n "$$PROMETHEUS_MULTIPROC_DIR" ]; then mkdir -p "$$PROMETHEUS_MULTIPROC_DIR" && find "$$PROMETHEUS_MULTIPROC_DIR" -mindepth 1 -delete; fi
	$(MANAGE) runserver 0.0.0.0:8000

setup_celery: migrate compilemessages create_es_fields
	cd $(SRC) && $(CELERY) -A requester worker -E --loglevel=info

# Celery beat: sends the daily and weekly job-alert digests (CELERY_BEAT_SCHEDULE).
setup_scheduler: migrate
	cd $(SRC) && $(CELERY) -A requester beat --loglevel=info --schedule /tmp/celerybeat-schedule

create_es_fields: migrate
	$(MANAGE) search_index --rebuild -f

collectstatic:
	$(MANAGE) collectstatic --noinput

# Demo accounts have a known password: the commands refuse to run unless DEBUG is on.
insert_mock_data: migrate
	cd $(SRC) && PYTHONUTF8=1 $(PYTHON) manage.py seed_demo_data

# Faker volume data (fake_* users, unusable passwords): refuses unless DEBUG is on.
insert_fake_data: migrate
	cd $(SRC) && PYTHONUTF8=1 $(PYTHON) manage.py seed_fake_data $(FAKE_ARGS)

# Needs GNU gettext (installed in the Docker image): compiles src/locale/*/django.po.
compilemessages:
	$(MANAGE) compilemessages

# Creates the admin only when DJANGO_SUPERUSER_PASSWORD is set; never resets an existing one.
ensure_superuser: migrate
	$(MANAGE) ensure_superuser

database_diagram: ## Draw the model diagram (needs `uv sync --group diagram`)
	$(MANAGE) graph_models -a -g -o ../test.png

# ---------------------------------------------------------- languages (fa en ar de fr ru zh-hans)
# `make i18n` re-reads templates and Python for translatable text and merges it into the
# .po files (GNU gettext lives in the Docker image, not on a Windows dev machine). Fill
# the new empty msgstr entries, then `make i18n-check`.
i18n: ## Extract translatable text into src/locale/*/LC_MESSAGES/django.po (via Docker)
	$(COMPOSE) run --rm --no-deps -e DJANGO_DEBUG=true -w /app/src web 	  python manage.py makemessages --all --no-location --no-wrap -e html,py 	  --ignore 'staticfiles/*' --ignore '.venv/*'

i18n-compile: ## Compile the .po files to .mo without GNU gettext (pure Python, for local use)
	$(RUN) python scripts/compile_messages.py

i18n-check: ## Fail on missing, fuzzy or placeholder-breaking translations
	$(RUN) pytest src/requester/tests.py -k "catalog"

# ------------------------------------------------------------------ diagrams
# PlantUML runs in Docker, so no Java/Graphviz install is needed.
diagrams: ## Redraw diagram/*.png from diagram/*.puml (via Docker)
	docker run --rm -v "$(CURDIR)/diagram:/data" -w /data plantuml/plantuml:1.2024.7 -tpng /data/*.puml
