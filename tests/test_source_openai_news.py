from __future__ import annotations

import pytest

from max.sources.openai_news import OpenAINewsAdapter, parse_openai_news


def test_openai_news_normalizes_entries_and_extracts_metadata() -> None:
    signals = parse_openai_news([
        {"title": "Introducing GPT-4.1 in the API", "url": "https://openai.com/news/gpt-4-1?utm=feed", "summary": "Model news"},
        {"title": "Duplicate", "url": "https://openai.com/news/gpt-4-1"},
    ])

    assert len(signals) == 1
    assert signals[0].metadata["model"] == "GPT-4.1"
    assert signals[0].metadata["product"] == "api"
    assert signals[0].content == "Model news"


def test_openai_news_missing_optional_fields_fallback() -> None:
    signals = parse_openai_news([{"title": "ChatGPT product update", "link": "https://openai.com/news/chatgpt-update"}])

    assert signals[0].content == "ChatGPT product update"
    assert signals[0].metadata["product"] == "chatgpt"


@pytest.mark.asyncio
async def test_openai_news_empty_and_limit() -> None:
    assert await OpenAINewsAdapter(config={"entries": []}).fetch(limit=2) == []
    adapter = OpenAINewsAdapter(config={"entries": [{"title": "One", "url": "https://openai.com/news/one"}, {"title": "Two", "url": "https://openai.com/news/two"}]})

    assert [signal.title for signal in await adapter.fetch(limit=1)] == ["One"]
