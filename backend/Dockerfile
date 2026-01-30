FROM python:3.12-slim AS build

ENV POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install poetry

WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root --no-interaction --no-ansi

COPY run.py ./
COPY app ./app

# Runtime image
FROM python:3.12-slim

# netcat-openbsd is used by the setup job to find whether the database has started up.

RUN apt-get update && \
    apt-get install -y --no-install-recommends tini netcat-openbsd && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=build /app /app

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production

EXPOSE 3201

ENTRYPOINT ["tini", "--"]

CMD ["python", "run.py"]
