from dataclasses import asdict, dataclass
from typing import Any, Literal, Mapping, Optional

from esperanto import LanguageModel
from langchain_core.language_models.chat_models import BaseChatModel
from loguru import logger

from open_notebook.ai.model_routing import get_provider_location
from open_notebook.ai.models import model_manager
from open_notebook.ai.provider_registry import PROVIDERS
from open_notebook.exceptions import ConfigurationError
from open_notebook.utils import token_count


@dataclass(frozen=True)
class ModelExecutionInfo:
    """Stable, non-secret provenance for one language-model invocation."""

    id: str
    name: str
    provider: str
    provider_display_name: str
    location: Literal["local", "cloud"]
    selection_reason: Literal["explicit", "default", "large_context"]

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


async def provision_langchain_model_with_info(
    content,
    model_id,
    default_type,
    *,
    openai_compatible_extra_body: Optional[Mapping[str, Any]] = None,
    **kwargs,
) -> tuple[BaseChatModel, ModelExecutionInfo]:
    """
    Returns the best model to use based on the context size and on whether there is a specific model being requested in Config.
    If context > 105_000, returns the large_context_model
    If model_id is specified in Config, returns that model
    Otherwise, returns the default model for the given type
    """
    tokens = token_count(content)
    model = None
    resolved_model_id: str | None = None
    selection_reason: Literal["explicit", "default", "large_context"]

    if tokens > 105_000:
        selection_reason = "large_context"
        logger.debug(
            f"Using large context model because the content has {tokens} tokens"
        )
        resolved_model_id = await model_manager.get_default_model_id("large_context")
        model = await model_manager.get_default_model("large_context", **kwargs)
    elif model_id:
        selection_reason = "explicit"
        resolved_model_id = str(model_id)
        model = await model_manager.get_model(resolved_model_id, **kwargs)
    else:
        selection_reason = "default"
        resolved_model_id = await model_manager.get_default_model_id(default_type)
        model = await model_manager.get_default_model(default_type, **kwargs)

    logger.debug(f"Using model: {model}")

    if model is None:
        logger.error(
            f"Model provisioning failed: No model found. "
            f"Selection reason: {selection_reason}. "
            f"model_id={model_id}, default_type={default_type}. "
            f"Please check Settings → Models and ensure a default model is configured for '{default_type}'."
        )
        raise ConfigurationError(
            f"No model configured for {selection_reason}. "
            f"Please go to Settings → Models and configure a default model for '{default_type}'."
        )

    if not isinstance(model, LanguageModel):
        logger.error(
            f"Model type mismatch: Expected LanguageModel but got {type(model).__name__}. "
            f"Selection reason: {selection_reason}. "
            f"model_id={model_id}, default_type={default_type}."
        )
        raise ConfigurationError(
            f"Model is not a LanguageModel: {model}. "
            f"Please check that the model configured for '{default_type}' is a language model, not an embedding or speech model."
        )

    chain = model.to_langchain()

    # Esperanto supports instance-level ``extra_body`` for its native client,
    # but its OpenAI-compatible LangChain adapter currently does not carry that
    # field across. Preserve explicitly requested local endpoint controls (for
    # example Qwen's ``enable_thinking`` chat-template flag) at this boundary.
    provider = str(getattr(model, "provider", "")).replace("_", "-").lower()
    if openai_compatible_extra_body and provider == "openai-compatible":
        if not hasattr(chain, "extra_body"):
            raise ConfigurationError(
                "The installed LangChain OpenAI adapter does not support extra_body"
            )
        chain.extra_body = dict(openai_compatible_extra_body)  # type: ignore[attr-defined]

    registered_provider = str(
        getattr(model, "_open_notebook_provider", None)
        or getattr(model, "provider", "")
    ).replace("-", "_")
    registered_name = str(
        getattr(model, "_open_notebook_model_name", None)
        or getattr(model, "model_name", "")
        or resolved_model_id
    )
    spec = PROVIDERS.get(registered_provider)
    execution = ModelExecutionInfo(
        id=str(
            getattr(model, "_open_notebook_model_id", None) or resolved_model_id
        ),
        name=registered_name,
        provider=registered_provider,
        provider_display_name=(
            spec.display_name if spec is not None else registered_provider
        ),
        location=get_provider_location(registered_provider).value,
        selection_reason=selection_reason,
    )
    return chain, execution


async def provision_langchain_model(
    content,
    model_id,
    default_type,
    *,
    openai_compatible_extra_body: Optional[Mapping[str, Any]] = None,
    **kwargs,
) -> BaseChatModel:
    """Provision a model while preserving the established chain-only API."""

    chain, _execution = await provision_langchain_model_with_info(
        content,
        model_id,
        default_type,
        openai_compatible_extra_body=openai_compatible_extra_body,
        **kwargs,
    )
    return chain


def attach_model_execution_metadata(message, execution: ModelExecutionInfo):
    """Persist provenance in LangChain metadata so checkpoints retain it."""

    response_metadata = dict(getattr(message, "response_metadata", {}) or {})
    response_metadata["open_notebook_model"] = execution.to_dict()
    return message.model_copy(update={"response_metadata": response_metadata})
