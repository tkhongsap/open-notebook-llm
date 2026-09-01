from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from open_notebook.exceptions import DatabaseOperationError
from open_notebook.retrieval import (
    INSUFFICIENT_EVIDENCE_ANSWER,
    canonicalize_reference_id,
    enforce_grounded_answer,
    extract_reference_ids,
    fuse_and_rerank,
    hybrid_search,
    prepare_grounding_results,
)


def test_hybrid_fusion_deduplicates_and_preserves_both_evidence_channels():
    text_results = [
        {
            "id": "source:harborlight",
            "parent_id": "source:harborlight",
            "title": "Harborlight budget",
            "matches": ["The `Harborlight` budget is $4 million."],
            "relevance": -0.4,
        }
    ]
    vector_results = [
        {
            "id": "source:harborlight",
            "parent_id": "source:harborlight",
            "title": "Harborlight budget",
            "matches": ["Funding is capped at four million dollars."],
            "similarity": 0.92,
        }
    ]

    results = fuse_and_rerank(
        "Harborlight budget", text_results, vector_results, limit=10
    )

    assert len(results) == 1
    assert results[0]["id"] == "source:harborlight"
    assert results[0]["parent_id"] == "source:harborlight"
    assert results[0]["retrieval_sources"] == ["text", "vector"]
    assert results[0]["matches"] == [
        "The `Harborlight` budget is $4 million.",
        "Funding is capped at four million dollars.",
    ]
    assert results[0]["final_score"] > 0.9


def test_local_reranking_promotes_exact_evidence_over_rank_one_noise():
    text_results = [
        {
            "id": "source:noise",
            "title": "General project update",
            "matches": ["The weather was calm."],
        },
        {
            "id": "source:exact",
            "title": "Harborlight budget",
            "matches": ["The Harborlight budget was approved."],
        },
    ]

    results = fuse_and_rerank("Harborlight budget", text_results, [], limit=2)

    assert [result["id"] for result in results] == [
        "source:exact",
        "source:noise",
    ]
    assert results[0]["rerank_score"] > results[1]["rerank_score"]


def test_hybrid_fusion_removes_whitespace_only_duplicate_matches():
    rows = [
        {
            "id": "source:one",
            "title": "One",
            "matches": ["Exact excerpt\n", "Exact excerpt"],
        }
    ]

    results = fuse_and_rerank("excerpt", rows, [], limit=1)

    assert results[0]["matches"] == ["Exact excerpt"]


@pytest.mark.asyncio
async def test_hybrid_search_uses_expanded_candidate_pool_and_requested_limit():
    text_rows = [{"id": "source:text", "title": "Text", "matches": ["query"]}]
    vector_rows = [{"id": "source:vector", "title": "Vector", "matches": ["query"]}]
    with (
        patch(
            "open_notebook.domain.notebook.text_search",
            new_callable=AsyncMock,
            return_value=text_rows,
        ) as text_mock,
        patch(
            "open_notebook.domain.notebook.vector_search",
            new_callable=AsyncMock,
            return_value=vector_rows,
        ) as vector_mock,
    ):
        results = await hybrid_search("query", 1, minimum_score=0.4)

    assert len(results) == 1
    text_mock.assert_awaited_once_with("query", 3, True, True)
    vector_mock.assert_awaited_once_with("query", 3, True, True, 0.4)


@pytest.mark.asyncio
async def test_hybrid_search_degrades_to_one_healthy_channel():
    with (
        patch(
            "open_notebook.domain.notebook.text_search",
            new_callable=AsyncMock,
            side_effect=RuntimeError("lexical unavailable"),
        ),
        patch(
            "open_notebook.domain.notebook.vector_search",
            new_callable=AsyncMock,
            return_value=[
                {
                    "id": "note:semantic",
                    "title": "Semantic",
                    "matches": ["answer evidence"],
                }
            ],
        ),
    ):
        results = await hybrid_search("answer", 5)

    assert [result["id"] for result in results] == ["note:semantic"]


@pytest.mark.asyncio
async def test_hybrid_search_raises_when_both_channels_fail():
    with (
        patch(
            "open_notebook.domain.notebook.text_search",
            new_callable=AsyncMock,
            side_effect=RuntimeError("text down"),
        ),
        patch(
            "open_notebook.domain.notebook.vector_search",
            new_callable=AsyncMock,
            side_effect=RuntimeError("vector down"),
        ),
    ):
        with pytest.raises(DatabaseOperationError, match="Both hybrid"):
            await hybrid_search("answer", 5)


def test_grounding_results_are_bounded_and_require_exact_evidence():
    prepared = prepare_grounding_results(
        [
            {
                "id": "source:good",
                "title": "Good source",
                "matches": ["A" * 20, "second", "third"],
                "final_score": 0.8,
            },
            {"id": "source:no_evidence", "title": "No evidence"},
        ],
        max_matches=2,
        max_match_characters=5,
    )

    assert prepared == [
        {
            "id": "source:good",
            "title": "Good source",
            "matches": ["AAAAA", "secon"],
            "final_score": 0.8,
        }
    ]


def test_citations_are_canonical_exact_and_fabricated_ids_are_not_clickable():
    answer = (
        "Supported [insight:real-one]. Fabricated [source:made-up]. "
        "Repeated [source_insight:real-one]."
    )

    grounded = enforce_grounded_answer(answer, ["source_insight:real-one"])

    assert "[source_insight:real-one]" in grounded
    assert "source:made-up" not in grounded
    assert "citation unavailable" in grounded
    assert extract_reference_ids(grounded) == ["source_insight:real-one"]


@pytest.mark.parametrize(
    "answer,allowed",
    [
        ("An unsupported answer with no citation.", ["source:available"]),
        ("A fabricated answer [source:fake].", ["source:available"]),
        ("Anything", []),
    ],
)
def test_answers_without_allowed_evidence_fail_closed(answer, allowed):
    assert enforce_grounded_answer(answer, allowed) == INSUFFICIENT_EVIDENCE_ANSWER


def test_reference_ids_support_hyphens_and_reject_unknown_types():
    assert canonicalize_reference_id("insight:abc-123") == ("source_insight:abc-123")
    assert canonicalize_reference_id("website:abc") is None


def test_lexical_migration_returns_matches_and_is_registered():
    root = Path(__file__).resolve().parents[1]
    migration = (root / "open_notebook/database/migrations/24.surrealql").read_text(
        encoding="utf-8"
    )
    manager = (root / "open_notebook/database/async_migrate.py").read_text(
        encoding="utf-8"
    )

    assert "array::flatten(content) as matches" in migration
    assert "migrations/24.surrealql" in manager
    assert "migrations/24_down.surrealql" in manager
