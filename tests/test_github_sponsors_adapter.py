"""Tests for GitHub Sponsors import adapter."""

from __future__ import annotations

import json

import httpx
import pytest

from max.imports.github_sponsors_adapter import GitHubSponsorsImportAdapter
from max.types.signal import SignalSourceType


def _payload(login: str = "acme") -> dict:
    return {
        "data": {
            "user": {
                "login": login,
                "name": "Acme Maintainers",
                "url": f"https://github.com/{login}",
                "sponsorsListing": {
                    "name": "Acme Sponsors",
                    "shortDescription": "Support Acme maintenance.",
                    "tiers": {
                        "nodes": [
                            {
                                "name": "Backer",
                                "description": "Monthly support",
                                "monthlyPriceInDollars": 5,
                                "isOneTime": False,
                                "isCustomAmount": False,
                            },
                            {
                                "name": "Partner",
                                "description": "Commercial support",
                                "monthlyPriceInDollars": 50,
                                "isOneTime": False,
                                "isCustomAmount": False,
                            },
                        ]
                    },
                },
                "sponsorshipsAsMaintainer": {
                    "totalCount": 12,
                    "nodes": [
                        {
                            "isActive": True,
                            "createdAt": "2026-04-01T10:00:00Z",
                            "tier": {
                                "name": "Partner",
                                "monthlyPriceInDollars": 50,
                                "isOneTime": False,
                            },
                            "sponsorEntity": {
                                "login": "octo",
                                "name": "Octo Corp",
                                "url": "https://github.com/octo",
                            },
                        },
                        {
                            "isActive": False,
                            "createdAt": "2026-04-05T10:00:00Z",
                            "tier": {
                                "name": "Backer",
                                "monthlyPriceInDollars": 5,
                                "isOneTime": False,
                            },
                            "sponsorEntity": {
                                "login": "former",
                                "name": None,
                                "url": "https://github.com/former",
                            },
                        },
                    ],
                },
            },
            "organization": None,
        }
    }


def _client(payloads: list[dict | httpx.Response], requests: list[httpx.Request]) -> httpx.AsyncClient:
    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        item = payloads.pop(0)
        if isinstance(item, httpx.Response):
            return item
        return httpx.Response(200, json=item)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_properties_and_configured_accounts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "gh_env")
    adapter = GitHubSponsorsImportAdapter(
        config={"accounts": ["acme", " acme ", "octo"], "activity_limit": 250}
    )

    assert adapter.name == "github_sponsors_import"
    assert adapter.source_type == SignalSourceType.FUNDING.value
    assert adapter.token == "gh_env"
    assert adapter.accounts == ["acme", "octo"]
    assert adapter.activity_limit == 100


@pytest.mark.asyncio
async def test_fetch_maps_sponsor_activity_to_signal() -> None:
    requests: list[httpx.Request] = []
    adapter = GitHubSponsorsImportAdapter(
        config={"accounts": ["acme"], "activity_limit": 10},
        token="gh_token",
        client=_client([_payload()], requests),
    )

    signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    posted = json.loads(requests[0].read())
    assert requests[0].headers["Authorization"] == "Bearer gh_token"
    assert posted["variables"] == {"login": "acme", "first": 10}
    signal = signals[0]
    assert signal.source_type == SignalSourceType.FUNDING
    assert signal.source_adapter == "github_sponsors_import"
    assert signal.title == "Acme Maintainers has GitHub Sponsors activity"
    assert signal.url == "https://github.com/acme"
    assert signal.author == "acme"
    assert signal.published_at is not None
    assert signal.metadata["account"] == "acme"
    assert signal.metadata["sponsor_count"] == 12
    assert signal.metadata["active_sponsor_count"] == 1
    assert signal.metadata["monthly_sponsorship_usd"] == 50.0
    assert signal.metadata["tier_count"] == 2
    assert signal.metadata["tiers"][1]["name"] == "Partner"
    assert signal.metadata["recent_sponsors"][0]["login"] == "octo"
    assert signal.metadata["signal_role"] == "market"
    assert signal.credibility > 0.4
    assert {"github", "github-sponsors", "funding", "community"} <= set(signal.tags)


@pytest.mark.asyncio
async def test_missing_optional_fields_still_normalizes() -> None:
    payload = {
        "data": {
            "user": None,
            "organization": {
                "login": "foundation",
                "name": None,
                "url": None,
                "sponsorsListing": None,
                "sponsorshipsAsMaintainer": {
                    "totalCount": None,
                    "nodes": [
                        {
                            "isActive": True,
                            "createdAt": None,
                            "tier": {"name": "Community", "monthlyPriceInDollars": None},
                            "sponsorEntity": None,
                        }
                    ],
                },
            },
        }
    }
    requests: list[httpx.Request] = []
    adapter = GitHubSponsorsImportAdapter(
        config={"sponsor_accounts": ["foundation"]},
        token="gh_token",
        client=_client([payload], requests),
    )

    signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.title == "foundation has GitHub Sponsors activity"
    assert signal.url == "https://github.com/sponsors/foundation"
    assert signal.published_at is None
    assert signal.metadata["sponsor_count"] == 1
    assert signal.metadata["active_sponsor_count"] == 1
    assert signal.metadata["tiers"] == [
        {
            "name": "Community",
            "description": None,
            "monthly_price_usd": None,
            "is_one_time": False,
            "is_custom_amount": False,
        }
    ]
    assert signal.metadata["recent_sponsors"][0]["login"] is None


@pytest.mark.asyncio
async def test_fetch_respects_limit_across_accounts() -> None:
    requests: list[httpx.Request] = []
    adapter = GitHubSponsorsImportAdapter(
        config={"accounts": ["one", "two"]},
        token="gh_token",
        client=_client([_payload("one"), _payload("two")], requests),
    )

    signals = await adapter.fetch(limit=1)

    assert [signal.metadata["account"] for signal in signals] == ["one"]
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_missing_token_and_fetch_errors_return_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert await GitHubSponsorsImportAdapter(config={"accounts": ["acme"]}).fetch() == []

    requests: list[httpx.Request] = []
    adapter = GitHubSponsorsImportAdapter(
        config={"accounts": ["acme"]},
        token="bad",
        client=_client([httpx.Response(500)], requests),
    )

    assert await adapter.fetch(limit=5) == []


@pytest.mark.asyncio
async def test_graphql_errors_are_skipped() -> None:
    requests: list[httpx.Request] = []
    adapter = GitHubSponsorsImportAdapter(
        config={"accounts": ["acme"]},
        token="gh_token",
        client=_client([{"errors": [{"message": "not found"}]}], requests),
    )

    assert await adapter.fetch(limit=5) == []
