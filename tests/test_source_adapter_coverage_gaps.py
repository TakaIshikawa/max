"""Tests for source adapter coverage gap reporting."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from max.analysis.source_adapter_coverage_gaps import (
    SCHEMA_VERSION,
    build_source_adapter_coverage_gap_report,
    build_source_adapter_coverage_gap_report_for_profile,
    build_source_adapter_coverage_gaps_report,
)
from max.profiles.schema import DomainContext, PipelineProfile, SourceConfig
from max.sources.registry import AdapterMetadata
from max.store.db import Store
from max.types.signal import Signal, SignalSourceType


GENERATED_AT = "2026-04-30T00:00:00+00:00"


def test_source_adapter_coverage_gaps_flags_all_gap_types(store: Store) -> None:
    profile = _profile(
        sources=[
            SourceConfig(adapter="hackernews", weight=1.5, params={"max_items": 10}),
            SourceConfig(adapter="reddit", weight=1.0),
            SourceConfig(adapter="npm_registry", weight=0.5),
            SourceConfig(adapter="cisa_kev", enabled=False),
        ]
    )
    store.insert_signal(
        _signal(
            "sig-hn-new",
            "hackernews",
            SignalSourceType.FORUM,
            fetched_at=datetime(2026, 4, 29, tzinfo=timezone.utc),
        )
    )
    store.insert_signal(
        _signal(
            "sig-npm-old",
            "npm_registry",
            SignalSourceType.REGISTRY,
            fetched_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        )
    )
    store.insert_signal(
        _signal(
            "sig-bluesky-new",
            "bluesky",
            SignalSourceType.FORUM,
            fetched_at=datetime(2026, 4, 28, tzinfo=timezone.utc),
        )
    )
    store.insert_pipeline_run("run-1", {})
    store.update_pipeline_run(
        "run-1",
        adapter_metrics={
            "reddit": {"status": "error", "error_message": "rate limited"},
            "hackernews": {"status": "ok"},
        },
    )

    with (
        patch(
            "max.analysis.source_adapter_coverage_gaps.get_adapter_metadata",
            return_value=_metadata(),
        ),
        patch(
            "max.analysis.source_adapter_coverage_gaps.get_adapter",
            side_effect=_adapter,
        ),
        patch(
            "max.analysis.source_adapter_coverage_gaps.snapshot_circuit_breakers",
            return_value=[
                SimpleNamespace(
                    adapter_name="hackernews",
                    state="closed",
                    failure_count=0,
                    last_failure_at=None,
                    retry_after=0.0,
                ),
                SimpleNamespace(
                    adapter_name="reddit",
                    state="open",
                    failure_count=3,
                    last_failure_at=10.0,
                    retry_after=120.0,
                ),
                SimpleNamespace(
                    adapter_name="npm_registry",
                    state="closed",
                    failure_count=0,
                    last_failure_at=None,
                    retry_after=0.0,
                ),
                SimpleNamespace(
                    adapter_name="bluesky",
                    state="closed",
                    failure_count=0,
                    last_failure_at=None,
                    retry_after=0.0,
                ),
            ],
        ),
    ):
        report = build_source_adapter_coverage_gap_report_for_profile(
            store,
            profile,
            lookback_days=14,
            min_expected_sources=4,
            stale_days=30,
            generated_at=GENERATED_AT,
        )

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == "max.source_adapter_coverage_gaps"
    assert report["generated_at"] == GENERATED_AT
    assert report["profile_name"] == "coverage"
    assert report["lookback_window"]["days"] == 14
    assert report["filters"] == {
        "profile_name": "coverage",
        "lookback_days": 14,
        "min_expected_sources": 4,
        "stale_days": 30,
    }
    assert report["summary"]["configured_adapter_count"] == 3
    assert report["summary"]["disabled_adapter_count"] == 1
    assert report["summary"]["active_adapter_count"] == 2
    assert report["summary"]["recent_signal_count"] == 2
    assert report["summary"]["configured_silent_count"] == 2
    assert report["summary"]["active_unconfigured_count"] == 1
    assert report["summary"]["stale_count"] == 1
    assert report["summary"]["failing_count"] == 1
    assert report["summary"]["below_min_expected_sources"] is True

    rows = {row["adapter"]: row for row in report["adapter_rows"]}
    assert rows["hackernews"]["recent_signal_count"] == 1
    assert rows["hackernews"]["metadata"]["config_keys"] == ["filter_keywords"]
    assert rows["reddit"]["flags"] == ["configured_silent", "failing"]
    assert rows["reddit"]["latest_fetch_status"] == "error"
    assert rows["reddit"]["circuit_breaker"]["state"] == "open"
    assert rows["npm_registry"]["flags"] == ["configured_silent", "stale"]
    assert rows["npm_registry"]["newest_signal_at"] == "2026-03-01T00:00:00+00:00"
    assert rows["bluesky"]["flags"] == ["active_unconfigured"]
    assert rows["bluesky"]["configured"] is False
    assert rows["bluesky"]["present_in_profile"] is False

    assert report["coverage_flags"]["configured_silent"][0]["adapter"] == "npm_registry"
    assert {item["adapter"] for item in report["coverage_flags"]["active_unconfigured"]} == {
        "bluesky"
    }
    assert any(
        item["type"] == "increase_profile_source_coverage" for item in report["recommendations"]
    )
    assert any(item["type"] == "active_unconfigured" for item in report["recommendations"])
    assert json.loads(json.dumps(report))["summary"]["adapter_row_count"] == 4


def test_source_adapter_coverage_gap_report_loads_named_profile(store: Store) -> None:
    profile = _profile(sources=[SourceConfig(adapter="hackernews")])

    with (
        patch(
            "max.analysis.source_adapter_coverage_gaps.profile_loader.load_profile",
            return_value=profile,
        ) as load,
        patch(
            "max.analysis.source_adapter_coverage_gaps.get_adapter_metadata",
            return_value=_metadata(),
        ),
        patch(
            "max.analysis.source_adapter_coverage_gaps.get_adapter",
            side_effect=_adapter,
        ),
    ):
        report = build_source_adapter_coverage_gap_report(
            store,
            "coverage",
            generated_at=GENERATED_AT,
        )
        alias_report = build_source_adapter_coverage_gaps_report(
            store,
            "coverage",
            generated_at=GENERATED_AT,
        )

    assert load.call_count == 2
    load.assert_called_with("coverage")
    assert report["profile_name"] == "coverage"
    assert alias_report["profile_name"] == "coverage"


def test_source_adapter_coverage_gap_report_rejects_invalid_filters(store: Store) -> None:
    profile = _profile(sources=[SourceConfig(adapter="hackernews")])

    with pytest.raises(ValueError, match="lookback_days"):
        build_source_adapter_coverage_gap_report_for_profile(store, profile, lookback_days=0)
    with pytest.raises(ValueError, match="min_expected_sources"):
        build_source_adapter_coverage_gap_report_for_profile(
            store,
            profile,
            min_expected_sources=0,
        )
    with pytest.raises(ValueError, match="stale_days"):
        build_source_adapter_coverage_gap_report_for_profile(store, profile, stale_days=0)


def _profile(*, sources: list[SourceConfig]) -> PipelineProfile:
    return PipelineProfile(
        name="coverage",
        domain=DomainContext(
            name="developer-tools",
            description="Developer tools",
            categories=["application"],
            target_user_types=["developers"],
        ),
        sources=sources,
    )


def _metadata() -> dict[str, AdapterMetadata]:
    return {
        "hackernews": AdapterMetadata(
            name="hackernews",
            config_keys=["filter_keywords"],
            required_keys=[],
            description="Fetches Hacker News stories.",
        ),
        "reddit": AdapterMetadata(
            name="reddit",
            config_keys=["subreddits"],
            required_keys=[],
            description="Fetches subreddit posts.",
        ),
        "npm_registry": AdapterMetadata(
            name="npm_registry",
            config_keys=["queries"],
            required_keys=[],
            description="Searches the npm registry.",
        ),
        "bluesky": AdapterMetadata(
            name="bluesky",
            config_keys=["queries"],
            required_keys=[],
            description="Fetches social posts.",
        ),
    }


def _adapter(name: str) -> SimpleNamespace:
    source_types = {
        "hackernews": "forum",
        "reddit": "forum",
        "npm_registry": "registry",
        "bluesky": "forum",
    }
    return SimpleNamespace(source_type=source_types[name])


def _signal(
    signal_id: str,
    adapter: str,
    source_type: SignalSourceType,
    *,
    fetched_at: datetime,
) -> Signal:
    return Signal(
        id=signal_id,
        source_type=source_type,
        source_adapter=adapter,
        title=f"{adapter} signal",
        content="A source signal for coverage gap analysis.",
        url=f"https://example.test/{signal_id}",
        credibility=0.8,
        fetched_at=fetched_at,
    )
