from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.artifact_service import ARTIFACT_SPECS, generate_notebook_artifact
from open_notebook.ai.provision import ModelExecutionInfo
from open_notebook.exceptions import InvalidInputError, NotFoundError


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


@pytest.mark.asyncio
@pytest.mark.parametrize("artifact_kind", list(ARTIFACT_SPECS))
@patch("api.artifact_service.Note")
@patch(
    "api.artifact_service.provision_langchain_model_with_info",
    new_callable=AsyncMock,
)
@patch("api.artifact_service.Notebook.get", new_callable=AsyncMock)
async def test_each_artifact_kind_is_grounded_saved_and_linked(
    mock_get, mock_provision, mock_note_cls, artifact_kind
):
    notebook = AsyncMock()
    notebook.get_context.return_value = (
        "## Source: Evidence [source:abc]\n\nVerified material"
    )
    mock_get.return_value = notebook

    chain = AsyncMock()
    chain.ainvoke.return_value = SimpleNamespace(
        content="# Result\n\nSupported claim [source:abc]"
    )
    execution = ModelExecutionInfo(
        id="model:local",
        name="sandbox/qwen",
        provider="openai_compatible",
        provider_display_name="Local AI / OpenAI Compatible",
        location="local",
        selection_reason="explicit",
    )
    mock_provision.return_value = (chain, execution)

    note = AsyncMock()
    note.id = "note:generated"
    note.save.return_value = "command:embed"
    mock_note_cls.return_value = note

    result, command_id, used_model = await generate_notebook_artifact(
        "notebook:one",
        artifact_kind,
        custom_instructions="Focus on decisions",
        model_id="model:local",
    )

    assert result is note
    assert command_id == "command:embed"
    assert used_model is execution
    mock_provision.assert_awaited_once()
    provision_args = mock_provision.await_args.args
    assert provision_args[1] == "model:local"
    assert provision_args[2] == "transformation"
    await_args = chain.ainvoke.await_args.args[0]
    assert "Focus on decisions" in await_args[0].content
    assert "source:abc" in await_args[1].content
    mock_note_cls.assert_called_once_with(
        title=ARTIFACT_SPECS[artifact_kind].title,
        content="# Result\n\nSupported claim [source:abc]",
        note_type="ai",
    )
    note.save.assert_awaited_once()
    note.add_to_notebook.assert_awaited_once_with("notebook:one")


@pytest.mark.asyncio
@patch("api.artifact_service.Notebook.get", new_callable=AsyncMock)
async def test_artifact_requires_substantive_notebook_context(mock_get):
    notebook = AsyncMock()
    notebook.get_context.return_value = "   "
    mock_get.return_value = notebook

    with pytest.raises(InvalidInputError, match="Add at least one"):
        await generate_notebook_artifact("notebook:empty", "study_guide")


@patch("api.routers.artifacts.generate_notebook_artifact", new_callable=AsyncMock)
def test_artifact_endpoint_returns_durable_note(mock_generate, client):
    execution = ModelExecutionInfo(
        id="model:cloud",
        name="openai/gpt-4.1-mini",
        provider="openrouter",
        provider_display_name="OpenRouter",
        location="cloud",
        selection_reason="explicit",
    )
    mock_generate.return_value = (
        SimpleNamespace(
            id="note:generated",
            title="Study guide",
            content="Grounded content [source:abc]",
            note_type="ai",
            created="2026-08-31T00:00:00Z",
            updated="2026-08-31T00:00:00Z",
        ),
        "command:embed",
        execution,
    )

    response = client.post(
        "/api/notebooks/notebook:one/artifacts",
        json={"artifact_kind": "study_guide"},
    )

    assert response.status_code == 200
    assert response.json()["artifact_kind"] == "study_guide"
    assert response.json()["id"] == "note:generated"
    assert response.json()["model"] == execution.to_dict()


def test_artifact_endpoint_rejects_unknown_kind(client):
    response = client.post(
        "/api/notebooks/notebook:one/artifacts",
        json={"artifact_kind": "cinematic_magic"},
    )
    assert response.status_code == 422


@patch("api.routers.artifacts.generate_notebook_artifact", new_callable=AsyncMock)
def test_artifact_endpoint_maps_missing_notebook_to_404(mock_generate, client):
    mock_generate.side_effect = NotFoundError("missing")
    response = client.post(
        "/api/notebooks/notebook:missing/artifacts",
        json={"artifact_kind": "faq"},
    )
    assert response.status_code == 404
