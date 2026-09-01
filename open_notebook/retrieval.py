"""Hybrid retrieval, deterministic reranking, and citation safeguards."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Iterable, Sequence
from typing import Any

from loguru import logger

from open_notebook.exceptions import DatabaseOperationError, InvalidInputError

SearchResult = dict[str, Any]

RRF_K = 60
REFERENCE_PATTERN = re.compile(
    r"(?P<type>source_insight|insight|note|source):(?P<id>[A-Za-z0-9_-]{1,100})"
)
TOKEN_PATTERN = re.compile(r"[\w]+", re.UNICODE)
INSUFFICIENT_EVIDENCE_ANSWER = (
    "I couldn't find enough supporting evidence in your sources to answer that "
    "reliably. Try rephrasing the question or add a source that covers this topic."
)


def canonicalize_reference_id(value: Any) -> str | None:
    """Return a safe, canonical citation ID or ``None`` for invalid values."""

    reference = str(value or "").strip()
    match = REFERENCE_PATTERN.fullmatch(reference)
    if not match:
        return None
    reference_type = match.group("type")
    if reference_type == "insight":
        reference_type = "source_insight"
    return f"{reference_type}:{match.group('id')}"


def extract_reference_ids(text: str) -> list[str]:
    """Extract unique citation IDs in their first-occurrence order."""

    found: list[str] = []
    for match in REFERENCE_PATTERN.finditer(text or ""):
        reference = canonicalize_reference_id(match.group(0))
        if reference and reference not in found:
            found.append(reference)
    return found


def enforce_grounded_answer(answer: str, allowed_ids: Iterable[Any]) -> str:
    """Remove fabricated citations and reject answers with no allowed citation."""

    allowed = {
        reference
        for value in allowed_ids
        if (reference := canonicalize_reference_id(value)) is not None
    }
    if not allowed:
        return INSUFFICIENT_EVIDENCE_ANSWER

    def replace_reference(match: re.Match[str]) -> str:
        reference = canonicalize_reference_id(match.group(0))
        return reference if reference in allowed else "citation unavailable"

    sanitized = REFERENCE_PATTERN.sub(replace_reference, answer or "").strip()
    if not allowed.intersection(extract_reference_ids(sanitized)):
        return INSUFFICIENT_EVIDENCE_ANSWER
    return sanitized


def _tokens(text: str) -> set[str]:
    return {token.casefold() for token in TOKEN_PATTERN.findall(text or "")}


def _flatten_matches(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        flattened: list[str] = []
        for item in value:
            flattened.extend(_flatten_matches(item))
        return flattened
    rendered = str(value).strip()
    return [rendered] if rendered else []


def _merge_matches(existing: list[str], incoming: Any) -> list[str]:
    for match in _flatten_matches(incoming):
        if match not in existing:
            existing.append(match)
    return existing


def _local_rerank_score(query: str, result: SearchResult) -> float:
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.0

    title = str(result.get("title") or "")
    evidence = " ".join(_flatten_matches(result.get("matches")))
    title_coverage = len(query_tokens.intersection(_tokens(title))) / len(query_tokens)
    evidence_coverage = len(query_tokens.intersection(_tokens(evidence))) / len(
        query_tokens
    )
    normalized_query = " ".join(TOKEN_PATTERN.findall(query.casefold()))
    normalized_document = " ".join(
        TOKEN_PATTERN.findall(f"{title} {evidence}".casefold())
    )
    phrase_match = float(
        bool(normalized_query and normalized_query in normalized_document)
    )
    return min(
        1.0,
        (0.55 * evidence_coverage) + (0.30 * title_coverage) + (0.15 * phrase_match),
    )


def fuse_and_rerank(
    query: str,
    text_results: Sequence[SearchResult],
    vector_results: Sequence[SearchResult],
    *,
    limit: int,
) -> list[SearchResult]:
    """Fuse lexical/semantic ranks, deduplicate entities, and locally rerank."""

    if limit < 1:
        raise InvalidInputError("Search result limit must be positive")

    fused: dict[str, SearchResult] = {}
    channel_count = int(bool(text_results)) + int(bool(vector_results))
    channel_count = max(channel_count, 1)

    for channel, rows in (("text", text_results), ("vector", vector_results)):
        for rank, row in enumerate(rows, start=1):
            reference_id = canonicalize_reference_id(row.get("id"))
            if not reference_id:
                continue

            result = fused.setdefault(
                reference_id,
                {
                    **row,
                    "id": reference_id,
                    "parent_id": reference_id,
                    "citation_id": reference_id,
                    "matches": [],
                    "retrieval_sources": [],
                    "rrf_score": 0.0,
                },
            )
            for key, value in row.items():
                if key in {"matches", "content"}:
                    continue
                if key not in result or result[key] in (None, "", []):
                    result[key] = value
            _merge_matches(result["matches"], row.get("matches", row.get("content")))
            result["rrf_score"] += 1.0 / (RRF_K + rank)
            result[f"{channel}_rank"] = rank
            if channel not in result["retrieval_sources"]:
                result["retrieval_sources"].append(channel)
            if channel == "text" and "relevance" in row:
                result["lexical_score"] = row["relevance"]
            if channel == "vector" and "similarity" in row:
                result["semantic_score"] = row["similarity"]

    maximum_rrf = channel_count / (RRF_K + 1)
    for result in fused.values():
        result["rerank_score"] = _local_rerank_score(query, result)
        normalized_rrf = float(result["rrf_score"]) / maximum_rrf
        result["final_score"] = round(
            min(1.0, (0.70 * normalized_rrf) + (0.30 * result["rerank_score"])),
            6,
        )

    return sorted(
        fused.values(),
        key=lambda result: (
            -float(result["final_score"]),
            -float(result["rrf_score"]),
            str(result["id"]),
        ),
    )[:limit]


async def hybrid_search(
    keyword: str,
    results: int,
    source: bool = True,
    note: bool = True,
    minimum_score: float = 0.2,
) -> list[SearchResult]:
    """Search lexical and vector indexes concurrently, then fuse and rerank."""

    if not keyword or not keyword.strip():
        raise InvalidInputError("Search keyword cannot be empty")
    if results < 1:
        raise InvalidInputError("Search result limit must be positive")

    # Import lazily to keep the domain module independent from this orchestration
    # layer and make each retrieval channel straightforward to unit test.
    from open_notebook.domain.notebook import text_search, vector_search

    candidate_limit = min(max(results * 3, results), 1000)
    outcomes: Any = await asyncio.gather(
        text_search(keyword, candidate_limit, source, note),
        vector_search(keyword, candidate_limit, source, note, minimum_score),
        return_exceptions=True,
    )
    text_outcome: Any = outcomes[0]
    vector_outcome: Any = outcomes[1]

    text_rows: Sequence[SearchResult] = []
    vector_rows: Sequence[SearchResult] = []
    failures: list[BaseException] = []
    if isinstance(text_outcome, BaseException):
        failures.append(text_outcome)
        logger.warning("Lexical retrieval failed; using semantic candidates only")
    else:
        text_rows = text_outcome or []
    if isinstance(vector_outcome, BaseException):
        failures.append(vector_outcome)
        logger.warning("Semantic retrieval failed; using lexical candidates only")
    else:
        vector_rows = vector_outcome or []

    if len(failures) == 2:
        raise DatabaseOperationError(
            "Both hybrid retrieval channels failed"
        ) from failures[0]

    return fuse_and_rerank(
        keyword,
        text_rows,
        vector_rows,
        limit=results,
    )


def prepare_grounding_results(
    results: Sequence[SearchResult],
    *,
    max_matches: int = 4,
    max_match_characters: int = 1600,
) -> list[SearchResult]:
    """Reduce search results to bounded, exact evidence sent to answer models."""

    prepared: list[SearchResult] = []
    for result in results:
        reference_id = canonicalize_reference_id(result.get("id"))
        if not reference_id:
            continue
        matches = [
            match[:max_match_characters]
            for match in _flatten_matches(result.get("matches", result.get("content")))
            if match.strip()
        ][:max_matches]
        if not matches:
            continue
        prepared.append(
            {
                "id": reference_id,
                "title": str(result.get("title") or "Untitled"),
                "matches": matches,
                "final_score": result.get("final_score"),
            }
        )
    return prepared
