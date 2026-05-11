"""Tests for design brief reference customer profiles."""

from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis.design_brief_reference_customer_profile import (
    CSV_COLUMNS,
    SCHEMA_VERSION,
    build_design_brief_reference_customer_profile,
    render_design_brief_reference_customer_profile,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def test_reference_customer_profile_scores_and_sections(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        report = build_design_brief_reference_customer_profile(store, brief_id)
        repeated = build_design_brief_reference_customer_profile(store, brief_id)
    finally:
        store.close()

    assert report == repeated
    assert report is not None
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["summary"]["reference_posture"] == "reference_ready"
    assert report["readiness_score"]["score"] == 90
    assert "reference segment described" in report["readiness_score"]["factors"]
    assert [item["id"] for item in report["ideal_customer_attributes"]] == ["RCA1", "RCA2", "RCA3"]
    assert [item["id"] for item in report["disqualifiers"]] == ["RCD1", "RCD2", "RCD3"]
    assert [item["id"] for item in report["proof_milestones"]] == ["RCM1", "RCM2", "RCM3"]
    assert [item["id"] for item in report["testimonial_prompts"]] == ["RCT1", "RCT2", "RCT3"]

    markdown = render_design_brief_reference_customer_profile(report)
    assert markdown.startswith("# Reference Customer Profile: Reference Customer Brief")
    assert "## Testimonial Prompts" in markdown
    assert json.loads(render_design_brief_reference_customer_profile(report, fmt="json")) == report

    csv_text = render_design_brief_reference_customer_profile(report, fmt="csv")
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert len(rows) == 12
    assert rows[0]["design_brief_id"] == brief_id
    assert rows[0]["section"] == "ideal_customer_attributes"


def test_reference_customer_sparse_profile_needs_evidence(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path, sparse=True)
    try:
        report = build_design_brief_reference_customer_profile(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["summary"]["buyer"] == "economic sponsor"
    assert report["summary"]["reference_posture"] == "needs_more_evidence"
    assert report["readiness_score"]["score"] < 75


def test_reference_customer_missing_and_invalid_format(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_reference.db"), wal_mode=True)
    try:
        assert build_design_brief_reference_customer_profile(store, "dbf-missing") is None
    finally:
        store.close()

    with pytest.raises(ValueError, match="Unsupported reference customer profile format: yaml"):
        render_design_brief_reference_customer_profile({"design_brief": {}, "readiness_score": {}}, fmt="yaml")


def _store_with_brief(tmp_path, *, sparse: bool = False) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / f"reference_{sparse}.db"), wal_mode=True)
    lead = BuildableUnit(
        id="bu-reference-lead" if not sparse else "bu-reference-sparse",
        title="Reference Customer Lead",
        one_liner="Profile reference customers.",
        category="application",
        problem="Teams need customer reference criteria.",
        solution="Generate deterministic reference customer profiles.",
        value_proposition="" if sparse else "Prove launch value with credible customers.",
        specific_user="" if sparse else "implementation manager",
        buyer="" if sparse else "VP of Operations",
        workflow_context="" if sparse else "enterprise rollout review",
        current_workaround="manual customer notes",
        validation_plan="" if sparse else "Confirm measurable rollout value.",
        first_10_customers="" if sparse else "mid-market operations teams with formal rollout motions",
        domain_risks=[] if sparse else ["Reference approval may require legal review."],
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="Reference Customer Brief",
            domain="developer-tools",
            theme="references",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=80.0 if not sparse else 30.0,
            why_this_now="Launch needs proof from credible customers.",
            merged_product_concept="A deterministic reference customer profile.",
            synthesis_rationale="Connects customer fit, disqualifiers, proof, and testimonial prompts.",
            mvp_scope=[] if sparse else ["Profile", "CSV export"],
            first_milestones=[] if sparse else ["Complete pilot proof", "Approve testimonial"],
            validation_plan="" if sparse else "Confirm measurable rollout value.",
            risks=[] if sparse else ["Reference approval may require legal review."],
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )
    return store, brief_id
