"""Tests for design brief one-pager exports."""

from __future__ import annotations

import csv
import json
from copy import deepcopy
from dataclasses import dataclass
from io import StringIO
from typing import Any

import pytest

from max.analysis.design_brief_one_pager import (
    CSV_COLUMNS,
    SCHEMA_VERSION,
    build_design_brief_one_pager,
    render_design_brief_one_pager,
    render_design_brief_one_pager_csv,
)
from max.types.buildable_unit import BuildableUnit
from max.types.signal import Signal, SignalSourceType


@dataclass
class InMemoryDesignBriefStore:
    design_briefs: dict[str, dict[str, Any]]
    buildable_units: dict[str, BuildableUnit]
    signals: dict[str, Signal]

    def get_design_brief(self, brief_id: str) -> dict[str, Any] | None:
        return self.design_briefs.get(brief_id)

    def get_buildable_unit(self, unit_id: str) -> BuildableUnit | None:
        return self.buildable_units.get(unit_id)

    def get_signal(self, signal_id: str) -> Signal | None:
        return self.signals.get(signal_id)


@pytest.fixture
def one_pager_store() -> tuple[InMemoryDesignBriefStore, str]:
    signals = {
        signal_id: Signal(
            id=signal_id,
            source_type=source_type,
            source_adapter=f"test-{source_type.value}",
            title=title,
            content=f"Evidence for {title}.",
            url=f"https://example.com/{signal_id}",
            tags=[role],
            credibility=0.8,
            metadata={"signal_role": role},
        )
        for signal_id, source_type, role, title in [
            ("sig-one-problem", SignalSourceType.FORUM, "problem", "one-pager problem"),
            ("sig-one-market", SignalSourceType.SURVEY, "market", "one-pager market"),
            ("sig-one-workflow", SignalSourceType.ARTICLE, "workflow", "one-pager workflow"),
        ]
    }
    lead = BuildableUnit(
        id="bu-one-lead",
        title="One-Pager Lead",
        one_liner="Summarize design brief decisions",
        category="application",
        problem="Reviewers need a compact decision artifact.",
        solution="Expose a deterministic one-page summary.",
        value_proposition="Reduce review time before opening the full bundle.",
        specific_user="portfolio reviewer",
        buyer="VP product",
        workflow_context="design brief review",
        current_workaround="manual brief notes",
        why_now="Design brief bundles are already available.",
        validation_plan="Review the one-pager with decision owners.",
        first_10_customers="product leadership teams",
        domain_risks=["Owner alignment may be unclear."],
        evidence_rationale="Signals show review friction.",
        evidence_signals=list(signals),
        tech_approach="Deterministic FastAPI export.",
        suggested_stack={"language": "python"},
        domain="developer-tools",
        status="approved",
    )
    brief_id = "dbf-one-page"
    brief = {
        "id": brief_id,
        "title": "One-Pager Brief",
        "domain": "developer-tools",
        "theme": "decision-summary",
        "readiness_score": 84.0,
        "lead_idea_id": lead.id,
        "buyer": "VP product",
        "specific_user": "portfolio reviewer",
        "workflow_context": "design brief review",
        "why_this_now": "Reviewers need the decision fields before opening the full bundle.",
        "merged_product_concept": "A deterministic one-page design brief summary.",
        "synthesis_rationale": "Condenses problem, solution, evidence, risk, and next step.",
        "mvp_scope": ["One-pager JSON", "One-pager Markdown"],
        "first_milestones": ["Expose one-pager REST export"],
        "validation_plan": "Review the one-pager with decision owners.",
        "risks": ["Owner alignment may be unclear."],
        "source_idea_ids": [lead.id],
        "design_status": "draft",
        "created_at": "2026-04-01T00:00:00+00:00",
        "updated_at": "2026-04-02T00:00:00+00:00",
        "sources": [{"idea_id": lead.id, "role": "lead", "rank": 0}],
    }
    store = InMemoryDesignBriefStore(
        design_briefs={brief_id: brief},
        buildable_units={lead.id: lead},
        signals=signals,
    )
    return store, brief_id


def test_build_design_brief_one_pager_is_stable_for_existing_brief(
    one_pager_store: tuple[InMemoryDesignBriefStore, str],
) -> None:
    store, brief_id = one_pager_store

    one_pager = build_design_brief_one_pager(store, brief_id)  # type: ignore[arg-type]
    repeated = build_design_brief_one_pager(store, brief_id)  # type: ignore[arg-type]

    assert one_pager == repeated
    assert one_pager is not None
    assert one_pager["schema_version"] == SCHEMA_VERSION
    assert one_pager["design_brief"]["id"] == brief_id
    assert one_pager["title"] == "One-Pager Brief"
    assert one_pager["domain"] == "developer-tools"
    assert one_pager["target_customer"] == (
        "Primary user: portfolio reviewer. Buyer or sponsor: VP product."
    )
    assert one_pager["problem"] == "Reviewers need a compact decision artifact."
    assert one_pager["solution"] == "A deterministic one-page design brief summary."
    assert one_pager["evidence_count"] >= 4
    assert one_pager["readiness_score"] == 84.0
    assert one_pager["top_risks"][0]["title"] == "Owner alignment may be unclear"
    assert one_pager["validation_next_step"]
    assert one_pager["first_milestone"] == "Expose one-pager REST export"
    assert one_pager["source_idea_ids"] == ["bu-one-lead"]


def test_build_design_brief_one_pager_missing_brief_returns_none(
    one_pager_store: tuple[InMemoryDesignBriefStore, str],
) -> None:
    store, _brief_id = one_pager_store

    assert build_design_brief_one_pager(store, "dbf-missing") is None  # type: ignore[arg-type]


