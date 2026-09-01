from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from esperanto import LanguageModel
from langchain_core.messages import AIMessage

from open_notebook.ai.provision import (
    ModelExecutionInfo,
    attach_model_execution_metadata,
    provision_langchain_model,
    provision_langchain_model_with_info,
)


@pytest.mark.asyncio
@patch("open_notebook.ai.provision.model_manager.get_model", new_callable=AsyncMock)
async def test_openai_compatible_extra_body_reaches_langchain(mock_get_model):
    model = MagicMock(spec=LanguageModel)
    model.provider = "openai-compatible"
    chain = MagicMock()
    chain.extra_body = None
    model.to_langchain.return_value = chain
    mock_get_model.return_value = model
    extra_body = {"chat_template_kwargs": {"enable_thinking": False}}

    result = await provision_langchain_model(
        "content",
        "model:local",
        "chat",
        max_tokens=512,
        openai_compatible_extra_body=extra_body,
    )

    assert result is chain
    assert chain.extra_body == extra_body
    mock_get_model.assert_awaited_once_with("model:local", max_tokens=512)


@pytest.mark.asyncio
@patch("open_notebook.ai.provision.model_manager.get_model", new_callable=AsyncMock)
async def test_extra_body_is_not_sent_to_non_compatible_providers(mock_get_model):
    model = MagicMock(spec=LanguageModel)
    model.provider = "openai"
    chain = MagicMock()
    chain.extra_body = None
    model.to_langchain.return_value = chain
    mock_get_model.return_value = model

    result = await provision_langchain_model(
        "content",
        "model:cloud",
        "chat",
        openai_compatible_extra_body={
            "chat_template_kwargs": {"enable_thinking": False}
        },
    )

    assert result is chain
    assert chain.extra_body is None


@pytest.mark.asyncio
@patch("open_notebook.ai.provision.model_manager.get_model", new_callable=AsyncMock)
async def test_explicit_model_returns_non_secret_execution_provenance(mock_get_model):
    model = MagicMock(spec=LanguageModel)
    model.provider = "openai-compatible"
    model._open_notebook_model_id = "model:local"
    model._open_notebook_model_name = "sandbox/qwen"
    model._open_notebook_provider = "openai_compatible"
    chain = MagicMock()
    model.to_langchain.return_value = chain
    mock_get_model.return_value = model

    result, execution = await provision_langchain_model_with_info(
        "content",
        "model:local",
        "chat",
    )

    assert result is chain
    assert execution == ModelExecutionInfo(
        id="model:local",
        name="sandbox/qwen",
        provider="openai_compatible",
        provider_display_name="Local AI / OpenAI Compatible",
        location="local",
        selection_reason="explicit",
    )


def test_execution_provenance_is_preserved_in_message_metadata():
    execution = ModelExecutionInfo(
        id="model:cloud",
        name="openai/gpt-4.1-mini",
        provider="openrouter",
        provider_display_name="OpenRouter",
        location="cloud",
        selection_reason="default",
    )

    updated = attach_model_execution_metadata(
        AIMessage(content="Grounded answer", response_metadata={"usage": {}}),
        execution,
    )

    assert updated.content == "Grounded answer"
    assert updated.response_metadata == {
        "usage": {},
        "open_notebook_model": execution.to_dict(),
    }
