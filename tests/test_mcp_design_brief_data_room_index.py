from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_data_room_index import SCHEMA_VERSION
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_data_room_index_detail,
    get_design_brief_data_room_index,
    set_store_factory,
)
from max.store.db import Store
from tests.test_design_brief_bundle import _seed_design_brief


@pytest.fixture
def mcp_data_room_index_db(tmp_path):
    db_path = str(tmp_path / "mcp_design_brief_data_room_index.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_data_room_index_brief_id(mcp_data_room_index_db) -> str:
    store = Store(db_path=mcp_data_room_index_db, wal_mode=True)
    try:
        return _seed_design_brief(store)
    finally:
        store.close()


def test_get_design_brief_data_room_index_json(seeded_data_room_index_brief_id) -> None:
    result = get_design_brief_data_room_index(seeded_data_room_index_brief_id)

    assert result["id"] == seeded_data_room_index_brief_id
    assert result["format"] == "json"
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["kind"] == "max.design_brief.data_room_index"
    assert result["design_brief"]["id"] == seeded_data_room_index_brief_id
    assert result["summary"]["available_formats"] == ["json", "markdown", "csv"]
    assert result["summary"]["section_count"] == len(result["sections"])
    assert result["summary"]["artifact_count"] == len(result["artifacts"])
    assert result["sections"][0]["key"] == "core"
    assert result["artifacts"][0]["key"] == "design_brief"
    assert (
        result["artifacts"][0]["urls"]["json"]
        == f"/api/v1/design-briefs/{seeded_data_room_index_brief_id}"
    )
    assert json.loads(result["rendered"])["design_brief"]["id"] == seeded_data_room_index_brief_id


def test_get_design_brief_data_room_index_markdown(
    seeded_data_room_index_brief_id,
) -> None:
    result = get_design_brief_data_room_index(
        seeded_data_room_index_brief_id,
        format="markdown",
    )

    assert result["id"] == seeded_data_room_index_brief_id
    assert result["format"] == "markdown"
    assert result["data_room_index"]["design_brief"]["id"] == seeded_data_room_index_brief_id
    assert result["sections"][0]["key"] == "core"
    assert "# Data Room Index: Bundle Export Brief" in result["markdown"]
    assert "Schema: `max.design_brief.data_room_index.v1`" in result["markdown"]
    assert "## Artifact Index" in result["markdown"]
    assert "## Sections" in result["markdown"]
    assert "/api/v1/design-briefs/" in result["markdown"]


def test_get_design_brief_data_room_index_not_found(mcp_data_room_index_db) -> None:
    result = get_design_brief_data_room_index("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_data_room_index_invalid_format(
    seeded_data_room_index_brief_id,
) -> None:
    result = get_design_brief_data_room_index(
        seeded_data_room_index_brief_id,
        format="yaml",
    )

    assert result["error"] == "Unsupported design brief data room index format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"


def test_design_brief_data_room_index_resource(seeded_data_room_index_brief_id) -> None:
    result = json.loads(design_brief_data_room_index_detail(seeded_data_room_index_brief_id))

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_data_room_index_brief_id
    assert any(section["key"] == "commercial" for section in result["sections"])


def test_create_mcp_server_registers_data_room_index_tool(monkeypatch) -> None:
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

    assert "get_design_brief_data_room_index" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-brief-data-room-indexes://{brief_id}"]
        == "design_brief_data_room_index_detail"
    )
