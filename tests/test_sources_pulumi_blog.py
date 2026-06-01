from __future__ import annotations

import pytest

from max.sources.pulumi_blog import PulumiBlogAdapter, parse_pulumi_blog


def test_pulumi_blog_normalizes_feed_entries() -> None:
    signals = parse_pulumi_blog([{"title": "Kubernetes updates", "url": "https://pulumi.com/blog/k8s", "summary": "Infra post", "published_at": "2026-05-01T00:00:00Z"}])
    assert signals[0].source_adapter == "pulumi_blog"
    assert signals[0].title == "Kubernetes updates"
    assert signals[0].published_at is not None


def test_pulumi_blog_captures_optional_tags() -> None:
    signal = parse_pulumi_blog([{"title": "AWS IaC", "url": "https://pulumi.com/blog/aws", "cloud_provider": "aws", "product": "pulumi cloud"}])[0]
    assert signal.metadata["cloud_provider"] == "aws"
    assert signal.metadata["product"] == "pulumi cloud"


def test_pulumi_blog_empty_feed() -> None:
    assert parse_pulumi_blog({"entries": []}) == []


@pytest.mark.asyncio
async def test_pulumi_blog_adapter_limit() -> None:
    signals = await PulumiBlogAdapter(config={"entries": [{"title": "A", "url": "https://p/a"}, {"title": "B", "url": "https://p/b"}]}).fetch(limit=1)
    assert len(signals) == 1
