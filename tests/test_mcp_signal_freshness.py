"""Tests for MCP signal freshness exposure."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from max.server import mcp_tools
from max.server.mcp_tools import (
    get_signal_freshness_report,
    set_store_factory,
    signal_freshness_report_detail,
)
from max.store.db import Store
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def mcp_db(tmp_path):
    """Create temp DB and configure mcp_tools to use it."""
    db_path = str(tmp_path / "test_mcp_signal_freshness.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


def _signal(
    idx: int,
    *,
    adapter: str,
    source_type: SignalSourceType = SignalSourceType.FORUM,
    age_days: int,
    tags: list[str] | None = None,
    role: str = "",
) -> Signal:
    timestamp = datetime.now(timezone.utc) - timedelta(days=age_days)
    metadata = {"signal_role": role} if role else {}
    return Signal(
        id=f"sig-mcp-fresh-{idx:03d}",
        source_type=source_type,
        source_adapter=adapter,
        title=f"Freshness MCP Signal {idx}",
        content="Signal freshness MCP fixture",
        url=f"https://example.com/mcp-freshness/{idx}",
        published_at=timestamp,
        fetched_at=timestamp,
        tags=tags or [],
        metadata=metadata,
    )


def _seed_signals(db_path: str) -> None:
    with Store(db_path=db_path, wal_mode=True) as store:
        store.insert_signal(
            _signal(
                1,
                adapter="hackernews",
                age_days=2,
                tags=["devtools"],
                role="market",
            )
        )
        store.insert_signal(
            _signal(
                2,
                adapter="hackernews",
                age_days=45,
                tags=["devtools", "ai"],
                role="market",
            )
        )
        store.insert_signal(
            _signal(
                3,
                adapter="npm_registry",
                source_type=SignalSourceType.REGISTRY,
                age_days=90,
                tags=["devtools"],
                role="solution",
            )
        )


def test_get_signal_freshness_report_returns_groups_recommendations_and_booleans(
    mcp_db,
) -> None:
    _seed_signals(mcp_db)

    report = get_signal_freshness_report(max_age_days=30)

    assert report["max_age_days"] == 30
    assert report["total_signals"] == 3
    assert report["stale_signals"] == 2
    assert report["has_stale_signals"] is True
    assert report["has_refresh_recommendations"] is True
    assert report["filters"] == {"source_adapters": [], "max_age_days": 30}

    by_adapter = {item["key"]: item for item in report["by_source_adapter"]}
    assert by_adapter["hackernews"]["total_count"] == 2
    assert by_adapter["hackernews"]["stale_count"] == 1
    assert by_adapter["npm_registry"]["stale_count"] == 1

    by_source_type = {item["key"]: item for item in report["by_source_type"]}
    assert by_source_type["forum"]["total_count"] == 2
    assert by_source_type["registry"]["total_count"] == 1

    by_domain_tag = {item["key"]: item for item in report["by_domain_tag"]}
    assert by_domain_tag["devtools"]["total_count"] == 3
    assert by_domain_tag["ai"]["total_count"] == 1

    by_signal_role = {item["key"]: item for item in report["by_signal_role"]}
    assert by_signal_role["market"]["total_count"] == 2
    assert by_signal_role["solution"]["total_count"] == 1

    assert [item["source_adapter"] for item in report["recommendations"]] == [
        "npm_registry",
        "hackernews",
    ]


def test_get_signal_freshness_report_filters_source_adapters(mcp_db) -> None:
    _seed_signals(mcp_db)

    report = get_signal_freshness_report(
        max_age_days=30,
        source_adapters=["hackernews"],
    )

    assert report["source_adapter_filters"] == ["hackernews"]
    assert report["filters"] == {
        "source_adapters": ["hackernews"],
        "max_age_days": 30,
    }
    assert report["total_signals"] == 2
    assert {item["key"] for item in report["by_source_adapter"]} == {"hackernews"}


def test_get_signal_freshness_report_invalid_max_age_days_returns_validation_error(
    mcp_db,
) -> None:
    result = get_signal_freshness_report(max_age_days=0)

    assert result["code"] == 400
    assert "max_age_days" in result["error"]
    assert result["details"]["field"] == "max_age_days"
    assert result["details"]["expected"] == "integer >= 1"
    assert result["details"]["actual"] == "0"


def test_signal_freshness_resource_returns_default_json(mcp_db) -> None:
    _seed_signals(mcp_db)

    payload = json.loads(signal_freshness_report_detail())

    assert payload["max_age_days"] == 30
    assert payload["total_signals"] == 3
    assert payload["has_stale_signals"] is True
    assert payload["has_refresh_recommendations"] is True


def test_create_mcp_server_registers_signal_freshness_tool_and_resource(
    monkeypatch: pytest.MonkeyPatch,
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

    monkeypatch.setattr(mcp_tools, "FastMCP", FakeMCP)

    mcp_tools.create_mcp_server()

    assert "get_signal_freshness_report" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["signal-freshness://report"]
        == "signal_freshness_report_detail"
    )
