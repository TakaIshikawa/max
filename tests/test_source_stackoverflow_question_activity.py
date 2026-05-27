from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from max.sources.stackoverflow_question_activity import StackOverflowQuestionActivityAdapter


@pytest.mark.asyncio
async def test_stackoverflow_question_activity_params_and_unresolved_status() -> None:
    adapter = StackOverflowQuestionActivityAdapter(config={"tags": ["python"], "query": "mcp", "min_score": 2, "site": "stackoverflow", "stackexchange_api_url": "https://se.test"})
    response = httpx.Response(200, json={"items": [{"question_id": 1, "title": "How?", "score": 3, "answer_count": 2, "view_count": 10, "tags": ["python"], "last_activity_date": 10, "link": "https://so/q/1"}], "backoff": 1, "quota_remaining": 10}, request=httpx.Request("GET", "https://se.test/search/advanced"))
    with patch("max.sources.stackoverflow_question_activity.httpx.AsyncClient") as cls:
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.get = AsyncMock(return_value=response)
        cls.return_value = client
        signals = await adapter.fetch(limit=5)
    params = client.get.await_args.kwargs["params"]
    assert params["tagged"] == "python"
    assert params["intitle"] == "mcp"
    assert params["min"] == 2
    assert signals[0].metadata["resolution_status"] == "unresolved"
