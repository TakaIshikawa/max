from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_executive_memo import SCHEMA_VERSION
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_executive_memo_detail,
    get_design_brief_executive_memo,
    set_store_factory,
)
from max.store.db import Store
from tests.test_design_brief_executive_memo import _seed_design_brief


@pytest.fixture
def mcp_executive_memo_db(tmp_path):
    db_path = str(tmp_path / "mcp_executive_memo.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_executive_memo_brief_id(mcp_executive_memo_db) -> str:
    store = Store(db_path=mcp_executive_memo_db, wal_mode=True)
    try:
        return _seed_design_brief(store)
    finally:
        store.close()


def test_get_design_brief_executive_memo_json(seeded_executive_memo_brief_id) -> None:
    result = get_design_brief_executive_memo(seeded_executive_memo_brief_id)

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["format"] == "json"
    assert result["design_brief"]["id"] == seeded_executive_memo_brief_id
    assert result["decision_summary"]["recommendation"] == "approve-validation"
    assert result["target_segment"]["buyer"] == "VP product"
    assert result["evidence_highlights"]
    assert result["top_risks"]
    assert json.loads(result["rendered"])["schema_version"] == SCHEMA_VERSION


def test_get_design_brief_executive_memo_markdown(seeded_executive_memo_brief_id) -> None:
    result = get_design_brief_executive_memo(
        seeded_executive_memo_brief_id,
        format="markdown",
    )

    assert result["id"] == seeded_executive_memo_brief_id
    assert result["format"] == "markdown"
    assert result["markdown"].startswith("# Executive Memo: Executive Memo Brief")
    assert "Schema: `max.design_brief.executive_memo.v1`" in result["markdown"]
    assert "## Decision Summary" in result["markdown"]
    assert "## Validation Next Step" in result["markdown"]


def test_get_design_brief_executive_memo_not_found(mcp_executive_memo_db) -> None:
    result = get_design_brief_executive_memo("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_executive_memo_invalid_format(
    seeded_executive_memo_brief_id,
) -> None:
    result = get_design_brief_executive_memo(
        seeded_executive_memo_brief_id,
        format="yaml",
    )

    assert result["error"] == "Unsupported executive memo format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"


def test_design_brief_executive_memo_resource(seeded_executive_memo_brief_id) -> None:
    result = json.loads(design_brief_executive_memo_detail(seeded_executive_memo_brief_id))

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["format"] == "json"
    assert result["design_brief"]["id"] == seeded_executive_memo_brief_id
    assert json.loads(result["rendered"])["design_brief"]["id"] == seeded_executive_memo_brief_id


def test_create_mcp_server_registers_executive_memo_tool(monkeypatch) -> None:
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

    assert "get_design_brief_executive_memo" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-brief-executive-memos://{brief_id}"]
        == "design_brief_executive_memo_detail"
    )
