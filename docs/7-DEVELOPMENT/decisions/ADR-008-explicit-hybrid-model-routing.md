# ADR-008: Hybrid model routing is explicit, policy-gated, and auditable

- **Status**: Accepted
- **Date**: 2026-09
- **Related**: [PDR-002](PDR-002-provider-agnostic-core.md), [local AI or OpenRouter](../../0-START-HERE/local-ai-or-openrouter.md)

## Context

Open Notebook can register both self-hosted models and cloud models, but the
existing flat selectors do not communicate where notebook content is sent.
Hosted demos also need to disable unreachable local endpoints, while private
deployments need to prevent cloud use even when cloud credentials are present.

## Decision

Classify every provider as `local` (a user-controlled endpoint) or `cloud` in
the provider registry. Enforce `OPEN_NOTEBOOK_MODEL_ROUTING_POLICY` at the
shared model-provisioning boundary with three values: `local-only`,
`cloud-only`, and `hybrid` (the backward-compatible default). The policy is an
allow/deny guard, not a fallback mechanism: a blocked, missing, or unreachable
selection fails visibly and never switches providers. Frontends consume a
backend routing catalog, group language models by location, disable models that
are blocked or unconfigured, and show the model used on generated chat messages.

## Alternatives considered

- **Frontend-only grouping** — rejected because API clients and background
  workflows could bypass it.
- **Automatic local-to-cloud fallback** — rejected because it can disclose
  private source content without a fresh user decision.
- **Infer location from model names or URLs in the browser** — rejected because
  it duplicates provider knowledge and can expose endpoint configuration.

## Consequences

- One image supports private local deployments, cloud demos, and hybrid use.
- Operators must set the policy and defaults consistently; invalid policy
  values fail startup.
- Provider location is intentionally categorical. A new provider must declare
  its location in the registry and add coverage before it can be selected.
- Availability in the catalog means configured and policy-allowed, not a live
  latency probe; invocation errors remain visible and do not trigger fallback.
