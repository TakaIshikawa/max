"""Tests for buildable unit dependency map analysis."""

from __future__ import annotations

import pytest

from max.analysis.unit_dependency_map import (
    build_unit_dependency_map,
    render_unit_dependency_map,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit


@pytest.fixture
def store() -> Store:
    s = Store(db_path=":memory:")
    yield s
    s.close()


def _unit(
    unit_id: str,
    title: str,
    problem: str,
    solution: str,
    *,
    target_users: str = "platform engineers",
    specific_user: str = "platform engineer",
    evidence: list[str] | None = None,
    stack: dict | None = None,
    tech_approach: str = "",
    composability_notes: str = "",
) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=title,
        one_liner=problem,
        category=BuildableCategory.APPLICATION,
        problem=problem,
        solution=solution,
        target_users=target_users,
        specific_user=specific_user,
        value_proposition="Reduce manual coordination work",
        evidence_signals=evidence or [],
        suggested_stack=stack or {"language": "python", "runtime": "fastapi"},
        tech_approach=tech_approach,
        composability_notes=composability_notes,
        quality_score=7.0,
    )


def test_dependency_map_includes_nodes_edges_clusters_and_stable_order(store: Store) -> None:
    store.insert_buildable_unit(
        _unit(
            "bu-foundation",
            "Evidence Ingestion Foundation",
            "Teams need a shared evidence ingestion foundation before downstream review tools.",
            "Create the reusable ingestion foundation and normalized evidence store.",
            evidence=["sig-shared", "sig-foundation"],
            tech_approach="Python FastAPI service with Postgres queues",
            composability_notes="Foundation for review automation.",
        )
    )
    store.insert_buildable_unit(
        _unit(
            "bu-review",
            "Review Automation Console",
            "Platform engineers need a review console that depends on the Evidence Ingestion Foundation.",
            "Build a console after the ingestion foundation exists.",
            evidence=["sig-shared", "sig-review"],
            tech_approach="Python FastAPI API with React console",
            composability_notes="Depends on Evidence Ingestion Foundation APIs.",
        )
    )
    store.insert_buildable_unit(
        _unit(
            "bu-payroll",
            "Payroll Export Cleaner",
            "Payroll analysts need cleaner spreadsheet exports.",
            "Normalize payroll spreadsheets.",
            target_users="finance teams",
            specific_user="payroll analyst",
            evidence=["sig-payroll"],
            stack={"language": "typescript", "runtime": "node"},
        )
    )

    report = build_unit_dependency_map(store)

    assert [node["id"] for node in report["nodes"]] == [
        "bu-foundation",
        "bu-payroll",
        "bu-review",
    ]
    assert len(report["nodes"]) == 3
    assert report["isolated_units"] == ["bu-payroll"]
    assert report["recommended_build_order"].index("bu-foundation") < report[
        "recommended_build_order"
    ].index("bu-review")

    edge = next(
        item
        for item in report["edges"]
        if item["source"] == "bu-foundation" and item["target"] == "bu-review"
    )
    reason_types = {reason["type"] for reason in edge["reasons"]}
    assert {
        "shared_evidence",
        "shared_stack",
        "same_target_user",
        "prerequisite_wording",
    } <= reason_types
    assert 0.0 < edge["confidence"] <= 1.0
    assert edge["direction"] == "prerequisite"

    cluster_types = {cluster["type"] for cluster in report["clusters"]}
    assert {"shared_evidence", "shared_stack", "same_target_user", "prerequisite"} <= cluster_types


def test_dependency_map_respects_limit_and_min_shared_signals(store: Store) -> None:
    store.insert_buildable_unit(
        _unit("bu-a", "Alpha", "Shared user problem", "Build alpha", evidence=["sig-1"])
    )
    store.insert_buildable_unit(
        _unit("bu-b", "Beta", "Shared user problem", "Build beta", evidence=["sig-1"])
    )
    store.insert_buildable_unit(
        _unit("bu-c", "Gamma", "Shared user problem", "Build gamma", evidence=["sig-1"])
    )

    report = build_unit_dependency_map(store, limit=2, min_shared_signals=2)

    assert [node["id"] for node in report["nodes"]] == ["bu-a", "bu-b"]
    assert all(
        reason["type"] != "shared_evidence"
        for edge in report["edges"]
        for reason in edge["reasons"]
    )


def test_render_unit_dependency_map_markdown_summarizes_clusters_and_edges(store: Store) -> None:
    store.insert_buildable_unit(
        _unit(
            "bu-foundation",
            "Evidence Ingestion Foundation",
            "Create foundation for review automation.",
            "Build shared evidence APIs.",
            evidence=["sig-shared"],
            tech_approach="Python FastAPI service",
        )
    )
    store.insert_buildable_unit(
        _unit(
            "bu-review",
            "Review Automation Console",
            "Console depends on Evidence Ingestion Foundation.",
            "Build after the foundation.",
            evidence=["sig-shared"],
            tech_approach="Python FastAPI service",
        )
    )

    report = build_unit_dependency_map(store)
    markdown = render_unit_dependency_map(report)

    assert markdown.startswith("# Buildable Unit Dependency Map")
    assert "## Clusters" in markdown
    assert "## Edges" in markdown
    assert "shared_evidence" in markdown
    assert "prerequisite_wording" in markdown
    assert "bu-foundation -> bu-review" in markdown
