"""Tests for fetch_with_retry and adapter exception types."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.sources.base import (
    AdapterFetchError,
    AdapterRateLimitError,
    fetch_with_retry,
)


def _mock_response(status_code: int) -> httpx.Response:
    """Create a minimal httpx.Response with the given status code."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    return resp


def _mock_client(*status_codes: int) -> httpx.AsyncClient:
    """Return a mock AsyncClient whose .request() yields responses in order."""
    responses = [_mock_response(code) for code in status_codes]
    client = AsyncMock(spec=httpx.AsyncClient)
    client.request = AsyncMock(side_effect=responses)
    return client


# ── Exception types ──────────────────────────────────────────────────


class TestAdapterFetchError:
    def test_attributes(self) -> None:
        err = AdapterFetchError("reddit", 404, "https://example.com")
        assert err.adapter_name == "reddit"
        assert err.status_code == 404
        assert err.url == "https://example.com"
        assert "reddit" in str(err)
        assert "404" in str(err)

    def test_is_exception(self) -> None:
        assert issubclass(AdapterFetchError, Exception)


class TestAdapterRateLimitError:
    def test_inherits_fetch_error(self) -> None:
        err = AdapterRateLimitError("github", "https://api.github.com")
        assert isinstance(err, AdapterFetchError)
        assert err.status_code == 429

    def test_attributes(self) -> None:
        err = AdapterRateLimitError("github", "https://api.github.com")
        assert err.adapter_name == "github"
        assert err.url == "https://api.github.com"


# ── Successful fetch (no retry) ─────────────────────────────────────


@pytest.mark.asyncio
async def test_success_on_first_attempt() -> None:
    client = _mock_client(200)
    resp = await fetch_with_retry(
        "https://example.com/api", client, adapter_name="test",
    )
    assert resp.status_code == 200
    client.request.assert_awaited_once()


@pytest.mark.asyncio
async def test_passes_request_kwargs() -> None:
    client = _mock_client(200)
    await fetch_with_retry(
        "https://example.com/api",
        client,
        adapter_name="test",
        params={"q": "hello"},
    )
    client.request.assert_awaited_once_with(
        "GET", "https://example.com/api", params={"q": "hello"},
    )


@pytest.mark.asyncio
async def test_post_method() -> None:
    client = _mock_client(200)
    await fetch_with_retry(
        "https://example.com/graphql",
        client,
        adapter_name="test",
        method="POST",
        json={"query": "{}"},
    )
    client.request.assert_awaited_once_with(
        "POST", "https://example.com/graphql", json={"query": "{}"},
    )


# ── Retry on 429 ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_on_429_then_success() -> None:
    client = _mock_client(429, 200)
    with patch("max.sources.base.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        resp = await fetch_with_retry(
            "https://example.com/api",
            client,
            adapter_name="test",
            max_retries=2,
            backoff_base=1.0,
        )
    assert resp.status_code == 200
    assert client.request.await_count == 2
    # First retry: backoff_base * 2^0 = 1.0
    mock_sleep.assert_awaited_once_with(1.0)


@pytest.mark.asyncio
async def test_429_exhausted_raises_rate_limit_error() -> None:
    client = _mock_client(429, 429, 429)
    with patch("max.sources.base.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(AdapterRateLimitError) as exc_info:
            await fetch_with_retry(
                "https://example.com/api",
                client,
                adapter_name="test",
                max_retries=2,
                backoff_base=0.1,
            )
    assert exc_info.value.status_code == 429
    assert exc_info.value.adapter_name == "test"
    assert client.request.await_count == 3  # 1 initial + 2 retries


# ── Retry on 5xx ─────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [500, 502, 503])
async def test_retry_on_5xx_then_success(status_code: int) -> None:
    client = _mock_client(status_code, 200)
    with patch("max.sources.base.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        resp = await fetch_with_retry(
            "https://example.com/api",
            client,
            adapter_name="test",
            max_retries=2,
            backoff_base=1.0,
        )
    assert resp.status_code == 200
    assert client.request.await_count == 2
    mock_sleep.assert_awaited_once_with(1.0)


@pytest.mark.asyncio
async def test_5xx_exhausted_raises_fetch_error() -> None:
    client = _mock_client(503, 503, 503)
    with patch("max.sources.base.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(AdapterFetchError) as exc_info:
            await fetch_with_retry(
                "https://example.com/api",
                client,
                adapter_name="test",
                max_retries=2,
            )
    assert exc_info.value.status_code == 503
    assert not isinstance(exc_info.value, AdapterRateLimitError)


# ── No retry on non-retryable 4xx ────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 422])
async def test_no_retry_on_client_errors(status_code: int) -> None:
    client = _mock_client(status_code)
    with pytest.raises(AdapterFetchError) as exc_info:
        await fetch_with_retry(
            "https://example.com/api",
            client,
            adapter_name="test",
            max_retries=2,
        )
    assert exc_info.value.status_code == status_code
    # Only one request — no retries attempted.
    client.request.assert_awaited_once()


# ── Exponential backoff timing ───────────────────────────────────────


@pytest.mark.asyncio
async def test_backoff_is_exponential() -> None:
    # 3 failures then success: expects sleeps of 1.0, 2.0, 4.0
    client = _mock_client(500, 500, 500, 200)
    with patch("max.sources.base.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        resp = await fetch_with_retry(
            "https://example.com/api",
            client,
            adapter_name="test",
            max_retries=3,
            backoff_base=1.0,
        )
    assert resp.status_code == 200
    assert client.request.await_count == 4
    delays = [call.args[0] for call in mock_sleep.await_args_list]
    assert delays == [1.0, 2.0, 4.0]


@pytest.mark.asyncio
async def test_custom_backoff_base() -> None:
    client = _mock_client(502, 502, 200)
    with patch("max.sources.base.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await fetch_with_retry(
            "https://example.com/api",
            client,
            adapter_name="test",
            max_retries=2,
            backoff_base=0.5,
        )
    delays = [call.args[0] for call in mock_sleep.await_args_list]
    # 0.5 * 2^0 = 0.5, 0.5 * 2^1 = 1.0
    assert delays == [0.5, 1.0]


# ── Zero retries ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_zero_retries_raises_immediately_on_5xx() -> None:
    client = _mock_client(500)
    with pytest.raises(AdapterFetchError) as exc_info:
        await fetch_with_retry(
            "https://example.com/api",
            client,
            adapter_name="test",
            max_retries=0,
        )
    assert exc_info.value.status_code == 500
    client.request.assert_awaited_once()


# ── Logging ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_logs_warning(caplog) -> None:
    client = _mock_client(429, 200)
    with patch("max.sources.base.asyncio.sleep", new_callable=AsyncMock):
        import logging

        with caplog.at_level(logging.WARNING, logger="max.sources.base"):
            await fetch_with_retry(
                "https://example.com/api",
                client,
                adapter_name="mytest",
                max_retries=2,
                backoff_base=1.0,
            )
    assert any("mytest" in msg and "429" in msg for msg in caplog.messages)
