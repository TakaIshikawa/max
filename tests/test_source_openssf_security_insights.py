"""Tests for the OpenSSF Security Insights source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.sources.openssf_security_insights import (
    OpenSSFSecurityInsightsAdapter,
    _candidate_github_urls,
)
from max.sources.registry import get_adapter, get_adapter_metadata, reload_registry
from max.types.signal import SignalSourceType


SECURITY_INSIGHTS_YAML = """
header:
  schema-version: "1.0.0"
  expiration-date: "2026-12-31T00:00:00Z"
  project-url: https://github.com/example/tool
project-lifecycle:
  stage: active
  bug-fixes-only: false
  core-maintainers:
    - github:example
contribution-policy:
  accepts-pull-requests: true
security-contacts:
  - type: email
    value: security@example.com
vulnerability-reporting:
  accepts-vulnerability-reports: true
  security-policy: https://github.com/example/tool/security/policy
dependencies:
  third-party-packages: true
fuzzing:
  fuzzing-coverage: critical-paths
audits:
  - date: "2026-01-20"
    auditor: Example Security
release-integrity:
  artifacts-signed: true
self-assessment:
  comment: Maintainers review OSPS baseline controls quarterly.
"""


@pytest.mark.asyncio
async def test_local_yaml_parsing_normalizes_security_posture(tmp_path) -> None:
    path = tmp_path / "SECURITY-INSIGHTS.yml"
    path.write_text(SECURITY_INSIGHTS_YAML, encoding="utf-8")
    adapter = OpenSSFSecurityInsightsAdapter(config={"local_paths": [str(path)]})

    signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "openssf_security_insights:example/tool"
    assert signal.source_type == SignalSourceType.SECURITY
    assert signal.source_adapter == "openssf_security_insights"
    assert signal.url == str(path)
    assert "security posture fields" in signal.content
    assert "security" in signal.tags
    assert "supply-chain" in signal.tags
    assert "release-integrity" in signal.tags
    assert signal.metadata["repo"] == "example/tool"
    assert signal.metadata["schema_version"] == "1.0.0"
    assert signal.metadata["expiration_date"] == "2026-12-31T00:00:00Z"
    assert signal.metadata["security_contacts"] == [
        {"type": "email", "value": "security@example.com"}
    ]
    assert signal.metadata["vulnerability_reporting"]["accepts-vulnerability-reports"] is True
    assert signal.metadata["dependencies"]["third-party-packages"] is True
    assert signal.metadata["fuzzing"]["fuzzing-coverage"] == "critical-paths"
    assert signal.metadata["audits"][0]["auditor"] == "Example Security"
    assert signal.metadata["release_integrity"]["artifacts-signed"] is True
    assert signal.metadata["self_assessment"]["comment"].startswith("Maintainers review")
    assert signal.metadata["security_insights"]["header"]["project-url"].endswith("/tool")
    assert signal.metadata["posture_score"] == 1.0
    assert signal.metadata["missing_required_fields"] == []


@pytest.mark.asyncio
async def test_direct_url_fetch_with_mocked_http() -> None:
    adapter = OpenSSFSecurityInsightsAdapter(
        config={"insight_urls": ["https://example.test/security-insights.yml"], "token": "tok"}
    )

    async def mock_fetch(url: str, client: httpx.AsyncClient, **kwargs) -> MagicMock:
        return MagicMock(text=SECURITY_INSIGHTS_YAML)

    with patch("max.sources.openssf_security_insights.fetch_with_retry", mock_fetch), \
         patch("max.sources.openssf_security_insights.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value = MagicMock()
        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    assert signals[0].metadata["source_url"] == "https://example.test/security-insights.yml"
    assert mock_client.call_args.kwargs["headers"]["Authorization"] == "Bearer tok"


@pytest.mark.asyncio
async def test_repository_fetch_probes_security_insights_paths() -> None:
    adapter = OpenSSFSecurityInsightsAdapter(config={"repositories": ["example/tool"]})
    requested: list[str] = []

    async def mock_request(method: str, url: str, **kwargs) -> MagicMock:
        requested.append(url)
        status_code = 200 if url.endswith("/main/SECURITY-INSIGHTS.yaml") else 404
        return MagicMock(status_code=status_code, text=SECURITY_INSIGHTS_YAML)

    with patch("max.sources.openssf_security_insights.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.request = mock_request
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    assert signals[0].metadata["repo"] == "example/tool"
    assert signals[0].url.endswith("/main/SECURITY-INSIGHTS.yaml")
    assert requested[:2] == _candidate_github_urls("example/tool")[:2]


@pytest.mark.asyncio
async def test_invalid_yaml_and_missing_required_fields_do_not_crash(tmp_path) -> None:
    broken = tmp_path / "broken.yml"
    broken.write_text("header: [", encoding="utf-8")
    missing = tmp_path / "missing.yml"
    missing.write_text(
        """
