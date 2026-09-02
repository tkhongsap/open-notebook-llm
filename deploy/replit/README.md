# Replit cloud deployment

This profile runs the same repository used by local GPU installations. Replit
runs a full Open Notebook stack (Next.js, FastAPI, background worker, and a
pinned SurrealDB binary) but deliberately permits **cloud/OpenRouter models
only**. A workstation can run the same commit with `local-only` or `hybrid` as
documented in [Local AI or OpenRouter](../../docs/0-START-HERE/local-ai-or-openrouter.md).

There is no automatic local-to-cloud fallback in either environment.

## Source synchronization

Import the **GitHub repository**, not a Vercel frontend export. The checked-in
[`.replit`](../../.replit) and [`replit.nix`](../../replit.nix) files are the
Replit contract. Replit's version-control panel should track the same GitHub
branch that is reviewed and merged locally:

1. Pull the desired GitHub branch before testing Preview.
2. Do not let an import migration replace the repository with a PNPM-only
   frontend. That removes FastAPI, SurrealDB, and the worker.
3. Make product changes in Git branches and merge through the normal CI path.
4. Pull the merged `main` commit in Replit, verify Preview, and republish the
   resulting snapshot.

## What the runtime does

The Replit build command:

- installs the frozen Python and npm lockfiles;
- builds the Next.js standalone server;
- downloads SurrealDB `v2.6.5` for Linux from the official release and verifies
  its committed SHA-256 digest;
- pre-caches the tokenizer and verifies that `ffmpeg` is available.

Replit sets `UV_PROJECT_ENVIRONMENT` to its managed `.pythonlibs` directory.
The supervisor honors that value instead of assuming uv created `.venv`, so
Preview and deployed runs use the same pinned Python environment produced by
the build command.

The run command starts these processes in order and fails the whole deployment
if any one exits:

1. loopback-only SurrealDB on port `8000`;
2. loopback-only FastAPI on port `5055`;
3. the continuously running source/podcast command worker;
4. public Next.js on Replit's mapped port `8502`.

The checked-in `.replit` maps only port `8502` to public port `80`, preventing
stale import-time port detection from routing Preview to a different process.
Only the Next.js port is public. The launcher derives explicit CORS origins
from `REPLIT_DOMAINS`/`REPLIT_DEV_DOMAIN`, enables strict production security,
and enforces `OPEN_NOTEBOOK_MODEL_ROUTING_POLICY=cloud-only`. Attempts to set
`hybrid`, `local-only`, wildcard CORS, or weak deployment credentials fail
startup instead of weakening the profile.

## Secrets

Add these values to the Replit **Secrets** tool for Preview and to the
**Published app secrets** section before publishing:

```dotenv
OPENROUTER_API_KEY=<your-openrouter-key>
SURREAL_PASSWORD=<random-value-at-least-16-characters>
OPEN_NOTEBOOK_ENCRYPTION_KEY=<random-value-at-least-32-characters>
OPEN_NOTEBOOK_PASSWORD=<team-login-password-at-least-12-characters>
```

The launcher supplies the non-secret database name, namespace, user, internal
URLs, security mode, and cloud-only routing policy. Keep the OpenRouter key
server-side: never create a `NEXT_PUBLIC_OPENROUTER_API_KEY` variable and never
commit a populated `.env` file.

If the final public domain cannot be read from Replit's environment, set
`CORS_ORIGINS=https://<your-app>.replit.app` explicitly. Do not use `*`.

## Preview and publish

1. Select **Run** and wait for `/healthz` to return `{"status":"ready"}`.
2. Sign in with `OPEN_NOTEBOOK_PASSWORD`.
3. In Settings, migrate/test the environment OpenRouter credential, discover a
   small approved model set, and assign chat, transformation, embedding, and
   podcast models deliberately.
4. Create a notebook, add a source, ask a cited question, and generate a short
   podcast. Confirm the worker completes the queued jobs.
5. Choose a **Reserved VM** deployment. The worker must remain available while
   source and podcast jobs are queued; Autoscale can suspend it between web
   requests.
6. Confirm Replit auto-detects the public listener on port `8502`, add the
   published app secrets, publish, and repeat the `/healthz`, authentication,
   source, chat, and podcast checks at the `replit.app` URL.

## Durability and scaling boundary

Replit documents that a published app's filesystem is not persistent and is
replaced by a new snapshot when republished. In this demo profile, notebook
records, uploads, generated audio, and checkpoints are therefore disposable.
This is acceptable for a team demonstration, not a durable production system.

Before horizontal scaling or durable use:

- move SurrealDB to an external durable SurrealDB service;
- move uploads and generated audio to shared object storage;
- run the worker as a continuously available service;
- point every replica at the same database and storage;
- keep `cloud-only` unless the hosted environment can reach an authenticated,
  private inference endpoint.

Current platform behavior is documented in Replit's
[Publishing overview](https://docs.replit.com/learn/projects-and-artifacts/replit-deployments),
[Reserved VM guide](https://docs.replit.com/cloud-services/deployments/reserved-vm-deployments),
and [publishing troubleshooting guide](https://docs.replit.com/build/troubleshooting).
