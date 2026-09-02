# ADR-009: Replit uses a checked-in managed-runtime launcher

- **Status**: Accepted
- **Date**: 2026-09
- **Related**: [ADR-004](ADR-004-background-workers.md), [ADR-008](ADR-008-explicit-hybrid-model-routing.md), [Replit deployment](../../../deploy/replit/README.md)

## Context

The production image runs Next.js, FastAPI, a background worker, and optionally
SurrealDB under Supervisor. Replit imports and publishes applications through
checked-in build/run commands rather than executing this repository's
Dockerfile, and a frontend-only import silently removes core notebook flows.
The Replit demo also cannot reach a model server on a developer's private Mac.

## Decision

Keep Docker as the general deployment contract and add a narrow, checked-in
Replit launcher that starts the same four processes. Reuse the frozen Python and
npm locks, download the same pinned SurrealDB release with a committed digest,
expose only Next.js, require strict security, and fail startup unless model
routing is `cloud-only` with an OpenRouter credential. The worker is a required
process, so the published profile uses a continuously available Reserved VM.

## Alternatives considered

- **Keep the generated frontend-only Replit port** — rejected because notebook
  CRUD, ingestion, chat, search, and podcasts require the backend and worker.
- **Proxy a developer's local API from Replit** — rejected because it couples a
  public demo to a private workstation and exposes a new network trust boundary.
- **Automatically fall back from local models to OpenRouter** — rejected by
  ADR-008 because source disclosure must remain an explicit deployment choice.

## Consequences

- Local, hybrid, and Replit deployments can track one reviewed Git history.
- Replit has a small platform-specific process supervisor that requires unit
  coverage alongside the Docker release-image contract.
- Embedded data is disposable because Replit published filesystems are not
  durable; production scaling requires external SurrealDB and object storage.
