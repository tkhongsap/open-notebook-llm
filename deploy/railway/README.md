# Railway deployment

Railway's legacy `railway.toml`/`railway.json` config is no longer available to
new services. Use the current service/template flow:

1. Create a Railway project and connect this repository as a service.
2. Railway detects `Dockerfile`; use its final `runtime` stage.
3. Set the public target port and `PORT` to `8502`.
4. Attach one persistent volume at `/app/data`.
5. Set the health-check path to `/healthz` with a 300-second startup timeout.
6. Add the variables listed in the deployment guide. Mark all passwords and
   encryption/provider keys as secrets.
7. Generate a public domain only for this app service. Do not expose port 5055
   or the embedded database.

The embedded database is stored at `/app/data/surrealdb`, so the single Railway
volume protects records, uploads, generated audio, and checkpoints together.
This topology supports one application replica; use an external SurrealDB and
shared object storage before horizontal scaling.
