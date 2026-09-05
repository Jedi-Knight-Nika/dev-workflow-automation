FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.11.30 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --all-extras --no-install-project
COPY . .
RUN uv sync --frozen --all-extras

FROM base AS api
EXPOSE 8000
CMD ["sh", "-c", ".venv/bin/alembic upgrade head && exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000"]

FROM node:22-slim AS node-runtime

FROM base AS worker
COPY --from=node-runtime /usr/local/ /usr/local/
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*
CMD [".venv/bin/python", "-m", "app.scheduler_runner"]
