from __future__ import annotations

import pytest

from max.sources.microsoft_python_devblogs import MicrosoftPythonDevBlogsAdapter, parse_microsoft_python_devblogs
from max.sources.registry import get_adapter_class
from max.types.signal import SignalSourceType


def test_microsoft_python_devblogs_normalizes_articles_and_metadata() -> None:
    signals = parse_microsoft_python_devblogs(
        [
            {
                "title": "Python in Visual Studio update",
                "link": "https://devblogs.microsoft.com/python/python-update/?WT.mc_id=x",
                "excerpt": "Tooling update.",
                "date": "2026-05-20T08:00:00Z",
                "author": "Python Team",
                "tags": ["Python", "VS Code", "python"],
            },
            {"title": "Missing URL"},
            {"url": "https://devblogs.microsoft.com/python/missing-title"},
        ]
    )

    assert len(signals) == 1
    signal = signals[0]
    assert signal.id.startswith("microsoft_python_devblogs:")
    assert signal.source_type == SignalSourceType.ARTICLE
    assert signal.url == "https://devblogs.microsoft.com/python/python-update"
    assert signal.content == "Tooling update."
    assert signal.published_at is not None
    assert signal.published_at.isoformat() == "2026-05-20T08:00:00+00:00"
    assert signal.author == "Python Team"
    assert signal.tags == ["microsoft", "python", "devblogs", "VS Code"]
    assert signal.metadata["canonical_url"] == signal.url
    assert signal.metadata["author"] == "Python Team"


def test_microsoft_python_devblogs_limit_and_content_fallback() -> None:
    signals = parse_microsoft_python_devblogs(
        [
            {"title": "First", "url": "https://devblogs.microsoft.com/python/first", "content": "Full post body"},
            {"title": "Second", "url": "https://devblogs.microsoft.com/python/second"},
        ],
        limit=1,
    )

    assert len(signals) == 1
    assert signals[0].content == "Full post body"


@pytest.mark.asyncio
async def test_microsoft_python_devblogs_fetch_reads_configured_entries() -> None:
    adapter = MicrosoftPythonDevBlogsAdapter(config={"entries": [{"title": "A", "url": "https://devblogs.microsoft.com/python/a"}]})

    signals = await adapter.fetch(limit=5)

    assert [signal.title for signal in signals] == ["A"]


def test_microsoft_python_devblogs_registry_fallback_mapping() -> None:
    assert get_adapter_class("microsoft_python_devblogs") is MicrosoftPythonDevBlogsAdapter
