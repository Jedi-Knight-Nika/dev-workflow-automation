FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.11.30 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --extra dev --no-install-project

FROM base AS api-system
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

FROM api-system AS api
COPY . .
RUN uv sync --frozen --extra dev
EXPOSE 8000
CMD ["sh", "-c", ".venv/bin/alembic upgrade head && exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000"]

FROM node:22-slim AS node-runtime

FROM base AS worker-system
COPY --from=node-runtime /usr/local/ /usr/local/
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

FROM worker-system AS worker
COPY . .
RUN uv sync --frozen --extra dev
CMD [".venv/bin/python", "-m", "app.scheduler_runner"]

# Built separately; never started as a long-running Compose service.
FROM worker-system AS developer-runner
RUN uv sync --frozen --extra harness --no-install-project \
    && groupadd --gid 10001 runner \
    && useradd --uid 10001 --gid 10001 --create-home runner \
    && mkdir /workspace \
    && chown runner:runner /workspace
COPY . .
RUN uv sync --frozen --extra harness
USER 10001:10001
WORKDIR /workspace
CMD ["/app/.venv/bin/python", "-m", "app.agent_runtime.infrastructure.runner", "/run/control/task.json"]
