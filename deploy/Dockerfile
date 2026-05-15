# Multi-stage build for Knative Functions when buildpacks are unavailable.
# Targets a small image so cold starts stay under our budget.

FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN pip install --no-cache-dir uv==0.5.4

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-install-project \
 && uv pip install --system .

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

RUN useradd --create-home --uid 1001 app
USER app
WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

EXPOSE 8080
CMD ["uvicorn", "db2st_mcp.apps.server.main:app", "--host", "0.0.0.0", "--port", "8080"]
