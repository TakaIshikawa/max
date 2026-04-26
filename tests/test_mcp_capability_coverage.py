"""Tests for MCP capability coverage analysis."""

from __future__ import annotations

import json

import pytest

from max.analysis.mcp_capability_coverage import (
    build_mcp_capability_coverage_report,
    classify_mcp_capability,
)
from max.server import mcp_tools
from max.server.mcp_tools import (
    max_mcp_capability_coverage,
    mcp_capability_coverage_detail,
    set_store_factory,
)
from max.store.db import Store
from max.types.signal import Signal, SignalSourceType


def _insert_signal(
    store: Store,
    *,
    signal_id: str,
    source_adapter: str,
    title: str,
    content: str = "MCP server",
    tags: list[str] | None = None,
    metadata: dict | None = None,
) -> None:
    store.insert_signal(
        Signal(
            id=signal_id,
            source_type=SignalSourceType.REGISTRY,
            source_adapter=source_adapter,
            title=title,
            content=content,
            url=f"https://example.com/{signal_id}",
            tags=["mcp"] if tags is None else tags,
            metadata=metadata or {},
        )
    )


def test_classify_mcp_capability_uses_tags_title_content_and_metadata() -> None:
    assert (
        classify_mcp_capability(
            {
                "title": "Generic MCP connector",
                "content": "",
                "tags": ["observability"],
                "metadata": {},
            }
        )
        == "observability"
    )
    assert (
        classify_mcp_capability(
            {
                "title": "MCP server",
                "content": "Connects agents to tools",
                "tags": [],
                "metadata": {"capability": "FHIR patient records"},
            }
        )
        == "healthcare"
    )
    assert (
        classify_mcp_capability(
            {
                "title": "MCP server",
                "content": "Connects agents to tools",
                "tags": [],
                "metadata": {},
            }
        )
        == "unknown"
    )


def test_build_mcp_capability_coverage_counts_categories_and_adapters(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "coverage.db"))
    try:
        _insert_signal(
            store,
            signal_id="sig-filesystem",
            source_adapter="mcp_registry",
            title="Filesystem MCP server",
            content="Read files and directories",
        )
        _insert_signal(
            store,
            signal_id="sig-browser",
            source_adapter="npm_registry",
            title="Browser automation MCP",
            content="Playwright browser tools",
        )
        _insert_signal(
            store,
            signal_id="sig-security",
            source_adapter="github",
            title="Security audit MCP",
            content="Find secrets and CVEs",
        )
        _insert_signal(
            store,
            signal_id="sig-healthcare",
            source_adapter="awesome_lists",
            title="Clinical MCP connector",
            content="FHIR patient workflow",
            tags=["mcp", "healthcare"],
            metadata={"domain": "healthcare"},
        )
        _insert_signal(
            store,
            signal_id="sig-unknown",
            source_adapter="mcp_registry",
            title="Generic MCP tools",
        )
        _insert_signal(
            store,
            signal_id="sig-unrelated",
            source_adapter="reddit",
            title="General developer tool",
            content="No protocol mention",
            tags=[],
        )

        report = build_mcp_capability_coverage_report(
            store,
            min_count=2,
            limit_representatives=1,
        )
    finally:
        store.close()

    by_category = {category.category: category for category in report.categories}
    assert report.total_signals == 5
    assert by_category["filesystem"].total_count == 1
    assert by_category["browser"].total_count == 1
    assert by_category["security"].source_adapters == {"github": 1}
    assert by_category["unknown"].total_count == 1
    assert len(by_category["filesystem"].representative_signal_ids) == 1
    assert report.category_percentages["filesystem"] == 20.0
    assert "finance" in report.undercovered_categories
    assert "filesystem" in report.undercovered_categories

    by_adapter = {adapter.source_adapter: adapter for adapter in report.top_source_adapters}
    assert by_adapter["mcp_registry"].total_count == 2
    assert by_adapter["mcp_registry"].categories == {"filesystem": 1, "unknown": 1}


