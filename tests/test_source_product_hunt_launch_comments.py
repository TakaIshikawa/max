from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from max.sources.product_hunt_launch_comments import ProductHuntLaunchCommentsAdapter


@pytest.mark.asyncio
async def test_product_hunt_comments_variables_and_maker_filter() -> None:
    adapter = ProductHuntLaunchCommentsAdapter(config={"slugs": ["demo"], "api_url": "https://ph.test/graphql", "token": "secret", "include_maker_replies": False})
    payload = {
        "data": {
            "post": {
                "id": "p1",
                "slug": "demo",
                "name": "Demo",
                "tagline": "Tag",
                "url": "https://ph/demo",
                "comments": {
                    "edges": [
                        {"node": {"id": "c1", "body": "maker", "votesCount": 1, "user": {"username": "m", "isMaker": True}}},
                        {"node": {"id": "c2", "body": "user", "votesCount": 2, "createdAt": "2026-01-01T00:00:00Z", "user": {"username": "u"}}},
                    ]
                },
            }
        }
    }
    with patch("max.sources.product_hunt_launch_comments.httpx.AsyncClient") as cls:
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(return_value=httpx.Response(200, json=payload, request=httpx.Request("POST", "https://ph.test/graphql")))
        cls.return_value = client
        signals = await adapter.fetch(limit=5)
    assert client.post.await_args.kwargs["json"]["variables"]["slug"] == "demo"
    assert cls.call_args.kwargs["headers"]["Authorization"] == "Bearer secret"
    assert len(signals) == 1
    assert signals[0].metadata["commenter_role"] == "community"
    assert "secret" not in repr(signals[0].metadata)
