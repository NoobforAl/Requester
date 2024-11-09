FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

RUN apt-get update && \
    apt-get install -y \
    pkg-config libmariadb-dev-compat \
    libmariadb-dev build-essential \
    graphviz graphviz-dev make gcc && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

RUN cd src/ && \
    python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["make", "PYTHON=python", "deploy"]