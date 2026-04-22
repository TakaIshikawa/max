"""Tests for GitHub awesome-list markdown source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.awesome_lists import (
    AwesomeListsAdapter,
    github_url_to_raw,
    parse_awesome_markdown,
)
from max.types.signal import SignalSourceType


AWESOME_MARKDOWN = """\
# Awesome Observability

Introductory text should be ignored.

## Metrics

- [Prometheus](https://github.com/prometheus/prometheus) - Monitoring system and time series database.
* [Grafana](https://github.com/grafana/grafana): Dashboards for metrics and logs.
- Missing link entry should not crash.

## Tracing

1. [Jaeger](https://github.com/jaegertracing/jaeger) - Distributed tracing platform.
- [Prometheus Duplicate](https://github.com/prometheus/prometheus) - Same URL as above.
- [Relative Link](/local/path) - Relative URLs are ignored.
"""


def test_parse_awesome_markdown_tracks_section_headings() -> None:
    items = parse_awesome_markdown(AWESOME_MARKDOWN)

    assert [item.title for item in items] == [
        "Prometheus",
        "Grafana",
        "Jaeger",
        "Prometheus Duplicate",
    ]
    assert items[0].description == "Monitoring system and time series database."
    assert items[1].description == "Dashboards for metrics and logs."
    assert items[0].section_heading == "Metrics"
    assert items[2].section_heading == "Tracing"
    assert items[0].raw_line.startswith("- [Prometheus]")


def test_github_url_to_raw_converts_blob_urls() -> None:
    assert github_url_to_raw(
        "https://github.com/sindresorhus/awesome/blob/main/readme.md"
    ) == "https://raw.githubusercontent.com/sindresorhus/awesome/main/readme.md"
    assert github_url_to_raw(
        "https://raw.githubusercontent.com/sindresorhus/awesome/main/readme.md"
    ) == "https://raw.githubusercontent.com/sindresorhus/awesome/main/readme.md"


def test_parse_awesome_markdown_tolerates_malformed_markdown() -> None:
    markdown = """\
## Broken
- [No closing paren](https://example.com
- [](https://example.com/empty-title) - empty titles are ignored
- [Good](https://example.com/good) - valid item
not a list item [Ignored](https://example.com/ignored)
"""

    items = parse_awesome_markdown(markdown)

    assert len(items) == 1
    assert items[0].title == "Good"
    assert items[0].section_heading == "Broken"


class TestAwesomeListsAdapter:
    def test_name_source_type_and_config_properties(self) -> None:
        adapter = AwesomeListsAdapter(config={
            "lists": ["https://example.com/awesome.md"],
            "topics": ["observability"],
            "include_descriptions": False,
            "github_token": "token",
        })

        assert adapter.name == "awesome_lists"
        assert adapter.source_type == SignalSourceType.REGISTRY.value
        assert adapter.lists == ["https://example.com/awesome.md"]
        assert adapter.topics == ["observability"]
        assert adapter.include_descriptions is False
        assert adapter.github_token == "token"

    @pytest.mark.asyncio
    async def test_fetch_converts_markdown_items_to_signals(self) -> None:
        adapter = AwesomeListsAdapter(config={
            "lists": ["https://github.com/sindresorhus/awesome/blob/main/readme.md"],
            "topics": ["observability"],
        })
        mock_resp = MagicMock()
        mock_resp.text = AWESOME_MARKDOWN

        with patch(
            "max.sources.awesome_lists.fetch_with_retry",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ) as mock_fetch:
            signals = await adapter.fetch(limit=10)

        mock_fetch.assert_awaited()
        assert mock_fetch.await_args.args[0] == (
            "https://raw.githubusercontent.com/sindresorhus/awesome/main/readme.md"
        )
        assert len(signals) == 3

        signal = signals[0]
        assert signal.source_type == SignalSourceType.REGISTRY
        assert signal.source_adapter == "awesome_lists"
        assert signal.title == "Prometheus"
        assert signal.url == "https://github.com/prometheus/prometheus"
        assert signal.content == "Monitoring system and time series database."
        assert signal.tags == ["observability", "sindresorhus", "awesome"]
        assert signal.metadata["list_url"] == (
            "https://github.com/sindresorhus/awesome/blob/main/readme.md"
        )
        assert signal.metadata["raw_list_url"] == (
            "https://raw.githubusercontent.com/sindresorhus/awesome/main/readme.md"
        )
        assert signal.metadata["section_heading"] == "Metrics"
        assert signal.metadata["repository_owner"] == "sindresorhus"
        assert signal.metadata["repository_name"] == "awesome"
        assert signal.metadata["raw_line"].startswith("- [Prometheus]")

    @pytest.mark.asyncio
    async def test_fetch_filters_by_topic(self) -> None:
        adapter = AwesomeListsAdapter(config={
            "lists": ["https://example.com/awesome.md"],
            "topics": ["tracing"],
        })
        mock_resp = MagicMock()
        mock_resp.text = AWESOME_MARKDOWN

        with patch(
            "max.sources.awesome_lists.fetch_with_retry",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            signals = await adapter.fetch(limit=10)

        assert [signal.title for signal in signals] == ["Jaeger"]

    @pytest.mark.asyncio
    async def test_fetch_suppresses_duplicate_links(self) -> None:
        adapter = AwesomeListsAdapter(config={"lists": ["https://example.com/awesome.md"]})
        mock_resp = MagicMock()
        mock_resp.text = AWESOME_MARKDOWN

        with patch(
            "max.sources.awesome_lists.fetch_with_retry",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            signals = await adapter.fetch(limit=10)

        assert [signal.url for signal in signals].count("https://github.com/prometheus/prometheus") == 1
        assert len(signals) == 3

    @pytest.mark.asyncio
    async def test_fetch_can_omit_descriptions(self) -> None:
        adapter = AwesomeListsAdapter(config={
            "lists": ["https://example.com/awesome.md"],
            "include_descriptions": False,
        })
        mock_resp = MagicMock()
        mock_resp.text = AWESOME_MARKDOWN

        with patch(
            "max.sources.awesome_lists.fetch_with_retry",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            signals = await adapter.fetch(limit=1)

        assert signals[0].content == ""
