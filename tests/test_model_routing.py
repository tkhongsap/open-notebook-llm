from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from open_notebook.ai.model_routing import (
    ModelLocation,
    ModelRoutingPolicy,
    enforce_model_routing_policy,
    get_model_routing_policy,
    get_provider_location,
    is_provider_allowed,
)
from open_notebook.exceptions import ConfigurationError


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


def test_routing_policy_defaults_to_hybrid():
    assert get_model_routing_policy({}) is ModelRoutingPolicy.HYBRID


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" local-only ", ModelRoutingPolicy.LOCAL_ONLY),
        ("CLOUD-ONLY", ModelRoutingPolicy.CLOUD_ONLY),
        ("hybrid", ModelRoutingPolicy.HYBRID),
    ],
)
def test_routing_policy_normalizes_supported_values(raw, expected):
    assert get_model_routing_policy(
        {"OPEN_NOTEBOOK_MODEL_ROUTING_POLICY": raw}
    ) is expected


def test_invalid_routing_policy_fails_closed_without_echoing_secrets():
    with pytest.raises(ConfigurationError, match="must be one of"):
        get_model_routing_policy(
            {"OPEN_NOTEBOOK_MODEL_ROUTING_POLICY": "automatic-fallback"}
        )


def test_registry_classifies_private_endpoints_and_cloud_providers():
    assert get_provider_location("openai_compatible") is ModelLocation.LOCAL
    assert get_provider_location("openai-compatible") is ModelLocation.LOCAL
    assert get_provider_location("ollama") is ModelLocation.LOCAL
    assert get_provider_location("openrouter") is ModelLocation.CLOUD


@pytest.mark.parametrize(
    ("policy", "local_allowed", "cloud_allowed"),
    [
        (ModelRoutingPolicy.HYBRID, True, True),
        (ModelRoutingPolicy.LOCAL_ONLY, True, False),
        (ModelRoutingPolicy.CLOUD_ONLY, False, True),
    ],
)
def test_policy_is_an_allow_deny_guard(policy, local_allowed, cloud_allowed):
    assert is_provider_allowed("openai_compatible", policy) is local_allowed
    assert is_provider_allowed("openrouter", policy) is cloud_allowed


def test_policy_enforcement_never_falls_back(monkeypatch):
    monkeypatch.setenv("OPEN_NOTEBOOK_MODEL_ROUTING_POLICY", "local-only")

    with pytest.raises(ConfigurationError, match="selected cloud model is disabled"):
        enforce_model_routing_policy("openrouter")


@pytest.mark.asyncio
@patch("api.model_routing_service.check_env_configured")
@patch("api.model_routing_service.Model.get_models_by_type", new_callable=AsyncMock)
@patch("api.model_routing_service.DefaultModels.get_instance", new_callable=AsyncMock)
async def test_routing_catalog_groups_and_disables_models(
    mock_defaults, mock_models, mock_env_configured, client, monkeypatch
):
    monkeypatch.setenv("OPEN_NOTEBOOK_MODEL_ROUTING_POLICY", "local-only")
    mock_defaults.return_value = SimpleNamespace(default_chat_model="model:local")

    local_credential = AsyncMock(return_value=SimpleNamespace(id="credential:local"))
    cloud_credential = AsyncMock(return_value=SimpleNamespace(id="credential:cloud"))
    unconfigured_credential = AsyncMock(return_value=None)
    mock_models.return_value = [
        SimpleNamespace(
            id="model:cloud",
            name="openai/gpt-4.1-mini",
            provider="openrouter",
            credential="credential:cloud",
            get_credential_obj=cloud_credential,
        ),
        SimpleNamespace(
            id="model:local",
            name="sandbox/qwen",
            provider="openai_compatible",
            credential="credential:local",
            get_credential_obj=local_credential,
        ),
        SimpleNamespace(
            id="model:missing",
            name="offline",
            provider="ollama",
            credential=None,
            get_credential_obj=unconfigured_credential,
        ),
    ]
    mock_env_configured.return_value = False

    response = client.get("/api/models/routing")

    assert response.status_code == 200
    data = response.json()
    assert data["policy"] == "local-only"
    assert data["default_model_id"] == "model:local"
    assert [model["id"] for model in data["models"]] == [
        "model:local",
        "model:missing",
        "model:cloud",
    ]

    by_id = {model["id"]: model for model in data["models"]}
    assert by_id["model:local"] == {
        "id": "model:local",
        "name": "sandbox/qwen",
        "provider": "openai_compatible",
        "provider_display_name": "Local AI / OpenAI Compatible",
        "location": "local",
        "configuration_source": "credential",
        "configured": True,
        "allowed": True,
        "selectable": True,
        "unavailable_reason": None,
        "is_default": True,
    }
    assert by_id["model:cloud"]["selectable"] is False
    assert by_id["model:cloud"]["unavailable_reason"] == "policy_local_only"
    assert by_id["model:missing"]["selectable"] is False
    assert (
        by_id["model:missing"]["unavailable_reason"]
        == "provider_not_configured"
    )


@pytest.mark.asyncio
@patch("open_notebook.ai.models.Model.get", new_callable=AsyncMock)
async def test_model_manager_enforces_policy_before_credentials(
    mock_model_get, monkeypatch
):
    from open_notebook.ai.models import model_manager

    monkeypatch.setenv("OPEN_NOTEBOOK_MODEL_ROUTING_POLICY", "local-only")
    model = SimpleNamespace(
        id="model:cloud",
        name="openai/gpt-4.1-mini",
        provider="openrouter",
        type="language",
        credential=None,
    )
    mock_model_get.return_value = model

    with pytest.raises(ConfigurationError, match="selected cloud model is disabled"):
        await model_manager.get_model("model:cloud")
