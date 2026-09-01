# Single source of truth for both published image variants:
#   - regular (multi-container, SurrealDB external): default build / --target runtime
#   - single-container (app + SurrealDB):            --target single
# Shared stages below guarantee that fixes (tiktoken pre-cache, env defaults,
# npm retry logic, ...) apply to both variants at once.

# Stage 1: Frontend builder
FROM node:22-slim AS frontend-builder
WORKDIR /app/frontend

# Copy dependency files first to leverage cache
COPY frontend/package.json frontend/package-lock.json ./
ARG NPM_REGISTRY=https://registry.npmjs.org/
RUN npm config set registry ${NPM_REGISTRY} \
 && npm config set fetch-retries 5 \
 && npm config set fetch-retry-mintimeout 20000 \
 && npm config set fetch-retry-maxtimeout 120000
# Retry npm ci to survive transient registry ECONNRESETs, which are common on
# the QEMU-emulated arm64 leg of the multi-arch build.
RUN i=0; until npm ci; do \
      i=$((i+1)); \
      if [ "$i" -ge 5 ]; then echo "npm ci failed after $i attempts"; exit 1; fi; \
      echo "npm ci failed (attempt $i); retrying in 15s"; sleep 15; \
    done

# Copy the rest of the frontend source and build
COPY frontend/ ./
RUN npm run build

# Stage 2: Backend builder
FROM python:3.12-slim-trixie AS backend-builder

# Install build dependencies (uv downloads pre-built wheels for most packages)
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv using the official method
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Set build optimization environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_HTTP_TIMEOUT=120

# Copy dependency files and minimal package structure first for better layer caching
COPY pyproject.toml uv.lock ./
COPY open_notebook/__init__.py ./open_notebook/__init__.py

# Install dependencies (this layer is cached unless dependencies change)
RUN uv sync --frozen --no-dev

# Pre-download tiktoken encoding so the app works offline (issue #264).
# /app/tiktoken-cache is intentionally outside /app/data/ so that volume mounts
# of /app/data (for user data persistence) do not hide the pre-baked encoding.
# config.py reads TIKTOKEN_CACHE_DIR from the environment to pick up this path.
ENV TIKTOKEN_CACHE_DIR=/app/tiktoken-cache
RUN mkdir -p /app/tiktoken-cache && \
    .venv/bin/python -c "import tiktoken; tiktoken.get_encoding('o200k_base')"

# Stage 3: SurrealDB binary (pinned to v2 to match docker-compose.yml; used by the single target only)
FROM surrealdb/surrealdb:v2 AS surreal-binary

# Stage 4: Shared runtime base (everything common to both variants)
FROM python:3.12-slim-trixie AS runtime-base

# Install only runtime system dependencies (no build tools)
# Add Node.js 22.x LTS for running the frontend
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    ffmpeg \
    supervisor \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install uv using the official method
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Keep the regular image usable with an external SurrealDB while also allowing
# single-service PaaS deployments to opt into the pinned embedded server with
# SURREAL_EMBEDDED=true. The default remains external DB mode.
COPY --from=surreal-binary /surreal /usr/local/bin/surreal

WORKDIR /app

# Copy the virtual environment from the backend builder
COPY --from=backend-builder /app/.venv /app/.venv

# Copy the source code
COPY . /app

# Copy pre-downloaded tiktoken encoding from builder (outside /data/ — volume-mount safe)
COPY --from=backend-builder /app/tiktoken-cache /app/tiktoken-cache

# Copy built frontend from standalone output
COPY --from=frontend-builder /app/frontend/.next/standalone /app/frontend/
COPY --from=frontend-builder /app/frontend/.next/static /app/frontend/.next/static
COPY --from=frontend-builder /app/frontend/public /app/frontend/public
COPY --from=frontend-builder /app/frontend/start-server.js /app/frontend/start-server.js

# Ensure uv uses the existing venv without attempting network operations
ENV UV_NO_SYNC=1
ENV VIRTUAL_ENV=/app/.venv
# Point the app at the pre-baked tiktoken encoding (see open_notebook/config.py)
ENV TIKTOKEN_CACHE_DIR=/app/tiktoken-cache
# Bind the API to all interfaces (IPv4). Set API_HOST=:: for IPv6 dual-stack environments
ENV API_HOST=0.0.0.0
ENV SURREAL_EMBEDDED=false

# Caches for the opt-in heavy extraction runtimes (Docling, Crawl4AI local).
# These live UNDER /app/data so the user's volume mount persists them across
# container restarts and upgrades: wheels (uv), the Chromium browser (playwright)
# and Docling's ML models (huggingface) are downloaded once, then reused.
# See scripts/docker-entrypoint.sh and docs/7-DEVELOPMENT/decisions/ADR-007-optin-runtimes.md.
ENV UV_CACHE_DIR=/app/data/.cache/uv
ENV PLAYWRIGHT_BROWSERS_PATH=/app/data/.cache/playwright
ENV HF_HOME=/app/data/.cache/huggingface

# Data directory (volume-mounted by users) and supervisor log directory
RUN mkdir -p /app/data /mydata /var/log/supervisor \
    && chmod +x /app/scripts/wait-for-api.sh /app/scripts/docker-entrypoint.sh

# Copy supervisord configuration (shared programs: api, worker, frontend)
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
RUN cat /app/supervisord.surrealdb.conf >> /etc/supervisor/conf.d/supervisord.conf

# Expose ports for Frontend and API
EXPOSE 8502 5055

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD curl --fail --silent http://127.0.0.1:8502/healthz >/dev/null || exit 1

# Runtime API URL Configuration
# By default, browser requests remain same-origin and Next.js proxies /api to
# INTERNAL_API_URL. Set API_URL only when exposing the API on another origin.
#
# Example: docker run -e API_URL=https://api.your-domain.com ...

# The entrypoint installs any opt-in heavy runtimes (Docling, Crawl4AI local)
# enabled via OPEN_NOTEBOOK_ENABLE_* before handing off to CMD (supervisord).
ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]

# Stage 5: Single-container variant (enables the embedded SurrealDB program)
# Build with: docker build --target single .
FROM runtime-base AS single
ENV SURREAL_EMBEDDED=true

# Stage 6 (default): Regular multi-container image (SurrealDB runs externally).
# Kept last so a plain `docker build .` produces this variant.
FROM runtime-base AS runtime
