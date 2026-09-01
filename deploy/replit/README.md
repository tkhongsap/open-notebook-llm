# Replit cloud demo

This is a demo profile for the repository's single-service container. It uses
cloud language models explicitly and never attempts to reach a model running on
the developer's Mac.

## Publish

1. Import this repository into a Replit App. Keep the root `Dockerfile` as the
   build source.
2. Choose a **Reserved VM** deployment when podcast/source workers must remain
   alive continuously. Autoscale is suitable only for short-lived UI demos
   where background work is not expected to survive scale-to-zero.
3. Set the run command to the image default (`/app/scripts/docker-entrypoint.sh`
   followed by supervisord) and expose port `8502`. The server must bind to
   `0.0.0.0`; the variables below provide that contract.
4. Add every production value in the **Publishing** deployment secrets panel.
   Editor secrets are not automatically copied to a published deployment.
5. Publish and verify `/healthz`, then sign in and register only the OpenRouter
   models intended for the demo.

Required deployment variables/secrets:

```dotenv
PORT=8502
FRONTEND_BIND_HOST=0.0.0.0
API_HOST=0.0.0.0
INTERNAL_API_URL=http://127.0.0.1:5055
SURREAL_EMBEDDED=true
SURREAL_URL=ws://127.0.0.1:8000/rpc
SURREAL_DATA_PATH=/app/data/surrealdb
SURREAL_USER=open_notebook_admin
SURREAL_PASSWORD=<generated-secret>
SURREAL_NAMESPACE=open_notebook
SURREAL_DATABASE=open_notebook
OPEN_NOTEBOOK_ENCRYPTION_KEY=<generated-secret-at-least-32-characters>
OPEN_NOTEBOOK_PASSWORD=<generated-login-password>
OPEN_NOTEBOOK_REQUIRE_SECURITY=true
CORS_ORIGINS=https://<your-app>.replit.app
OPEN_NOTEBOOK_MODEL_ROUTING_POLICY=cloud-only
OPENROUTER_API_KEY=<deployment-secret>
```

The OpenRouter key stays server-side. Do not use a `NEXT_PUBLIC_*` variable for
it and do not commit a populated `.env` file. After first sign-in, use Settings
to migrate/test the environment credential, discover a small approved model
set, and assign the default chat and embedding models deliberately.

## Durability and scaling boundary

Replit documents that a published app's filesystem is reset on republish. With
`SURREAL_EMBEDDED=true`, records, uploads, generated audio, and checkpoints are
therefore disposable. This is acceptable for a demonstration, not production.

Before horizontal scaling or durable use:

- move SurrealDB to a durable external service;
- move uploads and generated audio to shared object storage;
- run the background worker as a continuously available service;
- point every replica at the same database/storage;
- keep `cloud-only` unless the hosted environment can reach an authenticated,
  private inference endpoint.

Current platform behavior is documented in Replit's
[Publishing overview](https://docs.replit.com/learn/projects-and-artifacts/replit-deployments)
and [deployment troubleshooting guide](https://docs.replit.com/build/troubleshooting).
