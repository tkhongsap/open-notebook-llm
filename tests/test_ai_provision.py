from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from esperanto import LanguageModel

from open_notebook.ai.provision import provision_langchain_model


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
