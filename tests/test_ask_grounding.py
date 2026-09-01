from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables import RunnableConfig

from open_notebook.graphs.ask import SubGraphState, ThreadState
from open_notebook.retrieval import INSUFFICIENT_EVIDENCE_ANSWER


def _config() -> RunnableConfig:
    return {
        "configurable": {
            "answer_model": "model:answer",
            "final_answer_model": "model:final",
        }
    }


@pytest.mark.asyncio
async def test_subanswer_uses_hybrid_evidence_and_keeps_exact_citations():
    from open_notebook.graphs import ask

    model = MagicMock()
    model.ainvoke = AsyncMock(
        return_value=MagicMock(
            content="The budget is four million. [source:harbor-light]"
        )
    )
    state = cast(
        SubGraphState,
        {
            "question": "What is the budget?",
            "term": "Harborlight budget",
            "instructions": "Find the approved budget",
        },
    )

    with (
        patch.object(
            ask,
            "hybrid_search",
            new_callable=AsyncMock,
            return_value=[
                {
                    "id": "source:harbor-light",
                    "title": "Budget",
                    "matches": ["The approved budget is four million."],
                    "final_score": 0.9,
                }
            ],
        ) as search_mock,
        patch.object(
            ask, "provision_langchain_model", new_callable=AsyncMock, return_value=model
        ),
        patch.object(ask, "Prompter") as prompter,
    ):
        prompter.return_value.render.return_value = "grounding prompt"
        result = await ask.provide_answer(state, _config())

    search_mock.assert_awaited_once_with("Harborlight budget", 10, True, True)
    assert result == {
        "answers": ["The budget is four million. [source:harbor-light]"],
        "evidence_ids": ["source:harbor-light"],
    }


@pytest.mark.asyncio
async def test_subanswer_with_fabricated_citation_is_discarded():
    from open_notebook.graphs import ask

    model = MagicMock()
    model.ainvoke = AsyncMock(
        return_value=MagicMock(content="Made up claim. [source:fabricated]")
    )
    state = cast(
        SubGraphState,
        {"question": "Question", "term": "term", "instructions": "instructions"},
    )

    with (
        patch.object(
            ask,
            "hybrid_search",
            new_callable=AsyncMock,
            return_value=[
                {
                    "id": "source:real",
                    "title": "Real",
                    "matches": ["Real evidence"],
                }
            ],
        ),
        patch.object(
            ask, "provision_langchain_model", new_callable=AsyncMock, return_value=model
        ),
        patch.object(ask, "Prompter") as prompter,
    ):
        prompter.return_value.render.return_value = "grounding prompt"
        result = await ask.provide_answer(state, _config())

    assert result == {"answers": [], "evidence_ids": []}


@pytest.mark.asyncio
async def test_final_answer_fails_closed_without_cited_evidence():
    from open_notebook.graphs import ask

    state = cast(
        ThreadState,
        {
            "question": "Question",
            "strategy": ask.Strategy(reasoning="reason", searches=[]),
            "answers": [],
            "evidence_ids": [],
        },
    )

    with patch.object(
        ask, "provision_langchain_model", new_callable=AsyncMock
    ) as provision:
        result = await ask.write_final_answer(state, _config())

    assert result == {"final_answer": INSUFFICIENT_EVIDENCE_ANSWER}
    provision.assert_not_awaited()


@pytest.mark.asyncio
async def test_final_answer_removes_citations_outside_evidence_set():
    from open_notebook.graphs import ask

    model = MagicMock()
    model.ainvoke = AsyncMock(
        return_value=MagicMock(
            content=("Supported. [note:real] Unsupported citation. [source:fake]")
        )
    )
    state = cast(
        ThreadState,
        {
            "question": "Question",
            "strategy": ask.Strategy(reasoning="reason", searches=[]),
            "answers": ["Evidence. [note:real]"],
            "evidence_ids": ["note:real"],
        },
    )

    with (
        patch.object(
            ask, "provision_langchain_model", new_callable=AsyncMock, return_value=model
        ),
        patch.object(ask, "Prompter") as prompter,
    ):
        prompter.return_value.render.return_value = "final prompt"
        result = await ask.write_final_answer(state, _config())

    assert "[note:real]" in result["final_answer"]
    assert "source:fake" not in result["final_answer"]
    assert "citation unavailable" in result["final_answer"]
