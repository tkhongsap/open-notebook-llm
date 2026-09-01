"""Build the non-secret model catalog used by hybrid routing selectors."""

from api.credentials_service import check_env_configured
from api.models import ModelRoutingResponse, RoutedModelResponse
from open_notebook.ai.model_routing import (
    ModelLocation,
    ModelRoutingPolicy,
    get_model_routing_policy,
    get_provider_location,
    is_provider_allowed,
)
from open_notebook.ai.models import DefaultModels, Model
from open_notebook.ai.provider_registry import PROVIDERS


async def _configuration_source(model: Model) -> str:
    """Resolve whether a model has usable credential metadata without secrets."""

    if model.credential and await model.get_credential_obj() is not None:
        return "credential"
    if check_env_configured(model.provider):
        return "environment"
    return "none"


def _unavailable_reason(
    *, configured: bool, location: ModelLocation, policy: ModelRoutingPolicy
) -> str | None:
    if not configured:
        return "provider_not_configured"
    if policy is ModelRoutingPolicy.LOCAL_ONLY and location is ModelLocation.CLOUD:
        return "policy_local_only"
    if policy is ModelRoutingPolicy.CLOUD_ONLY and location is ModelLocation.LOCAL:
        return "policy_cloud_only"
    return None


async def get_model_routing_catalog() -> ModelRoutingResponse:
    """Return language models grouped by execution location and deployment policy."""

    policy = get_model_routing_policy()
    defaults = await DefaultModels.get_instance()
    default_model_id = (
        str(defaults.default_chat_model) if defaults.default_chat_model else None
    )
    registered_models = await Model.get_models_by_type("language")

    routed_models: list[RoutedModelResponse] = []
    for model in registered_models:
        model_id = str(model.id or "")
        location = get_provider_location(model.provider)
        configuration_source = await _configuration_source(model)
        configured = configuration_source != "none"
        allowed = is_provider_allowed(model.provider, policy)
        spec = PROVIDERS.get(model.provider)
        routed_models.append(
            RoutedModelResponse(
                id=model_id,
                name=model.name,
                provider=model.provider,
                provider_display_name=(
                    spec.display_name if spec is not None else model.provider
                ),
                location=location.value,
                configuration_source=configuration_source,
                configured=configured,
                allowed=allowed,
                selectable=configured and allowed,
                unavailable_reason=_unavailable_reason(
                    configured=configured,
                    location=location,
                    policy=policy,
                ),
                is_default=model_id == default_model_id,
            )
        )

    routed_models.sort(
        key=lambda model: (
            0 if model.location == ModelLocation.LOCAL.value else 1,
            model.provider_display_name.casefold(),
            model.name.casefold(),
        )
    )
    return ModelRoutingResponse(
        policy=policy.value,
        default_model_id=default_model_id,
        models=routed_models,
    )
