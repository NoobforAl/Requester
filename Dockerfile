# syntax=docker/dockerfile:1.7
#
# Two stages:
#   builder  compilers + headers, resolves the virtualenv with uv (cached between builds)
#   runtime  only the shared libraries the app needs, the venv, the code, a non-root user
#
# Production builds the runtime deps only. docker-compose.dev.yaml passes
# UV_SYNC_ARGS="--dev" (Faker for the fake data, pytest-benchmark, debug toolbar, silk).

ARG PYTHON_IMAGE=python:3.12.16-slim-trixie

# --------------------------------------------------------------------------- builder
FROM ${PYTHON_IMAGE} AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential pkg-config libmariadb-dev \
    && rm -rf /var/lib/apt/lists/*

# uv from PyPI (pinned), so the build needs no access to ghcr.io.
RUN pip install --no-cache-dir uv==0.12.9

# The venv lives outside /app, because docker-compose bind-mounts the project over /app.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

ARG UV_SYNC_ARGS="--no-dev"
WORKDIR /build
# Only the lock files: the dependency layer is rebuilt only when they change.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=.python-version,target=.python-version \
    uv sync --frozen ${UV_SYNC_ARGS}

# --------------------------------------------------------------------------- runtime
FROM ${PYTHON_IMAGE} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Runtime libraries only: MariaDB client, Pango/HarfBuzz for WeasyPrint PDFs,
# gettext for compilemessages, make (the compose commands), curl (health checks).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libmariadb3 libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
        gettext make curl \
    && rm -rf /var/lib/apt/lists/*

# Fixed uid/gid 1000 so files written to the bind-mounted project (static files,
# compiled translations, resumes) belong to the usual first user on the host.
ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd --gid "${APP_GID}" app \
    && useradd --uid "${APP_UID}" --gid app --create-home --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
# The image is self-contained (compose bind-mounts the project over it in dev).
COPY --chown=app:app . /app

USER app
EXPOSE 8000
CMD ["make", "RUN=", "deploy"]
