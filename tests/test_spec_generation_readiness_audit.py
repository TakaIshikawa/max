from __future__ import annotations

import csv
import json
from io import StringIO

import pytest

from max.analysis.spec_generation_readiness_audit import (
    KIND,
    SCHEMA_VERSION,
    build_spec_generation_readiness_audit,
    render_spec_generation_readiness_audit,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit


def test_spec_generation_readiness_audit_groups_blocked_warning_and_ready(store: Store) -> None:
    store.insert_buildable_unit(_unit("ready", "Ready", status="approved"))
    store.insert_buildable_unit(_unit("warn", "Warn", status="approved", validation_plan="", domain_risks=[]))
    store.insert_buildable_unit(
        _unit(
            "blocked",
            "Blocked",
            status="approved",
            problem="",
            solution="",
            target_users="both",
            suggested_stack={},
            evidence_signals=[],
            validation_plan="",
            domain_risks=[],
        )
    )
    store.insert_buildable_unit(_unit("draft", "Draft", status="draft", problem=""))

    report = build_spec_generation_readiness_audit(store)
    repeated = build_spec_generation_readiness_audit(store)

    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["summary"] == {
        "approved_unit_count": 3,
        "blocked_count": 1,
        "warning_only_count": 1,
        "ready_count": 1,
        "blocker_count": 5,
        "warning_count": 4,
    }
    assert [row["unit_id"] for row in report["rows"]] == ["blocked", "warn", "ready"]
    blocked = report["rows"][0]
    assert blocked["missing_fields"] == [
        "problem",
        "solution",
        "target_users",
        "suggested_stack",
        "evidence_signals",
        "validation_plan",
        "domain_risks",
    ]
    assert blocked["blocker_count"] == 5
    assert blocked["warning_count"] == 2
    assert blocked["readiness_band"] == "blocked"
    assert blocked["issues"][0] == {
        "field": "problem",
        "severity": "blocker",
        "message": "problem is required before tact spec generation.",
    }


def test_render_spec_generation_readiness_audit_is_stable(store: Store) -> None:
    store.insert_buildable_unit(_unit("ready", "Ready", status="approved"))
    store.insert_buildable_unit(_unit("blocked", "Blocked", status="approved", problem="", evidence_signals=[]))
    report = build_spec_generation_readiness_audit(store)

    assert json.loads(render_spec_generation_readiness_audit(report, fmt="json")) == report

    markdown = render_spec_generation_readiness_audit(report, fmt="markdown")
    assert markdown.startswith("# Spec Generation Readiness Audit")
    assert markdown.index("## Blocked Units") < markdown.index("## Warning-Only Units")
    assert markdown.index("## Warning-Only Units") < markdown.index("## Ready Units")
    assert "| `blocked` | Blocked | problem, evidence_signals | 2 | 0 | blocked |" in markdown
    assert "| `ready` | Ready | none | 0 | 0 | ready |" in markdown

    rendered_csv = render_spec_generation_readiness_audit(report, fmt="csv")
    assert rendered_csv.splitlines()[0] == "unit_id,title,missing_fields,blocker_count,warning_count,readiness_band"
    rows = list(csv.DictReader(StringIO(rendered_csv)))
    assert [row["unit_id"] for row in rows] == ["blocked", "ready"]
    assert rows[0]["missing_fields"] == "problem; evidence_signals"

    with pytest.raises(ValueError, match="Unsupported spec generation readiness audit format: yaml"):
        render_spec_generation_readiness_audit(report, fmt="yaml")


def test_spec_generation_readiness_audit_validates_limit(store: Store) -> None:
    with pytest.raises(ValueError, match="limit must be at least 1"):
        build_spec_generation_readiness_audit(store, limit=0)


def _unit(
    unit_id: str,
    title: str,
    *,
    status: str,
    problem: str = "Clear problem",
    solution: str = "Clear solution",
    target_users: str = "operators",
    suggested_stack: dict[str, str] | None = None,
    evidence_signals: list[str] | None = None,
    validation_plan: str = "Interview users",
    domain_risks: list[str] | None = None,
) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=title,
        one_liner="One line",
        category=BuildableCategory.APPLICATION,
        problem=problem,
        solution=solution,
        target_users=target_users,
        value_proposition="Value",
        validation_plan=validation_plan,
        domain_risks=["risk"] if domain_risks is None else domain_risks,
        inspiring_insights=["ins-1"],
        evidence_signals=["sig-1"] if evidence_signals is None else evidence_signals,
        suggested_stack={"app": "python"} if suggested_stack is None else suggested_stack,
        status=status,
    )
