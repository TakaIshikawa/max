"""Tests for source allocation simulation."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from max.analysis.source_simulation import simulate_source_allocation
from max.profiles.schema import DomainContext, PipelineProfile, SourceConfig
from max.sources.base import get_circuit_breaker


def _profile(*, signal_limit: int = 30) -> PipelineProfile:
    return PipelineProfile(
        name="devtools",
        domain=DomainContext(
            name="developer-tools",
            description="Developer tools",
            categories=["cli_tool"],
            target_user_types=["developers"],
        ),
        signal_limit=signal_limit,
        sources=[
            SourceConfig(
                adapter="hackernews",
                weight=2.0,
                watchlist=["mcp"],
                params={"filter_keywords": ["agents"]},
            ),
            SourceConfig(
                adapter="reddit",
                enabled=False,
                params={"subreddits": ["LocalLLaMA"]},
            ),
        ],
    )


def _store() -> MagicMock:
    store = MagicMock()
    store.get_adapter_quality_stats.return_value = {}
    store.get_adapter_approval_stats.return_value = {}
    return store


def test_simulation_uses_default_profile_budget() -> None:
    store = _store()
    report = simulate_source_allocation(_profile(signal_limit=25), store)

    assert report.profile == "devtools"
    assert report.total_budget == 25
    assert report.allocation == {"hackernews": 25}


def test_simulation_applies_budget_override() -> None:
    store = _store()
    report = simulate_source_allocation(_profile(signal_limit=25), store, budget=80)

    assert report.total_budget == 80
    assert report.allocation == {"hackernews": 80}
    assert report.sources[0].allocated_limit == 80


def test_simulation_includes_disabled_sources_without_allocation() -> None:
    store = _store()
    report = simulate_source_allocation(_profile(), store)
    by_adapter = {source.adapter: source for source in report.sources}

    assert by_adapter["reddit"].enabled is False
    assert by_adapter["reddit"].allocated_limit == 0
    assert "reddit" not in report.allocation


def test_simulation_includes_quality_approval_params_and_circuit_state() -> None:
    store = _store()
    store.get_adapter_quality_stats.return_value = {
        "hackernews": {
            "total_signals": 10,
            "insight_hit_rate": 0.4,
            "idea_hit_rate": 0.2,
        }
    }
    store.get_adapter_approval_stats.return_value = {
        "hackernews": {
            "total_feedbacked": 3,
            "approved": 2,
            "rejected": 1,
            "approval_rate": 2 / 3,
        }
    }
    cb = get_circuit_breaker("hackernews")
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()

    report = simulate_source_allocation(_profile(), store)
    source = report.sources[0]

    assert source.params["filter_keywords"] == ["agents", "mcp"]
    assert source.params["watchlist_terms"] == ["mcp"]
    assert source.total_signals == 10
    assert source.insight_hit_rate == 0.4
    assert source.idea_hit_rate == 0.2
    assert source.total_feedbacked == 3
    assert source.approved == 2
    assert source.rejected == 1
    assert source.approval_rate == pytest.approx(2 / 3)
    assert source.circuit_state == "open"
    assert source.circuit_failures == 3


def test_simulation_rejects_invalid_budget() -> None:
    with pytest.raises(ValueError, match="budget must be at least 1"):
        simulate_source_allocation(_profile(), _store(), budget=0)
