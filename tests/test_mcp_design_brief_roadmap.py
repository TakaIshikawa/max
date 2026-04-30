from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_roadmap import SCHEMA_VERSION
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_roadmap_detail,
    get_design_brief_roadmap,
    set_store_factory,
)
from max.store.db import Store
from tests.test_design_brief_roadmap import _seed_brief


@pytest.fixture
def mcp_roadmap_db(tmp_path):
    db_path = str(tmp_path / "mcp_roadmap.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_roadmap_brief_id(mcp_roadmap_db) -> str:
    store = Store(db_path=mcp_roadmap_db, wal_mode=True)
    try:
        return _seed_brief(store)
    finally:
        store.close()


def test_get_design_brief_roadmap_structured(seeded_roadmap_brief_id) -> None:
    result = get_design_brief_roadmap(seeded_roadmap_brief_id)

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_roadmap_brief_id
    assert result["design_brief"]["title"] == "Roadmap Brief"
    assert [phase["id"] for phase in result["phases"]] == [
        "discovery",
        "prototype",
        "validation",
        "beta",
        "launch",
    ]
    assert result["items"]
    assert result["summary"]["item_count"] == len(result["items"])


def test_get_design_brief_roadmap_markdown_boolean(
    seeded_roadmap_brief_id,
) -> None:
    result = get_design_brief_roadmap(seeded_roadmap_brief_id, markdown=True)

    assert result["id"] == seeded_roadmap_brief_id
    assert result["format"] == "markdown"
    assert "# Roadmap: Roadmap Brief" in result["markdown"]
    assert "Schema: `max.design_brief.roadmap.v1`" in result["markdown"]
    assert "## Discovery" in result["markdown"]
    assert "## Prototype" in result["markdown"]
    assert "## Validation" in result["markdown"]
    assert "## Beta" in result["markdown"]
    assert "## Launch" in result["markdown"]


def test_get_design_brief_roadmap_missing_brief_returns_mcp_error(
    mcp_roadmap_db,
) -> None:
    result = get_design_brief_roadmap("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_design_brief_roadmap_resource(seeded_roadmap_brief_id) -> None:
    result = json.loads(design_brief_roadmap_detail(seeded_roadmap_brief_id))

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_roadmap_brief_id
    assert result["items"]


def test_create_mcp_server_registers_roadmap_tool(monkeypatch) -> None:
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

    assert "get_design_brief_roadmap" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-brief-roadmaps://{brief_id}"]
        == "design_brief_roadmap_detail"
    )
