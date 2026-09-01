from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client after environment variables have been cleared by conftest."""
    from api.main import app

    return TestClient(app)


class TestSearchLimitValidation:
    """SearchRequest.limit must reject non-positive values (#863)."""

    @pytest.mark.parametrize("bad_limit", [0, -1, -100])
    def test_non_positive_limit_returns_422(self, bad_limit, client):
        response = client.post(
            "/api/search",
            json={"query": "x", "type": "text", "limit": bad_limit},
        )
        assert response.status_code == 422

    def test_limit_above_max_returns_422(self, client):
        response = client.post(
            "/api/search",
            json={"query": "x", "type": "text", "limit": 1001},
        )
        assert response.status_code == 422

    @patch("api.routers.search.text_search", new_callable=AsyncMock)
    def test_valid_limit_returns_200(self, mock_text_search, client):
        mock_text_search.return_value = []
        response = client.post(
            "/api/search",
            json={"query": "x", "type": "text", "limit": 10},
        )
        assert response.status_code == 200
        mock_text_search.assert_awaited_once()


class TestHybridSearchAPI:
    @patch("api.routers.search.hybrid_search", new_callable=AsyncMock)
    @patch(
        "api.routers.search.model_manager.get_embedding_model", new_callable=AsyncMock
    )
    def test_hybrid_search_returns_fused_results(
        self, mock_embedding_model, mock_hybrid_search, client
    ):
        mock_embedding_model.return_value = object()
        mock_hybrid_search.return_value = [
            {
                "id": "source:grounded",
                "parent_id": "source:grounded",
                "title": "Grounded",
                "matches": ["evidence"],
                "final_score": 0.91,
            }
        ]

        response = client.post(
            "/api/search",
            json={"query": "grounded", "type": "hybrid", "limit": 5},
        )

        assert response.status_code == 200
        assert response.json()["search_type"] == "hybrid"
        assert response.json()["results"][0]["final_score"] == 0.91
        mock_hybrid_search.assert_awaited_once_with(
            keyword="grounded",
            results=5,
            source=True,
            note=True,
            minimum_score=0.2,
        )

    @patch(
        "api.routers.search.model_manager.get_embedding_model", new_callable=AsyncMock
    )
    def test_hybrid_search_requires_embedding_model(self, mock_embedding_model, client):
        mock_embedding_model.return_value = None

        response = client.post(
            "/api/search",
            json={"query": "grounded", "type": "hybrid", "limit": 5},
        )

        assert response.status_code == 400
        assert "Hybrid search requires an embedding model" in response.json()["detail"]


class TestTextSearchHighlightOverflowFallback:
    """text_search() must fall back to vector search on a highlight position overflow (#648)."""

    @pytest.mark.asyncio
    async def test_position_overflow_falls_back_to_vector_search(self):
        from open_notebook.domain import notebook as notebook_module

        overflow = RuntimeError(
            "A value can't be highlighted: position overflow: 2545 - len: 1965"
        )
        with (
            patch.object(
                notebook_module,
                "repo_query",
                new_callable=AsyncMock,
                side_effect=overflow,
            ),
            patch.object(
                notebook_module,
                "vector_search",
                new_callable=AsyncMock,
                return_value=[{"id": "source:1"}],
            ) as mock_vector,
        ):
            result = await notebook_module.text_search("hello", 10)

        assert result == [{"id": "source:1"}]
        mock_vector.assert_awaited_once_with("hello", 10, True, True)

    @pytest.mark.asyncio
    async def test_position_overflow_raises_when_vector_also_fails(self):
        from open_notebook.domain import notebook as notebook_module
        from open_notebook.exceptions import DatabaseOperationError

        overflow = RuntimeError("position overflow: 1 - len: 0")
        with (
            patch.object(
                notebook_module,
                "repo_query",
                new_callable=AsyncMock,
                side_effect=overflow,
            ),
            patch.object(
                notebook_module,
                "vector_search",
                new_callable=AsyncMock,
                side_effect=Exception("no embedding model"),
            ),
        ):
            # When both search paths fail, surface the error rather than masking it
            # as an empty result set.
            with pytest.raises(DatabaseOperationError):
                await notebook_module.text_search("hello", 10)

    @pytest.mark.asyncio
    async def test_other_runtime_errors_still_raise(self):
        from open_notebook.domain import notebook as notebook_module
        from open_notebook.exceptions import DatabaseOperationError

        with patch.object(
            notebook_module,
            "repo_query",
            new_callable=AsyncMock,
            side_effect=RuntimeError("some other db failure"),
        ):
            with pytest.raises(DatabaseOperationError):
                await notebook_module.text_search("hello", 10)
