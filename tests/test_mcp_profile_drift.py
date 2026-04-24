"""Tests for profile drift analysis exposed through MCP."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from max.profiles.schema import DomainContext, EvaluationConfig, PipelineProfile, SourceConfig
from max.server import mcp_tools
from max.server.mcp_tools import get_profile_drift, profile_drift_detail, set_store_factory
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.insight import Insight
from max.types.signal import Signal


def _profile() -> PipelineProfile:
    return PipelineProfile(
        name="test-profile",
        domain=DomainContext(
            name="test-domain",
            description="Test domain",
            categories=["application", "integration"],
            target_user_types=["admins", "operators"],
        ),
        sources=[
            SourceConfig(adapter="reddit", weight=2.0),
            SourceConfig(adapter="github", weight=1.0),
        ],
        evaluation=EvaluationConfig(weight_profile="default"),
    )


def _evaluation(unit_id: str) -> UtilityEvaluation:
    score = DimensionScore(value=7.0, confidence=0.8, reasoning="ok")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=score,
        addressable_scale=score,
        build_effort=score,
        composability=score,
        competitive_density=score,
        timing_fit=score,
        compounding_value=score,
        overall_score=70.0,
        weights_used={"pain_severity": 1.0},
    )


@pytest.fixture
def mcp_profile_drift_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "mcp_profile_drift.db")
    Store(db_path=db_path, wal_mode=True).close()

    profile = _profile()

    def fake_load_profile(profile_name: str) -> PipelineProfile:
        if profile_name != profile.name:
            raise FileNotFoundError(profile_name)
        return profile

    monkeypatch.setattr("max.profiles.loader.load_profile", fake_load_profile)
    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


def _seed_profile_drift(store: Store) -> None:
    now = datetime.now(timezone.utc)
    recent = store.insert_signal(
        Signal(
            source_type="forum",
            source_adapter="reddit",
            title="Recent signal",
            content="content",
            url="https://example.com/recent",
            fetched_at=now - timedelta(days=2),
        )
    )
    old = store.insert_signal(
        Signal(
            source_type="forum",
            source_adapter="github",
            title="Old signal",
            content="content",
            url="https://example.com/old",
            fetched_at=now - timedelta(days=20),
        )
    )
    store.insert_insight(
        Insight(
            category="pain_point",
            title="Recent insight",
            summary="summary",
            evidence=[recent.id],
            domains=["test-domain"],
            created_at=now - timedelta(days=1),
        )
    )
    unit = store.insert_buildable_unit(
        BuildableUnit(
            title="MCP drift unit",
            one_liner="one liner",
            category="application",
            problem="problem",
            solution="solution",
            target_users="admins",
            value_proposition="value",
            evidence_signals=[recent.id, old.id],
            domain="test-domain",
            created_at=now - timedelta(days=1),
            updated_at=now - timedelta(days=1),
        )
    )
    store.insert_evaluation(_evaluation(unit.id))


def test_get_profile_drift_returns_seeded_report(mcp_profile_drift_db) -> None:
    with Store(db_path=mcp_profile_drift_db, wal_mode=True) as store:
        _seed_profile_drift(store)

    result = get_profile_drift("test-profile", lookback_days=30, min_signals=1)

    assert result["profile_name"] == "test-profile"
    assert result["domain"] == "test-domain"
    assert result["signals_analyzed"] == 2
    assert result["units_analyzed"] == 1
    assert result["evaluations_analyzed"] == 1
    assert result["source_mix_drift"]["counts"] == {"github": 1, "reddit": 1}


def test_get_profile_drift_validates_and_reflects_parameters(mcp_profile_drift_db) -> None:
    with Store(db_path=mcp_profile_drift_db, wal_mode=True) as store:
        _seed_profile_drift(store)

    result = get_profile_drift("test-profile", lookback_days=7, min_signals=2)

    assert result["lookback_days"] == 7
    assert result["min_signals"] == 2
    assert result["signals_analyzed"] == 1
    assert result["source_mix_drift"]["counts"] == {"reddit": 1}
    assert "Only 1 signal(s) were available; min_signals is 2." in result["warnings"]

    bad_lookback = get_profile_drift("test-profile", lookback_days=0)
    assert bad_lookback["error"] == "lookback_days must be at least 1"
    assert bad_lookback["code"] == 400
    assert bad_lookback["details"]["field"] == "lookback_days"

    bad_min_signals = get_profile_drift("test-profile", min_signals=-1)
    assert bad_min_signals["error"] == "min_signals must be non-negative"
    assert bad_min_signals["code"] == 400
    assert bad_min_signals["details"]["field"] == "min_signals"


def test_get_profile_drift_unknown_profile_returns_mcp_not_found(
    mcp_profile_drift_db,
) -> None:
    result = get_profile_drift("missing-profile")

    assert result == {
        "error": "Profile not found: missing-profile",
        "code": 404,
        "details": {
            "resource_type": "profile",
            "resource_id": "missing-profile",
        },
    }


def test_profile_drift_resource_returns_default_json(mcp_profile_drift_db) -> None:
    with Store(db_path=mcp_profile_drift_db, wal_mode=True) as store:
        _seed_profile_drift(store)

    payload = json.loads(profile_drift_detail("test-profile"))

    assert payload["profile_name"] == "test-profile"
    assert payload["lookback_days"] == 30
    assert payload["min_signals"] == 1
    assert payload["signals_analyzed"] == 2


def test_create_mcp_server_registers_profile_drift_tool_and_resource(monkeypatch) -> None:
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

    monkeypatch.setattr(mcp_tools, "FastMCP", FakeMCP)

    mcp_tools.create_mcp_server()

    assert "get_profile_drift" in FakeMCP.latest.tools
    assert FakeMCP.latest.resources["profile-drift://{profile_name}"] == "profile_drift_detail"
