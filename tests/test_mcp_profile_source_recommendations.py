"""Tests for profile source recommendations exposed through MCP."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from max.profiles.schema import DomainContext, PipelineProfile, SourceConfig
from max.server.mcp_tools import (
    create_mcp_server,
    get_profile_source_recommendations,
    profile_source_recommendations_detail,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def mcp_profile_db(tmp_path):
    db_path = str(tmp_path / "mcp_profile_recommendations.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


def _profile(name: str = "devtools") -> PipelineProfile:
    return PipelineProfile(
        name=name,
        domain=DomainContext(
            name="developer-tools",
            description="Developer tools",
            categories=["cli_tool"],
            target_user_types=["developers"],
        ),
        sources=[SourceConfig(adapter="test", enabled=True, weight=2.0)],
    )


def _score(value: float = 7.0) -> DimensionScore:
    return DimensionScore(value=value, confidence=0.7, reasoning="test")


def _evaluation(unit_id: str) -> UtilityEvaluation:
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=_score(8.0),
        addressable_scale=_score(7.0),
        build_effort=_score(6.0),
        composability=_score(7.0),
        competitive_density=_score(8.0),
        timing_fit=_score(7.0),
        compounding_value=_score(6.5),
        overall_score=72.0,
        strengths=["test"],
        weaknesses=["test"],
        recommendation="yes",
        weights_used={"pain_severity": 0.2},
    )


def _seed_source_recommendation_data(db_path: str) -> None:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        for index, outcome in enumerate(["approved", "rejected", "rejected", "rejected"]):
            signal_id = f"sig-test-{index}"
            unit_id = f"bu-test-{index}"
            store.insert_signal(
                Signal(
                    id=signal_id,
                    source_type=SignalSourceType.FORUM,
                    source_adapter="test",
                    title=f"Signal {index}",
                    content="Developers report a repeated workflow problem.",
                    url=f"https://example.com/signals/{index}",
                    fetched_at=datetime.now(timezone.utc),
                    credibility=0.7,
                )
            )
            store.insert_buildable_unit(
                BuildableUnit(
                    id=unit_id,
                    title=f"Idea {index}",
                    one_liner="Improve developer workflow",
                    category=BuildableCategory.CLI_TOOL,
                    ideation_mode=IdeationMode.DIRECT,
                    problem="Developers lose time switching tools.",
                    solution="Automate the repeated workflow.",
                    value_proposition="Reduce manual work.",
                    target_users="developers",
                    evidence_signals=[signal_id],
                )
            )
            store.insert_evaluation(_evaluation(unit_id))
            store.insert_feedback(unit_id, outcome)
    finally:
        store.close()


def test_get_profile_source_recommendations_returns_serializable_data(
    mcp_profile_db,
    monkeypatch,
) -> None:
    _seed_source_recommendation_data(mcp_profile_db)
    monkeypatch.setattr("max.profiles.loader.load_profile", lambda name: _profile(name))
    monkeypatch.setattr("max.analysis.profile_source_recommendations.list_adapters", lambda: ["test"])

    result = get_profile_source_recommendations("devtools", max_age_days=30)

    assert result["profile_name"] == "devtools"
    assert result["domain"] == "developer-tools"
    assert result["max_age_days"] == 30
    json.dumps(result)

    recommendation = result["recommendations"][0]
    assert recommendation["adapter"] == "test"
    assert recommendation["action"] == "decrease_weight"
    assert recommendation["severity"] == "medium"
    assert recommendation["reasons"]
    assert recommendation["reason"] == recommendation["reasons"][0]
    assert recommendation["evidence_counts"] == {
        "total_signals": 4,
        "total_feedbacked": 4,
        "approved": 1,
        "rejected": 3,
        "freshness_total": 4,
        "stale": 0,
    }
    assert recommendation["current_weight"] == 2.0
    assert recommendation["target_weight"] == 1.0
    assert recommendation["suggested_weight"] == 1.0


def test_get_profile_source_recommendations_unknown_profile_returns_mcp_error(
    mcp_profile_db,
    monkeypatch,
) -> None:
    def _missing_profile(name: str):
        raise FileNotFoundError(f"No profile named {name}")

    monkeypatch.setattr("max.profiles.loader.load_profile", _missing_profile)

    result = get_profile_source_recommendations("missing-profile")

    assert result["error"] == "Profile not found: missing-profile"
    assert result["code"] == 404
    assert result["details"] == {
        "resource_type": "profile",
        "resource_id": "missing-profile",
    }


def test_get_profile_source_recommendations_rejects_unsupported_format(
    mcp_profile_db,
) -> None:
    result = get_profile_source_recommendations("devtools", format="text")

    assert result["error"] == "format must be json"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"
    assert result["details"]["expected"] == "json"


def test_profile_source_recommendations_resource_returns_json_content(
    mcp_profile_db,
    monkeypatch,
) -> None:
    _seed_source_recommendation_data(mcp_profile_db)
    monkeypatch.setattr("max.profiles.loader.load_profile", lambda name: _profile(name))
    monkeypatch.setattr("max.analysis.profile_source_recommendations.list_adapters", lambda: ["test"])

    payload = json.loads(profile_source_recommendations_detail("devtools"))

    assert payload["profile_name"] == "devtools"
    assert payload["recommendations"][0]["adapter"] == "test"
    assert payload["recommendations"][0]["target_weight"] == 1.0


def test_create_mcp_server_registers_profile_source_recommendations(monkeypatch) -> None:
    class FakeMCP:
        latest = None

        def __init__(self, name):
            self.name = name
            self.tools = []
            self.resources = {}
            FakeMCP.latest = self

        def tool(self, fn):
            self.tools.append(fn.__name__)
            return fn

        def resource(self, uri):
            def decorator(fn):
                self.resources[uri] = fn.__name__
                return fn

            return decorator

    monkeypatch.setattr("max.server.mcp_tools.FastMCP", FakeMCP)

    create_mcp_server()

    assert "get_profile_source_recommendations" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["profile-source-recommendations://{profile_name}"]
        == "profile_source_recommendations_detail"
    )
