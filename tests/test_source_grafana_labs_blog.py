from __future__ import annotations

import pytest

from max.sources.grafana_labs_blog import GrafanaLabsBlogAdapter, parse_grafana_labs_blog
from max.sources.registry import get_adapter, reload_registry


def test_parse_grafana_labs_blog_preserves_observability_metadata() -> None:
    payload = [
        {
            "title": "Tracing cost controls",
            "url": "https://grafana.com/blog/tracing-cost-controls/",
            "product": "Tempo",
            "topic": "tracing",
            "tags": ["observability"],
            "author": "Grafana Labs",
        }
    ]

    signal = parse_grafana_labs_blog(payload)[0]

    assert signal.source_adapter == "grafana_labs_blog"
    assert signal.metadata["product"] == "Tempo"
    assert signal.metadata["topic"] == "tracing"
    assert signal.id == parse_grafana_labs_blog(payload)[0].id


@pytest.mark.asyncio
async def test_grafana_labs_blog_fetch_caps_limit() -> None:
    adapter = GrafanaLabsBlogAdapter(
        config={
            "entries": [
                {"title": "One", "url": "https://grafana.com/blog/one/"},
                {"title": "Two", "url": "https://grafana.com/blog/two/"},
            ]
        }
    )

    assert len(await adapter.fetch(limit=1)) == 1


def test_grafana_labs_blog_registry_instantiates_adapter() -> None:
    reload_registry()
    assert isinstance(get_adapter("grafana_labs_blog"), GrafanaLabsBlogAdapter)
