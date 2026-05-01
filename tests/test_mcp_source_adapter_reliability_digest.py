"""Tests for source adapter reliability digest exposed through MCP."""

from __future__ import annotations

import pytest

from max.analysis.source_adapter_reliability_digest import KIND, SCHEMA_VERSION
from max.profiles.schema import DomainContext, PipelineProfile, SourceConfig
from max.server.mcp_tools import (
    create_mcp_server,
    max_source_adapter_reliability_digest,
    set_store_factory,
)
from max.store.db import Store
from tests.test_source_adapter_reliability_digest import (
    _seed_runs,
    _seed_signals_and_utilization,
)


@pytest.fixture
def mcp_source_adapter_reliability_db(tmp_path):
    db_path = str(tmp_path / "mcp_source_adapter_reliability.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_reliability_db(mcp_source_adapter_reliability_db) -> str:
    store = Store(db_path=mcp_source_adapter_reliability_db, wal_mode=True)
    try:
        _seed_runs(store)
        _seed_signals_and_utilization(store)
    finally:
        store.close()
    return mcp_source_adapter_reliability_db


def _profile(name: str = "agent-sources") -> PipelineProfile:
    return PipelineProfile(
        name=name,
        domain=DomainContext(
            name="agent-source-selection",
            description="Source selection for autonomous agents",
            categories=["cli_tool"],
            target_user_types=["operators"],
        ),
        sources=[
            SourceConfig(adapter="healthy_adapter", enabled=True, weight=2.0),
            SourceConfig(adapter="broken_adapter", enabled=False, weight=1.0),
            SourceConfig(adapter="missing_adapter", enabled=True, weight=1.0),
        ],
    )


def test_max_source_adapter_reliability_digest_default_response(
    seeded_reliability_db,
) -> None:
    result = max_source_adapter_reliability_digest(limit=10)

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["kind"] == KIND
    assert result["filters"] == {
        "limit": 10,
        "min_runs": 1,
        "profile": None,
        "domain": None,
        "source_adapters": None,
    }
    assert result["summary"]["run_count"] == 3
    assert result["summary"]["adapter_count"] == 3
    assert result["reliability_bands"]["failing"] == ["broken_adapter"]
    assert result["reliability_bands"]["healthy"] == ["healthy_adapter"]
    assert [row["adapter"] for row in result["adapters"]] == [
        "broken_adapter",
        "low_yield_adapter",
        "healthy_adapter",
    ]
    assert result["next_actions"]


def test_max_source_adapter_reliability_digest_filters_by_adapter_and_profile(
    seeded_reliability_db,
    monkeypatch,
) -> None:
    monkeypatch.setattr("max.profiles.loader.load_profile", lambda name: _profile(name))

    result = max_source_adapter_reliability_digest(
        source_adapter=["healthy_adapter", "broken_adapter"],
        profile="agent-sources",
        limit=10,
    )

    assert result["filters"] == {
        "limit": 10,
        "min_runs": 1,
        "profile": "agent-sources",
        "domain": "agent-source-selection",
        "source_adapters": ["healthy_adapter"],
    }
    assert result["summary"]["adapter_count"] == 1
    assert result["summary"]["healthy_count"] == 1
    assert result["summary"]["failing_count"] == 0
    assert result["reliability_bands"] == {
        "failing": [],
        "low_yield": [],
        "watch": [],
        "healthy": ["healthy_adapter"],
    }
    assert [row["adapter"] for row in result["adapters"]] == ["healthy_adapter"]
    assert result["next_actions"] == [
        "Keep current adapter allocation and revisit after the next pipeline run."
    ]


def test_max_source_adapter_reliability_digest_invalid_filter_returns_mcp_error(
    seeded_reliability_db,
) -> None:
    result = max_source_adapter_reliability_digest(source_adapter=" ")

    assert result["error"] == "source_adapter must contain non-empty strings"
    assert result["code"] == 400
    assert result["details"]["field"] == "source_adapter"


def test_max_source_adapter_reliability_digest_missing_profile_returns_mcp_error(
    seeded_reliability_db,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "max.profiles.loader.load_profile",
        lambda name: (_ for _ in ()).throw(FileNotFoundError(name)),
    )

    result = max_source_adapter_reliability_digest(profile="missing")

    assert result["error"] == "Profile not found: missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "profile"
    assert result["details"]["resource_id"] == "missing"


def test_create_mcp_server_registers_source_adapter_reliability_digest_tool(
    monkeypatch,
) -> None:
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

    assert "max_source_adapter_reliability_digest" in FakeMCP.latest.tools