header:
  schema-version: "1.0.0"
  project-url: https://github.com/example/missing
security-contacts:
  - security@example.com
""",
        encoding="utf-8",
    )
    valid = tmp_path / "valid.yml"
    valid.write_text(SECURITY_INSIGHTS_YAML, encoding="utf-8")
    adapter = OpenSSFSecurityInsightsAdapter(
        config={"local_paths": [str(broken), str(missing), str(valid)]}
    )

    signals = await adapter.fetch(limit=5)

    assert [signal.metadata["repo"] for signal in signals] == ["example/tool"]


@pytest.mark.asyncio
async def test_required_fields_min_score_max_items_and_deduplication(tmp_path) -> None:
    first = tmp_path / "one.yml"
    duplicate = tmp_path / "two.yml"
    lean = tmp_path / "lean.yml"
    first.write_text(SECURITY_INSIGHTS_YAML, encoding="utf-8")
    duplicate.write_text(SECURITY_INSIGHTS_YAML, encoding="utf-8")
    lean.write_text(
        """
header:
  schema-version: "1.0.0"
  project-url: https://github.com/example/lean
project-lifecycle:
  stage: active
security-contacts:
  - security@example.com
vulnerability-reporting:
  accepts-vulnerability-reports: false
""",
        encoding="utf-8",
    )
    adapter = OpenSSFSecurityInsightsAdapter(
        config={
            "local_paths": [str(first), str(duplicate), str(lean)],
            "required_fields": ["header.project-url", "security-contacts"],
            "min_score": 50,
            "max_items": 5,
        }
    )

    signals = await adapter.fetch(limit=10)

    assert [signal.id for signal in signals] == ["openssf_security_insights:example/tool"]


def test_config_helpers_and_registry_metadata(monkeypatch) -> None:
    monkeypatch.setenv("ALT_SECURITY_INSIGHTS_TOKEN", "env-token")
    adapter = OpenSSFSecurityInsightsAdapter(
        config={
            "repositories": [" example/tool ", "example/tool"],
            "insight_urls": [" https://example.test/si.yml "],
            "local_paths": ["/tmp/security-insights.yml"],
            "token_env": "ALT_SECURITY_INSIGHTS_TOKEN",
            "min_score": "80",
            "max_items": "2",
        }
    )

    assert adapter.name == "openssf_security_insights"
    assert adapter.source_type == SignalSourceType.SECURITY.value
    assert adapter.repositories == ["example/tool"]
    assert adapter.insight_urls == ["https://example.test/si.yml"]
    assert adapter.local_paths == ["/tmp/security-insights.yml"]
    assert adapter.token == "env-token"
    assert adapter.min_score == 0.8
    assert adapter.max_items == 2

    reload_registry()
    registry_adapter = get_adapter("openssf_security_insights")
    metadata = get_adapter_metadata()["openssf_security_insights"]

    assert registry_adapter.name == "openssf_security_insights"
    assert metadata.config_keys == OpenSSFSecurityInsightsAdapter.config_keys
    assert metadata.required_keys == []
    assert "Security Insights YAML" in metadata.description
