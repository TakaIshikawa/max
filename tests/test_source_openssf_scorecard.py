"""Tests for the OpenSSF Scorecard source adapter."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest

from max.sources.openssf_scorecard import (
    OpenSSFScorecardAdapter,
    _extract_scorecard_results,
    _scorecard_api_url,
)
from max.types.signal import SignalSourceType


MOCK_SCORECARD = {
    "date": "2026-04-20T12:30:00Z",
    "repo": {"name": "github.com/example/tool", "commit": "abc123"},
    "score": 6.7,
    "checks": [
        {
            "name": "Token-Permissions",
            "score": 2,
            "reason": "Detected GitHub workflow tokens with write permissions.",
            "details": ["Warn: job has contents: write"],
            "documentation": {"url": "https://github.com/ossf/scorecard/blob/main/docs/checks.md"},
        },
        {
            "name": "Branch-Protection",
            "score": 8,
            "reason": "Branch protection is partially configured.",
            "details": ["Info: one branch has protection"],
        },
        {
            "name": "Maintained",
            "score": 10,
            "reason": "Repository has recent activity.",
        },
    ],
}


def test_openssf_scorecard_config_and_url_helpers(monkeypatch) -> None:
    monkeypatch.setenv("ALT_SCORECARD_TOKEN", "env-token")
    adapter = OpenSSFScorecardAdapter(
        config={
            "repositories": [" example/tool ", "example/tool"],
            "checks": ["Token-Permissions"],
            "min_risk_score": "7",
            "local_path": "/tmp/scorecard.json",
            "local_paths": ["/tmp/scorecard.json", "/tmp/other.json"],
            "token_env": "ALT_SCORECARD_TOKEN",
        }
    )

    assert adapter.name == "openssf_scorecard"
    assert adapter.source_type == SignalSourceType.SECURITY.value
    assert adapter.repositories == ["example/tool"]
    assert adapter.checks == ["Token-Permissions"]
    assert adapter.min_risk_score == 7
    assert adapter.local_paths == ["/tmp/scorecard.json", "/tmp/other.json"]
    assert adapter.token == "env-token"
    assert _scorecard_api_url("example/tool") == (
        "https://api.securityscorecards.dev/projects/github.com/example/tool"
    )


@pytest.mark.asyncio
async def test_local_fixture_parsing_normalizes_risky_checks(tmp_path) -> None:
    fixture = tmp_path / "scorecard.json"
    fixture.write_text(json.dumps(MOCK_SCORECARD), encoding="utf-8")
    adapter = OpenSSFScorecardAdapter(config={"local_path": str(fixture)})

    signals = await adapter.fetch(limit=10)

    assert [signal.metadata["check_name"] for signal in signals] == [
        "Token-Permissions",
        "Branch-Protection",
    ]
    signal = signals[0]
    assert signal.id == "openssf_scorecard:example/tool:token-permissions"
    assert signal.source_type == SignalSourceType.SECURITY
    assert signal.source_adapter == "openssf_scorecard"
    assert signal.title == "OpenSSF Scorecard risk: example/tool Token-Permissions scored 2"
    assert "GitHub workflow tokens with write permissions" in signal.content
    assert signal.url == "https://github.com/ossf/scorecard/blob/main/docs/checks.md"
    assert signal.published_at == datetime(2026, 4, 20, 12, 30, tzinfo=timezone.utc)
    assert signal.credibility > signals[1].credibility
    assert "high-risk" in signal.tags
    assert signal.metadata["repo"] == "example/tool"
    assert signal.metadata["date"] == "2026-04-20T12:30:00Z"
    assert signal.metadata["overall_score"] == 6.7
    assert signal.metadata["check_score"] == 2.0
    assert signal.metadata["risk_score"] == 8.0
    assert signal.metadata["reason"] == "Detected GitHub workflow tokens with write permissions."
    assert signal.metadata["details_url"] == signal.url
    assert signal.metadata["details"] == ["Warn: job has contents: write"]
    assert signal.metadata["signal_role"] == "problem"


def test_extract_scorecard_results_supports_nested_wrappers() -> None:
    other = {**MOCK_SCORECARD, "repo": {"name": "github.com/example/other"}}

    assert _extract_scorecard_results(MOCK_SCORECARD) == [MOCK_SCORECARD]
    assert _extract_scorecard_results({"data": {"results": [MOCK_SCORECARD, other]}}) == [
        MOCK_SCORECARD,
        other,
    ]
    assert _extract_scorecard_results({"items": [MOCK_SCORECARD, "invalid"]}) == [MOCK_SCORECARD]
    assert _extract_scorecard_results({"scorecards": {"items": [other, None]}}) == [other]


def test_extract_scorecard_results_ignores_malformed_wrappers() -> None:
    assert _extract_scorecard_results({"data": "not-a-wrapper"}) == []
    assert _extract_scorecard_results({"scorecards": {"items": "not-a-list"}}) == []
    assert _extract_scorecard_results({"data": {"results": 1}}) == []
    assert _extract_scorecard_results("not-json-object") == []


@pytest.mark.asyncio
async def test_api_fetch_normalization_and_token_header() -> None:
    adapter = OpenSSFScorecardAdapter(
        config={"repositories": ["example/tool"], "token": "configured-token"}
    )

    async def mock_fetch(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        return MagicMock(json=lambda: MOCK_SCORECARD)

    with patch("max.sources.openssf_scorecard.fetch_with_retry", mock_fetch), \
         patch("max.sources.openssf_scorecard.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value = MagicMock()
        signals = await adapter.fetch(limit=5)

    assert len(signals) == 2
    assert signals[0].metadata["repo"] == "example/tool"
    assert mock_client.call_args.kwargs["headers"]["Authorization"] == "Bearer configured-token"


@pytest.mark.asyncio
async def test_check_filtering(tmp_path) -> None:
    fixture = tmp_path / "scorecard.json"
    fixture.write_text(json.dumps(MOCK_SCORECARD), encoding="utf-8")
    adapter = OpenSSFScorecardAdapter(
        config={"local_path": str(fixture), "checks": ["Branch-Protection"]}
    )

    signals = await adapter.fetch(limit=10)

    assert [signal.metadata["check_name"] for signal in signals] == ["Branch-Protection"]


@pytest.mark.asyncio
async def test_score_thresholding_filters_by_min_risk_score(tmp_path) -> None:
    fixture = tmp_path / "scorecard.json"
    fixture.write_text(json.dumps(MOCK_SCORECARD), encoding="utf-8")
    adapter = OpenSSFScorecardAdapter(
        config={"local_path": str(fixture), "min_risk_score": 7}
    )

    signals = await adapter.fetch(limit=10)

    assert [signal.metadata["check_name"] for signal in signals] == ["Token-Permissions"]


@pytest.mark.asyncio
async def test_local_payload_collection_and_repository_filter(tmp_path) -> None:
    fixture = tmp_path / "scorecards.json"
    other = {**MOCK_SCORECARD, "repo": {"name": "github.com/example/other"}}
    fixture.write_text(json.dumps({"results": [other, MOCK_SCORECARD]}), encoding="utf-8")
    adapter = OpenSSFScorecardAdapter(
        config={"local_path": str(fixture), "repositories": ["example/tool"]}
    )

    signals = await adapter.fetch(limit=10)

    assert {signal.metadata["repo"] for signal in signals} == {"example/tool"}
