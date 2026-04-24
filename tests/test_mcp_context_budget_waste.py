from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from max.analysis.context_budget import build_context_budget_waste_report
from max.server import mcp_tools
from max.server.mcp_tools import (
    context_budget_waste_detail,
    max_context_budget_waste,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def mcp_context_budget_db(tmp_path: Path) -> str:
    db_path = str(tmp_path / "mcp_context_budget_waste.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


def _signal(signal_id: str, *, adapter: str, fetched_at: datetime, content: str = "") -> Signal:
    return Signal(
        id=signal_id,
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter,
        title=f"Signal {signal_id}",
        content=content or f"Context payload for {signal_id} from {adapter}.",
        url=f"https://example.com/{signal_id}",
        fetched_at=fetched_at,
        credibility=0.7,
    )


def _seed_context_budget_rows(db_path: str) -> None:
    now = datetime.now(timezone.utc)
    stale_at = now - timedelta(days=90)
    fresh_at = now - timedelta(days=2)
    large_payload = " ".join(["large context contributor"] * 250)

    with Store(db_path=db_path, wal_mode=True) as store:
        store.insert_signal(
            _signal(
                "sig-github-used",
                adapter="github",
                fetched_at=fresh_at,
                content=large_payload,
            )
        )
        store.insert_signal(_signal("sig-github-unused", adapter="github", fetched_at=fresh_at))
        store.insert_signal(_signal("sig-reddit-stale", adapter="reddit", fetched_at=stale_at))

        store.insert_insight(
            Insight(
                id="ins-github-used",
                category=InsightCategory.GAP,
                title="Used insight",
                summary="A reused signal supports an idea.",
                evidence=["sig-github-used"],
                confidence=0.8,
            )
        )
        store.insert_buildable_unit(
            BuildableUnit(
                id="bu-context-budget",
                title="Context budget pruning",
                one_liner="Uses evidence",
                category=BuildableCategory.APPLICATION,
                ideation_mode=IdeationMode.DIRECT,
                problem="Too much context",
                solution="Prune unused sources",
                value_proposition="Lower LLM spend",
                inspiring_insights=["ins-github-used"],
                evidence_signals=["sig-github-used"],
            )
        )


def test_max_context_budget_waste_returns_rest_core_fields_with_warning_booleans(
    mcp_context_budget_db: str,
) -> None:
    _seed_context_budget_rows(mcp_context_budget_db)

    report = max_context_budget_waste(
        days=30,
        source_adapter="github",
        min_reuse_count=1,
        adapter_limit=5,
    )

    with Store(db_path=mcp_context_budget_db, wal_mode=True) as store:
        rest_report = build_context_budget_waste_report(
            store,
            days=30,
            source_adapter="github",
            min_reuse_count=1,
        )

    for field in (
        "days",
        "source_adapter_filter",
        "min_reuse_count",
        "total_signals",
        "total_estimated_tokens",
        "insight_count",
        "idea_count",
        "reused_signal_count",
        "evidence_link_count",
        "evidence_reuse_rate",
        "low_utility_signal_count",
        "low_utility_signal_rate",
        "stale_signal_count",
        "stale_signal_rate",
        "projected_token_savings",
        "projected_cost_savings_usd",
    ):
        assert report[field] == rest_report[field]

    assert report["adapter_limit"] == 5
    assert report["high_waste_warning"] is True
    assert report["oversized_context_contributor_warning"] is True
    assert report["has_context_budget_waste_warnings"] is True
    adapter = report["adapters"][0]
    assert adapter["source_adapter"] == "github"
    assert adapter["high_waste_warning"] is True
    assert adapter["oversized_context_contributor_warning"] is True
    assert adapter["warning"] is True
    assert adapter["context_token_share"] == 1.0
    json.dumps(report)


@pytest.mark.parametrize(
    ("kwargs", "field", "expected"),
    [
        ({"days": 0}, "days", "integer between 1 and 3650"),
        ({"source_adapter": ""}, "source_adapter", "string length 1 to 100"),
        ({"min_reuse_count": 101}, "min_reuse_count", "integer between 0 and 100"),
        ({"adapter_limit": 0}, "adapter_limit", "integer between 1 and 500"),
    ],
)
def test_max_context_budget_waste_invalid_parameters_return_mcp_validation_errors(
    mcp_context_budget_db: str,
    kwargs: dict[str, object],
    field: str,
    expected: str,
) -> None:
    result = max_context_budget_waste(**kwargs)

    assert result["code"] == 400
    assert field in result["error"]
    assert result["details"]["field"] == field
    assert result["details"]["expected"] == expected


def test_context_budget_waste_resource_returns_default_json(
    mcp_context_budget_db: str,
) -> None:
    _seed_context_budget_rows(mcp_context_budget_db)

    payload = json.loads(context_budget_waste_detail())

    assert payload["days"] == 30
    assert payload["source_adapter_filter"] is None
    assert payload["min_reuse_count"] == 1
    assert payload["adapter_limit"] == 20
    assert payload["total_signals"] == 3
    assert payload["has_context_budget_waste_warnings"] is True
    assert "high_waste_warning" in payload["adapters"][0]
    assert "oversized_context_contributor_warning" in payload["adapters"][0]


def test_create_mcp_server_registers_context_budget_waste_tool_and_resource(
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

    assert "max_context_budget_waste" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["context-budget://waste"]
        == "context_budget_waste_detail"
    )
