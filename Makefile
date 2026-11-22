# Requester: developer and deploy commands.
#
#   make dev     run the dev server on SQLite (no Docker, no services)
#   make fix     format everything, run every linter, type check and the tests
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
PORT   ?= 8000
MANAGE := cd $(SRC) && $(PYTHON) manage.py

export PYTHON

# Docker: the base file is production-like, the dev file adds DEBUG, mock data and
# a known admin login. `make docker-up` uses both.
COMPOSE     := docker compose
COMPOSE_DEV := docker compose -f docker-compose.yaml -f docker-compose.dev.yaml

.DEFAULT_GOAL := help
.PHONY: help install dev seed migrate migrations superuser shell check \
        format lint typecheck test audit fix \
        clean clean-all docker-up docker-down docker-clean \
        deploy deploy-dev setup_celery ensure_superuser collectstatic test-mariadb database_diagram

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  make %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ---------------------------------------------------------------- setup
install: ## Install dependencies (runtime + dev tools)
	uv sync

# ---------------------------------------------------------- development
dev: ## Run the dev server on SQLite (change with PORT=8001 HOST=0.0.0.0)
	@echo "Dev server on SQLite (src/db.sqlite3) at http://$(HOST):$(PORT), tasks run inline, no services needed"
	cd $(SRC) && DJANGO_DEBUG=true $(PYTHON) manage.py migrate --noinput
	cd $(SRC) && DJANGO_DEBUG=true $(PYTHON) manage.py runserver $(HOST):$(PORT)

seed: ## Fill the SQLite dev database with mock data
	cd $(SRC) && export DJANGO_DEBUG=true PYTHONUTF8=1 && \
	  sh ./scripts/insert_offers.sh && sh ./scripts/insert_workers.sh && \
	  sh ./scripts/insert_tags.sh && sh ./scripts/insert_jobs.sh && \
	  sh ./scripts/insert_applications.sh

migrate: ## Apply database migrations
	$(MANAGE) migrate --noinput

migrations: ## Create new migrations after a model change
	$(MANAGE) makemigrations

superuser: ## Create an admin user (interactive)
	$(MANAGE) createsuperuser

shell: ## Open the Django shell
	$(MANAGE) shell_plus

check: ## Django system checks and "are migrations missing?"
	cd $(SRC) && DJANGO_DEBUG=true $(PYTHON) manage.py check
	cd $(SRC) && DJANGO_DEBUG=true $(PYTHON) manage.py makemigrations --check --dry-run

# -------------------------------------------------- quality: lint, test
format: ## Format all Python code (ruff, import order, unused imports)
	$(RUN) ruff check --select I,UP,F401 --fix .
	$(RUN) ruff format .

lint: ## Run every linter (ruff, flake8, djlint, bandit, vulture)
	$(RUN) ruff check .
	$(RUN) flake8 $(SRC)
	$(RUN) djlint $(SRC)/templates --lint
	PYTHONUTF8=1 $(RUN) bandit -c pyproject.toml -r $(SRC) -ll -q
	$(RUN) vulture

typecheck: ## Static type check (mypy + django-stubs)
	cd $(SRC) && $(RUN) mypy .

test: ## Run the test suite
	$(RUN) pytest

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
docker-up: ## Build and start the dev stack (MariaDB, Redis, Elasticsearch, Ollama)
	mkdir -p es_data mariadb_data redis_data ollama_data
	$(COMPOSE_DEV) down
	$(COMPOSE_DEV) up -d --build

docker-down: ## Stop the dev stack
	$(COMPOSE_DEV) down

docker-clean: ## Stop the stack and delete its data folders (asks sudo)
	$(COMPOSE_DEV) down
	sudo rm -rf es_data mariadb_data redis_data ollama_data

test-mariadb: ## Run the tests against a real MariaDB (starts and stops the compose service)
	$(COMPOSE) up -d --wait mariadb
	DB_HOST=127.0.0.1 $(RUN) pytest --ds=requester.settings_mariadb_test --create-db; 	  status=$$?; $(COMPOSE) stop mariadb; exit $$status

# These run INSIDE the containers (see docker-compose.yaml / docker-compose.dev.yaml).
# deploy: production-like (gunicorn, SECRET_KEY and ALLOWED_HOSTS required, no demo data).
deploy: migrate create_es_fields ensure_superuser collectstatic
	@echo "Starting gunicorn"
	cd $(SRC) && $(RUN) gunicorn -w 4 --bind 0.0.0.0:8000 requester.wsgi:application

# deploy-dev: Django dev server, mock data, and an admin from DJANGO_SUPERUSER_*.
deploy-dev: migrate create_es_fields insert_mock_data ensure_superuser
	@echo "Starting the dev server"
	$(MANAGE) runserver 0.0.0.0:8000

setup_celery: migrate create_es_fields
	cd $(SRC) && $(CELERY) -A requester worker --loglevel=info

create_es_fields: migrate
	$(MANAGE) search_index --rebuild -f

collectstatic:
	$(MANAGE) collectstatic --noinput

# Demo accounts have a known password: the commands refuse to run unless DEBUG is on.
insert_mock_data: migrate
	cd $(SRC) && export PYTHONUTF8=1 && sh ./scripts/insert_offers.sh && 	  sh ./scripts/insert_workers.sh && sh ./scripts/insert_tags.sh && 	  sh ./scripts/insert_jobs.sh && sh ./scripts/insert_applications.sh

# Creates the admin only when DJANGO_SUPERUSER_PASSWORD is set; never resets an existing one.
ensure_superuser: migrate
	$(MANAGE) ensure_superuser

database_diagram: ## Draw the model diagram (needs `uv sync --group diagram`)
	$(MANAGE) graph_models -a -g -o ../test.png
