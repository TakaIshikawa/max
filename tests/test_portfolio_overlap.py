"""Tests for portfolio overlap analysis."""

from __future__ import annotations

import json

from max.analysis.portfolio_overlap import find_portfolio_overlap_clusters
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit


def _unit(
    unit_id: str,
    title: str,
    problem: str,
    *,
    target_users: str = "devtools teams",
    specific_user: str = "platform engineer",
    evidence: list[str] | None = None,
    stack: dict | None = None,
    status: str = "evaluated",
) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=title,
        one_liner=problem,
        category=BuildableCategory.APPLICATION,
        problem=problem,
        solution="Build a focused workflow tool",
        target_users=target_users,
        specific_user=specific_user,
        value_proposition="Reduce manual review work",
        evidence_signals=evidence or [],
        tech_approach="TypeScript service with workflow automation",
        suggested_stack=stack or {"language": "typescript", "runtime": "node"},
        quality_score=7.0,
        usefulness_score=8.0,
        status=status,
    )


def _store_embedding(store: Store, entity_id: str, embedding: list[float]) -> None:
    store.conn.execute(
        "INSERT INTO embeddings (id, entity_type, embedding) VALUES (?, ?, ?)",
        (entity_id, "buildable_unit", json.dumps(embedding)),
    )
    store.conn.commit()


def test_find_portfolio_overlap_clusters_groups_shared_market_problem_and_evidence(store: Store) -> None:
    store.insert_buildable_unit(
        _unit(
            "bu-a",
            "MCP Test Runner",
            "MCP maintainers need repeatable server testing before release",
            evidence=["sig-1", "sig-2"],
        )
    )
    store.insert_buildable_unit(
        _unit(
            "bu-b",
            "MCP Protocol Validator",
            "MCP maintainers need repeatable protocol validation testing",
            evidence=["sig-2", "sig-3"],
        )
    )
    store.insert_buildable_unit(
        _unit(
            "bu-c",
            "Payroll Export Cleaner",
            "Payroll analysts need cleaner spreadsheet exports",
            target_users="finance teams",
            specific_user="payroll analyst",
            evidence=["sig-payroll"],
            stack={"language": "python", "runtime": "cli"},
        )
    )

    clusters = find_portfolio_overlap_clusters(store, min_overlap_score=0.25)

    assert len(clusters) == 1
    assert clusters[0].idea_ids == ["bu-a", "bu-b"]
    assert clusters[0].representative_idea_ids == ["bu-a", "bu-b"]
    assert clusters[0].suggested_action in {"merge", "differentiate"}
    assert {reason.type for reason in clusters[0].overlap_reasons} >= {
        "target_users",
        "problem_statement",
        "evidence_signal_ids",
    }


def test_find_portfolio_overlap_clusters_can_include_archived_and_use_stored_embeddings(store: Store) -> None:
    store.insert_buildable_unit(
        _unit("bu-live", "Incident Triage", "SREs need incident triage automation")
    )
    store.insert_buildable_unit(
        _unit(
            "bu-archived",
            "Alert Triage",
            "Support teams need alert grouping",
            status="archived",
        )
    )
    _store_embedding(store, "bu-live", [1.0, 0.0])
    _store_embedding(store, "bu-archived", [0.95, 0.05])

    assert find_portfolio_overlap_clusters(store, min_overlap_score=0.2) == []

    clusters = find_portfolio_overlap_clusters(
        store,
        min_overlap_score=0.2,
        include_archived=True,
    )

    assert len(clusters) == 1
    assert clusters[0].idea_ids == ["bu-archived", "bu-live"]
    assert "embedding_similarity" in {reason.type for reason in clusters[0].overlap_reasons}
