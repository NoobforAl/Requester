FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && \
    apt-get install -y \
    pkg-config libmariadb-dev-compat \
    libmariadb-dev build-essential \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
    gettext \
    make gcc curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# uv from PyPI (pinned), so the build needs no access to ghcr.io.
RUN pip install --no-cache-dir uv==0.12.9

# Keep the virtualenv outside /app, because docker-compose bind-mounts the
# project directory over /app.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV UV_LINK_MODE=copy
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml uv.lock .python-version /app/
RUN uv sync --frozen --no-dev

EXPOSE 8000
