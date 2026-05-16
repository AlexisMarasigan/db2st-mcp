# Multi-stage build. Knative Functions normally builds via Cloud Native
# Buildpacks (see deploy/func.yaml); this Dockerfile is the fallback for
# `docker build` and CI smoke tests.

FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install --no-cache-dir uv==0.8.18

WORKDIR /build
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# Build a wheel of the project, then resolve runtime deps into a single
# install prefix at /install. No venv, no editable installs — just a
# clean tree we can COPY into the runtime image.
RUN uv build --wheel --out-dir /wheels \
 && uv export --frozen --no-dev --no-emit-project --format requirements-txt > /tmp/requirements.txt \
 && pip install --no-cache-dir --prefix=/install -r /tmp/requirements.txt \
 && pip install --no-cache-dir --prefix=/install --no-deps /wheels/db2st_mcp-*.whl


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

RUN useradd --create-home --uid 1001 app
USER app
WORKDIR /app

COPY --from=builder /install /usr/local

EXPOSE 8080
CMD ["uvicorn", "db2st_mcp.apps.server.main:app", "--host", "0.0.0.0", "--port", "8080"]
