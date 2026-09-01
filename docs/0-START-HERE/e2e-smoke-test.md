# End-to-End Smoke Test

Use this check after first-time setup, model changes, or a deployment. It proves
that source ingestion, embeddings, grounded chat, citations, and Studio notes
work together. The check takes about five minutes after the models are ready.

## 1. Start and verify the services

For the native Apple Silicon setup, keep the local retrieval profile open in a
separate terminal:

```bash
"$HOME/Library/Application Support/LocalAISandbox/bin/local-ai" run retrieval
```

Then start Open Notebook:

```bash
make start-all
make status
```

Open <http://127.0.0.1:3000>. In **Settings**, test the language and embedding
models before continuing. A failed model test is an environment problem, not a
document-ingestion problem.

## 2. Create a small, verifiable source

Save this text as `smoke-test.md`:

```markdown
# Harborlight smoke test

Harborlight opens on 17 November 2026. Its launch budget is THB 2.4 million.
The unique verification phrase is LANTERN-482.
```

Create a notebook, choose **Add source → Upload file**, and upload the file.
Keep **Embedding** enabled. You can also select **Dense Summary** to test a
source transformation in the same run.

Wait until processing finishes. The source must remain readable after a page
reload, and the selected transformation must appear in its insights.

## 3. Verify grounded chat

Select the source in the notebook context and ask:

```text
What are Harborlight's opening date, launch budget, and unique verification
phrase? Cite the source.
```

The answer passes when it contains all three exact facts and a source citation:

- `17 November 2026`
- `THB 2.4 million`
- `LANTERN-482`
- a citation such as `[source:...]`

## 4. Verify Studio persistence

Generate a **Briefing document** in Studio. The generated note must:

- contain facts from the uploaded source;
- include source citations;
- appear in the notebook's notes after a page reload.

This verifies model generation and durable note storage, not just a transient
response.

## 5. Run the regression gates

```bash
uv run pytest
uv run ruff check .
uv run mypy open_notebook api
cd frontend
npm test -- --run
npm run lint
npm run build
cd ..
git diff --check
```

If Docker is installed, also build the deployment artifact:

```bash
docker build -t open-notebook:local .
```

Docker is optional for this native development workflow, but it remains the
portable deployment contract. If `docker --version` reports `command not
found`, install Docker Desktop before running the image gate.

## Troubleshooting local-model changes

- **401 or invalid API key:** Local gateway application keys can rotate. Save
  the current application key again in **Settings → API Keys**, test the
  credential, and restart the API and worker so new provider clients use it.
- **Embedding test fails:** Start the `retrieval` profile, not the text-only
  profile. Confirm ports 4000, 8010, 8030, and 8040 belong to one foreground
  profile and stop it with Ctrl-C when finished.
- **Tool-choice configuration error:** Update the LocalAISandbox launcher. Its
  Qwen text server must enable automatic tool choice with the matching Qwen
  tool-call parser. Do not expose the local gateway or its keys in logs.
- **Source remains in Processing:** Fix the model connection first, then retry
  the upload. Check the worker log before creating repeated uploads.

For hosted deployments, use OpenRouter or another reachable inference endpoint.
A cloud container cannot connect to a model bound to the Mac's `127.0.0.1`.
