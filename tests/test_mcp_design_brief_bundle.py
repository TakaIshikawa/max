from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_bundle import SCHEMA_VERSION
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_bundle_detail,
    get_design_brief_bundle,
    set_store_factory,
)
from max.store.db import Store
from tests.test_design_brief_bundle import _seed_design_brief


@pytest.fixture
def mcp_bundle_db(tmp_path):
    db_path = str(tmp_path / "mcp_design_brief_bundle.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_bundle_brief_id(mcp_bundle_db) -> str:
    store = Store(db_path=mcp_bundle_db, wal_mode=True)
    try:
        return _seed_design_brief(store)
    finally:
        store.close()


def test_get_design_brief_bundle_json(seeded_bundle_brief_id) -> None:
    result = get_design_brief_bundle(seeded_bundle_brief_id)

    assert result["id"] == seeded_bundle_brief_id
    assert result["format"] == "json"
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_bundle_brief_id
    assert result["artifact_status"]["design_brief"]["status"] == "generated"
    assert result["artifact_status"]["prd"]["status"] == "generated"
    assert result["prd"]["sections"]["problem"]["content"]
    assert json.loads(result["rendered"])["design_brief"]["id"] == seeded_bundle_brief_id


def test_get_design_brief_bundle_markdown(seeded_bundle_brief_id) -> None:
    result = get_design_brief_bundle(seeded_bundle_brief_id, format="markdown")

    assert result["id"] == seeded_bundle_brief_id
    assert result["format"] == "markdown"
    assert result["bundle"]["design_brief"]["id"] == seeded_bundle_brief_id
    assert result["artifact_status"]["roadmap"]["status"] == "generated"
    assert "# Design Brief Bundle: Bundle Export Brief" in result["markdown"]
    assert "Schema: `max.design_brief.bundle.v1`" in result["markdown"]
    assert "## PRD" in result["markdown"]


def test_get_design_brief_bundle_not_found(mcp_bundle_db) -> None:
    result = get_design_brief_bundle("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_bundle_invalid_format(seeded_bundle_brief_id) -> None:
    result = get_design_brief_bundle(seeded_bundle_brief_id, format="yaml")

    assert result["error"] == "Unsupported design brief bundle format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"


def test_design_brief_bundle_resource(seeded_bundle_brief_id) -> None:
    result = json.loads(design_brief_bundle_detail(seeded_bundle_brief_id))

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_bundle_brief_id
    assert result["artifact_status"]["competitive_landscape"]["status"] == "generated"


def test_create_mcp_server_registers_bundle_tool(monkeypatch) -> None:
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

    assert "get_design_brief_bundle" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-brief-bundles://{brief_id}"]
        == "design_brief_bundle_detail"
    )
