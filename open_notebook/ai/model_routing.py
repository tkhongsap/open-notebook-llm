"""Explicit local/cloud model routing policy.

This module deliberately does not select an alternative model. It only
classifies a registered provider and decides whether that model is permitted
in the current deployment profile. See ADR-008.
"""

import os
from collections.abc import Mapping
from enum import Enum

from open_notebook.ai.provider_registry import PROVIDERS
from open_notebook.exceptions import ConfigurationError

MODEL_ROUTING_POLICY_ENV = "OPEN_NOTEBOOK_MODEL_ROUTING_POLICY"


class ModelLocation(str, Enum):
    LOCAL = "local"
    CLOUD = "cloud"


class ModelRoutingPolicy(str, Enum):
    LOCAL_ONLY = "local-only"
    CLOUD_ONLY = "cloud-only"
    HYBRID = "hybrid"


def get_model_routing_policy(
    environment: Mapping[str, str] | None = None,
) -> ModelRoutingPolicy:
    """Return the configured policy, rejecting typos instead of guessing."""

    values = os.environ if environment is None else environment
    raw = (values.get(MODEL_ROUTING_POLICY_ENV) or ModelRoutingPolicy.HYBRID.value)
    normalized = raw.strip().lower()
    try:
        return ModelRoutingPolicy(normalized)
    except ValueError as exc:
        allowed = ", ".join(policy.value for policy in ModelRoutingPolicy)
        raise ConfigurationError(
            f"{MODEL_ROUTING_POLICY_ENV} must be one of: {allowed}"
        ) from exc


def get_provider_location(provider: str) -> ModelLocation:
    """Classify a provider from the registry, failing closed for unknown names."""

    spec = PROVIDERS.get(provider.replace("-", "_"))
    if spec is None:
        return ModelLocation.CLOUD
    return ModelLocation(spec.location)


def is_provider_allowed(
    provider: str,
    policy: ModelRoutingPolicy | None = None,
) -> bool:
    """Return whether a provider may be used under the deployment policy."""

    active_policy = policy or get_model_routing_policy()
    if active_policy is ModelRoutingPolicy.HYBRID:
        return True

    location = get_provider_location(provider)
    if active_policy is ModelRoutingPolicy.LOCAL_ONLY:
        return location is ModelLocation.LOCAL
    return location is ModelLocation.CLOUD


def enforce_model_routing_policy(provider: str) -> None:
    """Raise a typed configuration error when the selected model is blocked."""

    policy = get_model_routing_policy()
    if is_provider_allowed(provider, policy):
        return

    location = get_provider_location(provider).value
    raise ConfigurationError(
        f"The selected {location} model is disabled by "
        f"{MODEL_ROUTING_POLICY_ENV}={policy.value}. "
        "Choose an allowed model or update the deployment policy and restart."
    )
