"""Tests for OpenAlex source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.base import AdapterFetchError
from max.sources.openalex import (
    OpenAlexAdapter,
    _normalize_doi,
    _reconstruct_abstract,
)
from max.types.signal import SignalSourceType


MOCK_WORK = {
    "id": "https://openalex.org/W123",
    "doi": "https://doi.org/10.1145/1234567",
    "title": "Tool-Augmented Language Models for Developer Workflows",
    "abstract_inverted_index": {
        "Tool": [0],
        "augmented": [1],
        "models": [3],
        "language": [2],
        "improve": [4],
        "developer": [5],
        "workflows.": [6],
    },
    "publication_date": "2026-04-15",
    "cited_by_count": 42,
    "concepts": [
        {
            "id": "https://openalex.org/C154945302",
            "display_name": "Artificial intelligence",
            "level": 1,
            "score": 0.91,
        },
        {
            "id": "https://openalex.org/C41008148",
            "display_name": "Computer science",
            "level": 0,
            "score": 0.75,
        },
    ],
    "authorships": [
        {"author": {"id": "https://openalex.org/A1", "display_name": "Ada Lovelace"}},
        {"author": {"id": "https://openalex.org/A2", "display_name": "Grace Hopper"}},
    ],
    "primary_location": {
        "landing_page_url": "https://example.org/paper",
        "pdf_url": "https://example.org/paper.pdf",
        "source": {
            "id": "https://openalex.org/S123",
            "display_name": "Journal of Developer Systems",
            "type": "journal",
            "issn_l": "1234-5678",
            "issn": ["1234-5678"],
            "host_organization": "https://openalex.org/P4310319965",
        },
    },
}


def _response(payload: dict) -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = payload
    return response


def test_name_and_source_type() -> None:
    adapter = OpenAlexAdapter()
    assert adapter.name == "openalex"
    assert adapter.source_type == SignalSourceType.ARTICLE.value


def test_reconstruct_abstract_orders_inverted_index() -> None:
    assert _reconstruct_abstract({"world": [1], "hello": [0]}) == "hello world"


def test_normalize_doi_strips_url_prefix() -> None:
    assert _normalize_doi("https://doi.org/10.1145/1234567") == "10.1145/1234567"


@pytest.mark.asyncio
async def test_fetch_maps_openalex_work_to_signal() -> None:
    adapter = OpenAlexAdapter(config={"search_terms": ["developer tools"], "per_page": 10})

    with patch(
        "max.sources.openalex.fetch_with_retry",
        new_callable=AsyncMock,
        return_value=_response({"results": [MOCK_WORK]}),
    ) as mock_fetch:
        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.source_type == SignalSourceType.ARTICLE
    assert signal.source_adapter == "openalex"
    assert signal.title == "Tool-Augmented Language Models for Developer Workflows"
    assert signal.content == "Tool augmented language models improve developer workflows."
    assert signal.url == "https://doi.org/10.1145/1234567"
    assert signal.author == "Ada Lovelace"
    assert signal.published_at is not None
    assert signal.published_at.year == 2026
    assert signal.published_at.month == 4
    assert signal.metadata["doi"] == "10.1145/1234567"
    assert signal.metadata["cited_by_count"] == 42
    assert signal.metadata["authors"] == ["Ada Lovelace", "Grace Hopper"]
    assert signal.metadata["concepts"][0]["display_name"] == "Artificial intelligence"
    assert signal.metadata["venue"]["display_name"] == "Journal of Developer Systems"
    assert "artificial-intelligence" in signal.tags

    params = mock_fetch.await_args.kwargs["params"]
    assert params["search"] == "developer tools"
    assert params["per-page"] == 5


@pytest.mark.asyncio
async def test_fetch_uses_title_when_abstract_is_empty() -> None:
    work = {**MOCK_WORK, "id": "https://openalex.org/W456", "abstract_inverted_index": None}
    adapter = OpenAlexAdapter(config={"search_terms": ["developer tools"]})

    with patch(
        "max.sources.openalex.fetch_with_retry",
        new_callable=AsyncMock,
        return_value=_response({"results": [work]}),
    ):
        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert signals[0].content == work["title"]


@pytest.mark.asyncio
async def test_fetch_passes_date_concept_and_mailto_filters() -> None:
    adapter = OpenAlexAdapter(config={
        "search_terms": ["clinical ai"],
        "concepts": ["https://openalex.org/C154945302", "C41008148"],
        "from_publication_date": "2026-01-01",
        "per_page": 50,
        "mailto": "research@example.com",
    })

    with patch(
        "max.sources.openalex.fetch_with_retry",
        new_callable=AsyncMock,
        return_value=_response({"results": []}),
    ) as mock_fetch:
        signals = await adapter.fetch(limit=20)

    assert signals == []
    params = mock_fetch.await_args.kwargs["params"]
    assert params["search"] == "clinical ai"
    assert params["per-page"] == 20
    assert params["mailto"] == "research@example.com"
    assert params["filter"] == "from_publication_date:2026-01-01,concepts.id:C154945302|C41008148"
    assert params["sort"] == "publication_date:desc"


@pytest.mark.asyncio
async def test_fetch_propagates_retry_errors() -> None:
    adapter = OpenAlexAdapter(config={"search_terms": ["developer tools"]})
    error = AdapterFetchError("openalex", 503, "https://api.openalex.org/works")

    with patch(
        "max.sources.openalex.fetch_with_retry",
        new_callable=AsyncMock,
        side_effect=error,
    ):
        with pytest.raises(AdapterFetchError) as exc_info:
            await adapter.fetch(limit=1)

    assert exc_info.value is error
