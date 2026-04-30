"""Tests for unit dependency map exposed through MCP."""

from __future__ import annotations

import json

import pytest

from max.server.mcp_tools import (
    create_mcp_server,
    get_unit_dependency_map,
    set_store_factory,
    unit_dependency_map_detail,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit


@pytest.fixture
def mcp_unit_dependency_db(tmp_path):
    db_path = str(tmp_path / "mcp_unit_dependency_map.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


def _unit(
    unit_id: str,
    title: str,
    problem: str,
    solution: str,
    *,
    evidence: list[str] | None = None,
    tech_approach: str = "Python FastAPI service",
) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=title,
        one_liner=problem,
        category=BuildableCategory.APPLICATION,
        problem=problem,
        solution=solution,
        target_users="platform engineers",
        specific_user="platform engineer",
        value_proposition="Reduce manual coordination work",
        evidence_signals=evidence or [],
        suggested_stack={"language": "python", "runtime": "fastapi"},
        tech_approach=tech_approach,
        quality_score=7.0,
    )


def test_get_unit_dependency_map_returns_structured_clusters_and_edges(
    mcp_unit_dependency_db,
) -> None:
    with Store(db_path=mcp_unit_dependency_db, wal_mode=True) as store:
        store.insert_buildable_unit(
            _unit(
                "bu-foundation",
                "Evidence Ingestion Foundation",
                "Teams need a shared evidence ingestion foundation.",
                "Create the reusable ingestion foundation.",
                evidence=["sig-shared", "sig-foundation"],
            )
        )
        store.insert_buildable_unit(
            _unit(
                "bu-review",
                "Review Automation Console",
                "Platform engineers need a review console.",
                "Build a console after the Evidence Ingestion Foundation exists.",
                evidence=["sig-shared", "sig-review"],
            )
        )

    result = get_unit_dependency_map(limit=50, min_shared_signals=1)

    assert result["kind"] == "max.unit_dependency_map"
    assert result["parameters"] == {"limit": 50, "min_shared_signals": 1}
    assert result["summary"]["unit_count"] == 2
    assert result["summary"]["edge_count"] >= 1
    assert result["summary"]["cluster_count"] >= 1
    assert [node["id"] for node in result["nodes"]] == ["bu-foundation", "bu-review"]

    edge = next(
        item
        for item in result["edges"]
        if item["source"] == "bu-foundation" and item["target"] == "bu-review"
    )
    assert edge["direction"] == "prerequisite"
    assert "shared_evidence" in {reason["type"] for reason in edge["reasons"]}
    assert any(cluster["type"] == "shared_evidence" for cluster in result["clusters"])


def test_get_unit_dependency_map_markdown_mode(mcp_unit_dependency_db) -> None:
    with Store(db_path=mcp_unit_dependency_db, wal_mode=True) as store:
        store.insert_buildable_unit(
            _unit(
                "bu-foundation",
                "Evidence Ingestion Foundation",
                "Create foundation for review automation.",
                "Build shared evidence APIs.",
                evidence=["sig-shared"],
            )
        )
        store.insert_buildable_unit(
            _unit(
                "bu-review",
                "Review Automation Console",
                "Console depends on Evidence Ingestion Foundation.",
                "Build after the foundation.",
                evidence=["sig-shared"],
            )
        )

    result = get_unit_dependency_map(format="markdown")

    assert result["format"] == "markdown"
    assert result["summary"]["unit_count"] == 2
    assert result["parameters"] == {"limit": 100, "min_shared_signals": 1}
    assert result["markdown"].startswith("# Buildable Unit Dependency Map")
    assert "## Clusters" in result["markdown"]
    assert "bu-foundation -> bu-review" in result["markdown"]


@pytest.mark.parametrize(
    ("kwargs", "field", "expected", "actual"),
    [
        ({"limit": 0}, "limit", "integer >= 1", "0"),
        ({"min_shared_signals": 0}, "min_shared_signals", "integer >= 1", "0"),
        ({"format": "html"}, "format", "json or markdown", "html"),
    ],
)
def test_get_unit_dependency_map_invalid_parameters_return_validation_error(
    mcp_unit_dependency_db,
    kwargs: dict,
    field: str,
    expected: str,
    actual: str,
) -> None:
    result = get_unit_dependency_map(**kwargs)

    assert result["code"] == 400
    assert result["details"] == {
        "field": field,
        "expected": expected,
        "actual": actual,
    }


def test_unit_dependency_map_resource_returns_default_json(
    mcp_unit_dependency_db,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "max.server.mcp_tools.get_unit_dependency_map",
        lambda: {"kind": "max.unit_dependency_map", "summary": {"unit_count": 0}},
    )

    assert json.loads(unit_dependency_map_detail()) == {
        "kind": "max.unit_dependency_map",
        "summary": {"unit_count": 0},
    }


def test_create_mcp_server_registers_unit_dependency_map_tool_and_resource(
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

    assert "get_unit_dependency_map" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["unit-dependency-map://all"]
        == "unit_dependency_map_detail"
    )