def test_render_design_brief_one_pager_markdown_has_decision_fields_without_repr(
    one_pager_store: tuple[InMemoryDesignBriefStore, str],
) -> None:
    store, brief_id = one_pager_store
    one_pager = build_design_brief_one_pager(store, brief_id)  # type: ignore[arg-type]
    assert one_pager is not None

    parsed = json.loads(render_design_brief_one_pager(one_pager, fmt="json"))
    assert parsed["schema_version"] == SCHEMA_VERSION

    markdown = render_design_brief_one_pager(one_pager, fmt="markdown")
    assert markdown.startswith("# One-Pager: One-Pager Brief")
    assert "## Decision Fields" in markdown
    assert "**Target customer**: Primary user: portfolio reviewer." in markdown
    assert "**Problem**: Reviewers need a compact decision artifact." in markdown
    assert "**Solution**: A deterministic one-page design brief summary." in markdown
    assert "**Validation next step**:" in markdown
    assert "**First milestone**: Expose one-pager REST export" in markdown
    assert "**Source idea IDs**: bu-one-lead" in markdown
    assert "## Top Risks" in markdown
    assert "Owner alignment may be unclear" in markdown
    assert "{'" not in markdown
    assert "['" not in markdown

    with pytest.raises(ValueError):
        render_design_brief_one_pager(one_pager, fmt="yaml")


def test_render_design_brief_one_pager_csv_has_decision_and_risk_rows(
    one_pager_store: tuple[InMemoryDesignBriefStore, str],
) -> None:
    store, brief_id = one_pager_store
    one_pager = build_design_brief_one_pager(store, brief_id)  # type: ignore[arg-type]
    assert one_pager is not None

    csv_text = render_design_brief_one_pager(one_pager, fmt="csv")
    direct = render_design_brief_one_pager_csv(one_pager)
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert csv_text == direct
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert [row["row_type"] for row in rows[:6]] == ["decision_field"] * 6
    assert [row["field"] for row in rows[:6]] == [
        "Target customer",
        "Problem",
        "Solution",
        "Validation next step",
        "First milestone",
        "Source idea IDs",
    ]
    assert rows[0]["design_brief_id"] == brief_id
    assert rows[0]["design_brief_title"] == "One-Pager Brief"
    assert rows[0]["value"] == "Primary user: portfolio reviewer. Buyer or sponsor: VP product."
    assert rows[0]["source_idea_ids"] == "bu-one-lead"
    assert rows[5]["value"] == "bu-one-lead"

    risk_rows = rows[6:]
    assert risk_rows
    assert {row["row_type"] for row in risk_rows} == {"top_risk"}
    assert risk_rows[0]["field"] == "Owner alignment may be unclear"
    assert risk_rows[0]["value"] == "Owner alignment may be unclear"
    assert risk_rows[0]["risk_id"]
    assert risk_rows[0]["severity"] == "high"
    assert risk_rows[0]["likelihood"] == "possible"
    assert risk_rows[0]["priority"] == "1"
    assert risk_rows[0]["mitigation"]
    assert risk_rows[0]["validation_action"]
    assert risk_rows[0]["source_idea_ids"] == "bu-one-lead"


def test_render_design_brief_one_pager_csv_without_risks_keeps_decision_rows(
    one_pager_store: tuple[InMemoryDesignBriefStore, str],
) -> None:
    store, brief_id = one_pager_store
    one_pager = build_design_brief_one_pager(store, brief_id)  # type: ignore[arg-type]
    assert one_pager is not None
    no_risk_one_pager = deepcopy(one_pager)
    no_risk_one_pager["top_risks"] = []

    csv_text = render_design_brief_one_pager(no_risk_one_pager, fmt="csv")
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert len(rows) == 6
    assert {row["row_type"] for row in rows} == {"decision_field"}
    assert all(row["design_brief_id"] == brief_id for row in rows)
    assert all(row["risk_id"] == "" for row in rows)


def test_render_design_brief_one_pager_csv_is_deterministic(
    one_pager_store: tuple[InMemoryDesignBriefStore, str],
) -> None:
    store, brief_id = one_pager_store
    one_pager = build_design_brief_one_pager(store, brief_id)  # type: ignore[arg-type]
    assert one_pager is not None

    assert render_design_brief_one_pager(one_pager, fmt="csv") == render_design_brief_one_pager(
        one_pager,
        fmt="csv",
    )


def test_render_design_brief_one_pager_csv_escapes_long_text(
    one_pager_store: tuple[InMemoryDesignBriefStore, str],
) -> None:
    store, brief_id = one_pager_store
    one_pager = build_design_brief_one_pager(store, brief_id)  # type: ignore[arg-type]
    assert one_pager is not None
    escaped_one_pager = deepcopy(one_pager)
    escaped_one_pager["problem"] = (
        'Review "portfolio", owner, and sponsor decisions\n'
        "before the full design brief bundle is opened by the review group."
    )
    escaped_one_pager["top_risks"][0]["mitigation"] = (
        'Assign an "owner", reviewer, and fallback\nbefore kickoff.'
    )

    csv_text = render_design_brief_one_pager(escaped_one_pager, fmt="csv")
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert '"Review ""portfolio"", owner, and sponsor decisions' in csv_text
    assert '"Assign an ""owner"", reviewer, and fallback' in csv_text
    assert rows[1]["value"] == escaped_one_pager["problem"]
    assert rows[6]["mitigation"] == escaped_one_pager["top_risks"][0]["mitigation"]
