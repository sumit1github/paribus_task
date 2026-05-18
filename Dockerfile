FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Collect static at build time so WhiteNoise can serve them in production.
# SECRET_KEY is required by Django even for collectstatic, hence the dummy value.
RUN DJANGO_SETTINGS_MODULE=paribus.settings SECRET_KEY=build-time-dummy \
    python manage.py collectstatic --noinput

EXPOSE 8000
