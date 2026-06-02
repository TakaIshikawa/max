from __future__ import annotations

import pytest

from max.sources.langchain_changelog import LangChainChangelogAdapter
from max.sources.registry import get_adapter, reload_registry


@pytest.mark.asyncio
async def test_langchain_changelog_missing_dates_are_none_and_metadata_kept() -> None:
    signals = await LangChainChangelogAdapter({"entries": [
        {"title": "LangGraph release", "url": "https://langchain.example/changelog/langgraph", "project": "LangGraph", "package": "langgraph"},
    ]}).fetch()

    assert signals[0].source_adapter == "langchain_changelog"
    assert signals[0].published_at is None
    assert signals[0].metadata == {"project": "LangGraph", "package": "langgraph"}
    assert {"ai", "devtools"} <= set(signals[0].tags)


def test_langchain_changelog_registry_instantiates_adapter() -> None:
    reload_registry()
    assert get_adapter("langchain_changelog").name == "langchain_changelog"