def test_build_mcp_capability_coverage_filters_domain_and_source_adapter(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "coverage_filters.db"))
    try:
        _insert_signal(
            store,
            signal_id="sig-healthcare",
            source_adapter="awesome_lists",
            title="Clinical MCP connector",
            content="FHIR patient data",
            tags=["mcp", "healthcare"],
            metadata={"domain": "healthcare"},
        )
        _insert_signal(
            store,
            signal_id="sig-finance",
            source_adapter="npm_registry",
            title="Finance MCP connector",
            content="Payments and ledger data",
            tags=["mcp", "finance"],
            metadata={"domain": "finance"},
        )

        report = build_mcp_capability_coverage_report(
            store,
            domain="healthcare",
            source_adapter="awesome_lists",
        )
    finally:
        store.close()

    by_category = {category.category: category for category in report.categories}
    assert report.total_signals == 1
    assert report.domain == "healthcare"
    assert report.source_adapter_filter == "awesome_lists"
    assert by_category["healthcare"].total_count == 1
    assert by_category["finance"].total_count == 0


@pytest.fixture
def mcp_capability_db(tmp_path):
    db_path = str(tmp_path / "mcp_capability_coverage.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


def _seed_mcp_capability_rows(db_path: str) -> None:
    with Store(db_path=db_path, wal_mode=True) as store:
        _insert_signal(
            store,
            signal_id="sig-filesystem",
            source_adapter="mcp_registry",
            title="Filesystem MCP server",
            content="Read files and directories",
        )
        _insert_signal(
            store,
            signal_id="sig-browser",
            source_adapter="npm_registry",
            title="Browser automation MCP",
            content="Playwright browser tools",
        )
        _insert_signal(
            store,
            signal_id="sig-healthcare",
            source_adapter="awesome_lists",
            title="Clinical MCP connector",
            content="FHIR patient workflow",
            tags=["mcp", "healthcare"],
            metadata={"domain": "healthcare"},
        )


def test_max_mcp_capability_coverage_returns_agent_gap_payload(
    mcp_capability_db: str,
) -> None:
    _seed_mcp_capability_rows(mcp_capability_db)

    report = max_mcp_capability_coverage(min_count=2, limit_representatives=1)

    assert report["schema_version"] == "1.0"
    assert report["total_signals"] == 3
    assert report["gap_counts"]["finance"] == 2
    assert report["gap_summary"]["critical"] >= 1
    by_category = {
        bucket["category"]: bucket for bucket in report["capability_buckets"]
    }
    assert by_category["filesystem"]["gap_count"] == 1
    assert by_category["filesystem"]["gap_severity"] == "medium"
    assert by_category["filesystem"]["undercovered"] is True
    assert by_category["filesystem"]["representative_signal_ids"] == ["sig-filesystem"]
    assert by_category["filesystem"]["representative_signals"] == [
        {
            "id": "sig-filesystem",
            "title": "Filesystem MCP server",
            "source_adapter": "mcp_registry",
            "source_type": "registry",
            "url": "https://example.com/sig-filesystem",
            "tags": ["mcp"],
        }
    ]
    json.dumps(report)


@pytest.mark.parametrize(
    ("kwargs", "field", "expected"),
    [
        ({"min_count": 0}, "min_count", "integer between 1 and 10000"),
        (
            {"limit_representatives": -1},
            "limit_representatives",
            "integer between 0 and 100",
        ),
        ({"source_adapter": ""}, "source_adapter", "non-empty string"),
        ({"domain": ""}, "domain", "non-empty string"),
    ],
)
def test_max_mcp_capability_coverage_invalid_parameters_return_mcp_errors(
    mcp_capability_db: str,
    kwargs: dict[str, object],
    field: str,
    expected: str,
) -> None:
    result = max_mcp_capability_coverage(**kwargs)

    assert result["code"] == 400
    assert field in result["error"]
    assert result["details"]["field"] == field
    assert result["details"]["expected"] == expected


def test_mcp_capability_coverage_resource_returns_default_json(
    mcp_capability_db: str,
) -> None:
    _seed_mcp_capability_rows(mcp_capability_db)

    payload = json.loads(mcp_capability_coverage_detail())

    assert payload["schema_version"] == "1.0"
    assert payload["min_count"] == 2
    assert payload["limit_representatives"] == 3
    assert payload["source_adapter_filter"] is None
    assert payload["domain"] is None
    assert payload["total_signals"] == 3
    assert "capability_buckets" in payload
    assert "gap_counts" in payload
    assert "gap_severity" in payload["capability_buckets"][0]


def test_create_mcp_server_registers_mcp_capability_coverage_tool_and_resource(
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

    assert "max_mcp_capability_coverage" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["mcp-capabilities://coverage"]
        == "mcp_capability_coverage_detail"
    )
