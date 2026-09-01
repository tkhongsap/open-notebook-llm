# Deployment-Ready Open Notebook

This guide is the production contract for a single-instance Open Notebook
deployment. It provides fail-closed security validation, persistent storage,
database-aware readiness checks, backup/restore, and rollback instructions.

## Architecture

```text
Internet / HTTPS ingress
          |
          v
   Next.js :8502  ---- same-origin /api proxy ----> FastAPI :5055
                                                     |
                                                     v
                                               worker + SurrealDB
                                                     |
                                                     v
                                             persistent /app/data
```

Only port 8502 is public. `/healthz` succeeds only when the frontend, API, and
database are ready. `/health` remains a lightweight API liveness probe and
`/ready` verifies the required database connection.

The one-service Fly.io, Railway, and Render examples run the pinned embedded
SurrealDB and store it under `/app/data/surrealdb`. This is deliberately a
single-replica topology. For horizontal scaling, move SurrealDB to a dedicated
service and move uploads, generated audio, and checkpoints to shared storage.

## Required production settings

Every hosted example sets `OPEN_NOTEBOOK_REQUIRE_SECURITY=true`. Startup fails
until all of these are safe:

- `OPEN_NOTEBOOK_ENCRYPTION_KEY`: at least 32 non-placeholder characters;
- `OPEN_NOTEBOOK_PASSWORD`: at least 12 non-placeholder characters;
- `SURREAL_PASSWORD`: at least 16 non-placeholder characters;
- `CORS_ORIGINS`: explicit frontend origin(s), never `*`.

Provider keys belong in the platform's secret manager or the encrypted Settings
UI. Never commit a populated environment file.

## Production Docker Compose

```bash
cp deploy/docker/.env.production.example deploy/docker/.env.production
# Replace every placeholder in the private env file.
docker compose \
  --env-file deploy/docker/.env.production \
  -f deploy/docker/docker-compose.production.yml \
  up -d
```

Open `http://localhost:8502` unless `OPEN_NOTEBOOK_PORT` was changed. Confirm:

```bash
curl --fail http://localhost:8502/healthz
docker compose \
  --env-file deploy/docker/.env.production \
  -f deploy/docker/docker-compose.production.yml \
  ps
```

The database is isolated on an internal network. The frontend proxies browser
API traffic, so port 5055 is not published.

## Fly.io

```bash
cp deploy/fly/fly.toml.example fly.toml
# Replace the app name and CORS origin in fly.toml.
fly apps create YOUR_APP_NAME
fly volumes create open_notebook_data --region sin --size 10
fly secrets set \
  OPEN_NOTEBOOK_ENCRYPTION_KEY="$(openssl rand -hex 32)" \
  OPEN_NOTEBOOK_PASSWORD='replace-with-your-login-password' \
  SURREAL_PASSWORD="$(openssl rand -hex 24)"
fly deploy
```

The example uses Fly's `runtime` build target, a 10 GB volume, HTTPS, one
always-on Machine, and `/healthz` deployment checks. Change the region and
machine size for your workload.

## Railway

Follow [the Railway service checklist](../../deploy/railway/README.md). Required
variables are:

```text
PORT=8502
API_HOST=127.0.0.1
INTERNAL_API_URL=http://127.0.0.1:5055
OPEN_NOTEBOOK_REQUIRE_SECURITY=true
OPEN_NOTEBOOK_ENCRYPTION_KEY=<secret>
OPEN_NOTEBOOK_PASSWORD=<secret>
CORS_ORIGINS=https://<your-domain>
SURREAL_EMBEDDED=true
SURREAL_DATA_PATH=/app/data/surrealdb
SURREAL_URL=ws://127.0.0.1:8000/rpc
SURREAL_USER=open_notebook_admin
SURREAL_PASSWORD=<secret>
SURREAL_NAMESPACE=open_notebook
SURREAL_DATABASE=open_notebook
```

Attach one volume at `/app/data` and configure `/healthz`. Railway volumes allow
one replica, which matches this embedded topology.

## Render

Create a Blueprint from `deploy/render/render.yaml`. Before the first deploy,
provide `OPEN_NOTEBOOK_PASSWORD` and set `CORS_ORIGINS` to the final Render or
custom HTTPS origin. The Blueprint generates the encryption and database keys,
mounts 10 GB at `/app/data`, and gates deployment on `/healthz`.

## Backup

For a source install with the native database running:

```bash
uv run python scripts/backup_restore.py \
  --env-file .env \
  --data-dir data \
  backup backups/open-notebook-$(date -u +%Y%m%dT%H%M%SZ).tar.gz
```

The mode-`0600` archive contains a SurrealQL export, durable application data,
a versioned manifest, and SHA-256 checksums.

For Compose, run the helper inside the app container and copy the result:

```bash
docker compose \
  --env-file deploy/docker/.env.production \
  -f deploy/docker/docker-compose.production.yml \
  exec open_notebook uv run --no-sync python scripts/backup_restore.py \
  --data-dir /app/data backup /tmp/open-notebook-backup.tar.gz

docker compose \
  --env-file deploy/docker/.env.production \
  -f deploy/docker/docker-compose.production.yml \
  cp open_notebook:/tmp/open-notebook-backup.tar.gz ./
```

Store backups outside the application volume and test restore regularly.

## Restore

Restore into an empty database name first. This avoids deleting a working
database and gives you a rollback path:

```bash
SURREAL_DATABASE=open_notebook_restore \
uv run python scripts/backup_restore.py \
  --env-file .env \
  --data-dir /absolute/path/to/restored-data \
  restore ./open-notebook-backup.tar.gz \
  --confirm-restore
```

Validate `/ready`, inspect notebooks and sources, and run the end-to-end smoke
test. Then stop the app, point `SURREAL_DATABASE` and the data mount at the
restored copy, and restart. If `--overwrite-data` is explicitly used, the helper
moves the old data directory beside the new one instead of deleting it.

## Deploy checklist and rollback triggers

Before deploy:

- all backend/frontend tests, lint, type checks, and production builds pass;
- the Docker image smoke workflow is green;
- a recent backup exists and a restore has been exercised;
- `/healthz` is configured on the platform;
- security settings and provider secrets are present;
- release and migration notes are reviewed.

Roll back to the previous image if `/healthz` stays non-200, the API 5xx rate
exceeds 2% for five minutes, source processing cannot complete, or the database
reports offline. Keep the persistent volume; never roll back by deleting data.
