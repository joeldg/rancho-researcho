# syntax=docker/dockerfile:1
# @spec[RANCHO_DEPLOYMENT.md#requirements] req 6: pinned base image, locked
# dependencies, non-root runtime user, and no secrets or .env baked into the image.
FROM python:3.12-slim-bookworm

# Pinned uv for reproducible, locked dependency resolution.
COPY --from=ghcr.io/astral-sh/uv:0.8.13 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install locked runtime dependencies first for better layer caching. The dev
# group (pytest, ruff) is intentionally excluded from the runtime image.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# The runtime image includes Alembic's configuration and immutable migrations so
# operators can upgrade the durable store without mounting source from the host.
# @spec[RANCHO_ASYNC_RESEARCH.md#architecture-and-storage]
COPY alembic.ini ./
COPY migrations ./migrations

# Install the application itself against the locked environment.
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Drop privileges: the runtime user owns nothing writable and holds no secrets.
RUN useradd --create-home --uid 10001 rancho
USER rancho

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
CMD ["uvicorn", "rancho.main:app", "--host", "0.0.0.0", "--port", "8000"]
