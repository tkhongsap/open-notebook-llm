# Local AI or OpenRouter

Open Notebook supports an explicit private-local path and an explicit cloud
path. Credentials and model defaults are selected by you; the application does
not silently fail over from a local model to a cloud provider.

## Start the application from source

```bash
uv sync
cd frontend && npm ci && cd ..
cp .env.example .env
# Replace OPEN_NOTEBOOK_ENCRYPTION_KEY in .env before storing credentials.
make start-all
make status
```

Open <http://127.0.0.1:3000>. The managed stack binds the frontend, API, and
database to loopback. When Docker is not installed on Apple Silicon,
`make start-all` downloads SurrealDB v2.6.5 from its official release, verifies
the pinned SHA-256, and keeps the binary, data, logs, and PID files under the
ignored `.runtime/` directory.

Stop every managed application process safely with:

```bash
make stop-all
```

## Native Apple Silicon models

The LocalAISandbox gateway used by this workstation is an authenticated
OpenAI-compatible API at `http://127.0.0.1:4000/v1`. It is loopback-only and has
no implicit cloud fallback. Start its safe research profile in a separate
terminal:

```bash
"$HOME/Library/Application Support/LocalAISandbox/bin/local-ai" run retrieval
```

Then configure Open Notebook:

1. Open **Settings → API Keys**.
2. Add **Local AI / OpenAI Compatible**.
3. Click **Use local gateway**.
4. Enter the LocalAISandbox application key and save.
5. Test the credential, then open **Models** and discover models.
6. Register `sandbox/qwen3.8-27b` as **Language** and
   `sandbox/embed-small` as **Embedding**.
7. In **Default model assignments**, set those models as Chat and Embedding.
   Transformation, tools, and large-context slots can fall back to Chat.

The `retrieval` profile is the recommended Notebook workflow: it loads the
pinned text model, embedding model, and reranker within the workstation's safe
memory gate. Vision and speech recognition use separate profiles. The disabled
all-model profile must not be bypassed merely to keep every model resident.

## OpenRouter

For an explicit cloud configuration:

1. Add `OPENROUTER_API_KEY` to `.env`, restart the stack, and use the migration
   action in Settings; or add an OpenRouter credential directly in the UI.
2. Test the credential.
3. Discover and register only the models you intend to use.
4. Assign defaults deliberately. Adding OpenRouter does not change an existing
   local default and does not create automatic failover.

This separation makes cost and privacy boundaries visible. A notebook stays on
the selected local default until you select a cloud model or change a default.

## Notebook workflow now available

- text, file, URL, audio, video, and supported web sources;
- background extraction and embeddings;
- full-text and semantic search;
- source-grounded chat with source IDs in citations;
- durable notes;
- Studio generation for briefing documents, study guides, FAQs, timelines,
  mind maps, flashcards, and quizzes;
- audio overview generation when a text-to-speech model is configured.

Every Studio output is saved as an AI note related to the notebook. Generated
answers and artifacts are constrained to notebook context, but—as with any
model-generated text—citations should still be inspected before high-stakes use.

After configuration, run the [end-to-end smoke test](e2e-smoke-test.md) to
verify ingestion, embeddings, grounded chat, citations, and Studio persistence
with one small document.

## Deployment contract

The repository's Docker image and Compose files remain the portable deployment
path. A durable deployment needs:

- the Open Notebook web/API service;
- the background worker (included by the maintained container entrypoint);
- SurrealDB v2 with persistent storage;
- persistent `/app/data` storage for uploads, generated audio, and checkpoints;
- `OPEN_NOTEBOOK_ENCRYPTION_KEY`, a strong `OPEN_NOTEBOOK_PASSWORD`, and scoped
  `CORS_ORIGINS` supplied as secrets/configuration;
- HTTPS at the public ingress, exposing the application rather than SurrealDB.

Fly.io, Railway, Render, a VM, or a Kubernetes service can run this container
contract as long as the platform supports persistent volumes and long-running
workers. A cloud container cannot reach the Mac's `127.0.0.1`; use OpenRouter or
an explicitly deployed OpenAI-compatible inference endpoint for hosted use.
Never publish the local Metal gateway directly to the public internet.

Before a deployment, run the complete verification gate documented in
[Testing](../7-DEVELOPMENT/testing.md) and build the production image locally:

```bash
uv run pytest
cd frontend && npm test -- --run && npm run lint && npm run build
cd .. && git diff --check
docker build -t open-notebook:local .
```
