"""Tests for profile source recommendation analysis."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from max.analysis.profile_source_recommendations import (
    build_profile_source_recommendations_for_profile,
)
from max.profiles.schema import DomainContext, PipelineProfile, SourceConfig


NOW = datetime(2026, 1, 31, tzinfo=timezone.utc)


def _profile(*sources: SourceConfig) -> PipelineProfile:
    return PipelineProfile(
        name="testing",
        domain=DomainContext(
            name="testing",
            description="Testing domain",
            categories=["application"],
            target_user_types=["developers"],
        ),
        sources=list(sources),
    )


def _store(
    *,
    quality: dict | None = None,
    approval: dict | None = None,
    freshness: list[dict] | None = None,
) -> MagicMock:
    store = MagicMock()
    store.get_adapter_quality_stats.return_value = quality or {}
    store.get_adapter_approval_stats.return_value = approval or {}
    store.get_signal_freshness_records.return_value = freshness or []
    return store


def _freshness(adapter: str, fetched_at: str, signal_id: str = "sig") -> dict:
    return {
        "id": signal_id,
        "source_type": "forum",
        "source_adapter": adapter,
        "published_at": None,
        "fetched_at": fetched_at,
        "tags": [],
        "signal_role": "",
    }


def _by_adapter(report) -> dict:
    return {rec.adapter: rec for rec in report.recommendations}


@patch("max.analysis.profile_source_recommendations.list_adapters")
def test_healthy_adapter_keeps_configuration(mock_list_adapters) -> None:
    mock_list_adapters.return_value = ["hackernews"]
    profile = _profile(SourceConfig(adapter="hackernews", enabled=True, weight=1.0))

    report = build_profile_source_recommendations_for_profile(
        profile,
        _store(
            quality={
                "hackernews": {
                    "total_signals": 4,
                    "insight_hit_rate": 0.1,
                    "idea_hit_rate": 0.05,
                }
            },
            freshness=[
                _freshness("hackernews", "2026-01-30T00:00:00+00:00", "sig-1"),
                _freshness("hackernews", "2026-01-29T00:00:00+00:00", "sig-2"),
            ],
        ),
        now=NOW,
    )

    rec = _by_adapter(report)["hackernews"]
    assert rec.action == "keep"
    assert rec.severity == "low"
    assert rec.current_weight == 1.0
    assert rec.suggested_weight == 1.0


@patch("max.analysis.profile_source_recommendations.list_adapters")
def test_stale_adapter_recommends_investigation(mock_list_adapters) -> None:
    mock_list_adapters.return_value = ["reddit"]
    profile = _profile(SourceConfig(adapter="reddit", enabled=True, weight=1.0))

    report = build_profile_source_recommendations_for_profile(
        profile,
        _store(
            quality={"reddit": {"total_signals": 2, "insight_hit_rate": 0.2, "idea_hit_rate": 0.1}},
            freshness=[
                _freshness("reddit", "2025-10-01T00:00:00+00:00", "sig-old-1"),
                _freshness("reddit", "2025-10-02T00:00:00+00:00", "sig-old-2"),
            ],
        ),
        now=NOW,
    )

    rec = _by_adapter(report)["reddit"]
    assert rec.action == "investigate"
    assert rec.severity == "medium"
    assert rec.evidence["freshness"]["stale_count"] == 2
    assert "stale" in rec.reasons[0]


@patch("max.analysis.profile_source_recommendations.list_adapters")
def test_low_approval_adapter_decreases_weight(mock_list_adapters) -> None:
    mock_list_adapters.return_value = ["github"]
    profile = _profile(SourceConfig(adapter="github", enabled=True, weight=2.0))

    report = build_profile_source_recommendations_for_profile(
        profile,
        _store(
            quality={"github": {"total_signals": 10, "insight_hit_rate": 0.1, "idea_hit_rate": 0.05}},
            approval={
                "github": {
                    "total_feedbacked": 5,
                    "approved": 1,
                    "rejected": 4,
                    "approval_rate": 0.2,
                }
            },
        ),
        now=NOW,
    )

    rec = _by_adapter(report)["github"]
    assert rec.action == "decrease_weight"
    assert rec.severity == "medium"
    assert rec.suggested_weight == 1.0
    assert rec.evidence["approval"]["approval_rate"] == 0.2


@patch("max.analysis.profile_source_recommendations.list_adapters")
def test_missing_registered_adapter_recommends_investigation(mock_list_adapters) -> None:
    mock_list_adapters.return_value = ["hackernews"]
    profile = _profile(SourceConfig(adapter="missing_adapter", enabled=True, weight=1.0))

    report = build_profile_source_recommendations_for_profile(
        profile,
        _store(),
        now=NOW,
    )

    rec = _by_adapter(report)["missing_adapter"]
    assert rec.action == "investigate"
    assert rec.severity == "high"
    assert rec.registered is False
    assert "not registered" in rec.reasons[0]


@patch("max.analysis.profile_source_recommendations.list_adapters")
def test_disabled_high_performing_adapter_recommends_enable(mock_list_adapters) -> None:
    mock_list_adapters.return_value = ["stackoverflow"]
    profile = _profile(SourceConfig(adapter="stackoverflow", enabled=False, weight=0.25))

    report = build_profile_source_recommendations_for_profile(
        profile,
        _store(
            quality={
                "stackoverflow": {
                    "total_signals": 12,
                    "insight_hit_rate": 0.35,
                    "idea_hit_rate": 0.25,
                }
            },
            approval={
                "stackoverflow": {
                    "total_feedbacked": 4,
                    "approved": 3,
                    "rejected": 1,
                    "approval_rate": 0.75,
                }
            },
        ),
        now=NOW,
    )

    rec = _by_adapter(report)["stackoverflow"]
    assert rec.action == "enable"
    assert rec.severity == "medium"
    assert rec.enabled is False
    assert rec.suggested_weight == 1.0
