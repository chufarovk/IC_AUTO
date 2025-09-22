## Stage 1: Base image shared by all stages
FROM python:3.11-slim as base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    POETRY_VERSION=1.8.2 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"
WORKDIR /app

## Stage 2: Builder for dependencies
FROM base as builder

RUN apt-get update && apt-get install --no-install-recommends -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml poetry.lock ./
# Install only runtime deps for the API app
RUN poetry install --no-root --without dev

## Stage 3: Final lightweight runtime image
FROM base as production

RUN addgroup --system app && adduser --system --group app

# Copy the prepared virtualenv
COPY --from=builder --chown=app:app /app/.venv ./.venv

# Ensure asyncpg is always available inside the venv
RUN ./.venv/bin/pip install asyncpg

# Copy Alembic config and migrations (required for runtime migrations)
COPY --chown=app:app ./alembic.ini ./alembic.ini
COPY --chown=app:app ./migrations ./migrations

# Copy application code
COPY --chown=app:app ./app ./app

# Copy prestart and start scripts
COPY --chown=app:app ./prestart.py ./prestart.py
COPY --chown=app:app ./start.sh ./start.sh
RUN chmod +x ./start.sh

USER app

# Run prestart script then start Uvicorn
CMD ["sh", "-c", "./.venv/bin/python prestart.py && exec ./.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 80"]

