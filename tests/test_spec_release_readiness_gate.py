from __future__ import annotations

import csv
import io
import json

from max.spec import generate_release_readiness_gate as exported_generate
from max.spec import render_release_readiness_gate_csv as exported_render_csv
from max.spec import render_release_readiness_gate_json as exported_render_json
from max.spec import render_release_readiness_gate_markdown as exported_render
from max.spec.release_readiness_gate import (
    RELEASE_READINESS_GATE_CSV_COLUMNS,
    RELEASE_READINESS_GATE_SCHEMA_VERSION,
    generate_release_readiness_gate,
    render_release_readiness_gate_csv,
    render_release_readiness_gate_json,
    render_release_readiness_gate_markdown,
)


def _complete_tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-release-gate",
            "status": "approved",
            "domain": "developer-tools",
            "category": "agent-safety",
        },
        "project": {
            "title": "Agent Release Gate",
            "summary": "Final release decisioning for generated agent projects.",
            "value_proposition": "Reduce handoff risk before execution agents start work.",
            "target_users": "engineering teams",
            "specific_user": "platform engineer",
            "buyer": "engineering manager",
            "workflow_context": "release approval for generated TactSpec projects",
        },
        "solution": {
            "approach": "Summarize release evidence and required signoffs.",
            "technical_approach": "Python CLI generates a deterministic Markdown gate from TactSpec artifacts.",
            "suggested_stack": {
                "language": "python",
                "framework": "typer",
                "ci": "github-actions",
            },
        },
        "execution": {
            "mvp_scope": ["Read TactSpec artifacts", "Produce go/no-go decision"],
            "first_10_customers": "three pilot platform teams",
            "validation_plan": "Run the gate against approved and incomplete TactSpec fixtures.",
            "risks": ["Missing artifact evidence may create false release confidence"],
        },
        "evidence": {
            "rationale": "Spec consumers need deterministic final checks.",
            "insight_ids": ["insight-1"],
            "signal_ids": ["signal-1"],
            "source_idea_ids": ["source-1"],
        },
        "evaluation": {
            "overall_score": 86.0,
            "recommendation": "yes",
            "weaknesses": [],
        },
        "acceptance_criteria": {
            "functional_criteria": [
                {"id": "AC-F1", "statement": "Gate returns go for complete evidence."},
                {"id": "AC-F2", "statement": "Gate returns no-go for missing release evidence."},
            ],
            "non_functional_criteria": [
                {"id": "AC-NF1", "statement": "Markdown output is deterministic."}
            ],
        },
        "artifacts": {
            "security_review": {
                "summary": {"finding_count": 1, "high_or_critical_finding_count": 0},
                "findings": [{"id": "SEC-F1", "severity": "low"}],
            },
            "observability_plan": {
                "metrics": [{"id": "MET1", "name": "primary_workflow_success_rate"}],
                "alerts": [{"id": "ALT1", "name": "primary workflow failure"}],
            },
            "rollback_plan": {
                "rollback_triggers": [{"id": "RB1", "name": "primary workflow failure"}],
            },
            "support_playbook": {
                "support_scenarios": [{"id": "SC1", "name": "user cannot complete workflow"}],
            },
            "launch_checklist": {
                "checklist_items": [{"id": "LC1", "task": "run validation"}],
            },
            "stakeholder_handoff": {"summary": {"title": "Agent Release Gate"}},
        },
    }


def test_generate_release_readiness_gate_is_stable_go_for_complete_tact_spec() -> None:
    first = generate_release_readiness_gate(_complete_tact_spec())
    second = generate_release_readiness_gate(_complete_tact_spec())

    assert first == second
    assert first["schema_version"] == RELEASE_READINESS_GATE_SCHEMA_VERSION
    assert first["kind"] == "max.release_readiness_gate"
    assert first["summary"]["decision"] == "go"
    assert first["summary"]["go"] is True
    assert first["summary"]["ready_dimension_count"] == 7
    assert first["blockers"] == []
    assert [dimension["id"] for dimension in first["readiness_dimensions"]] == [
        "scope",
        "implementation",
        "security",
        "observability",
        "rollback",
        "support",
        "launch_evidence",
    ]
    assert all(dimension["status"] == "ready" for dimension in first["readiness_dimensions"])
    assert {signoff["role"] for signoff in first["required_signoffs"]} == {
        "product_owner",
        "technical_owner",
        "security_owner",
        "operations_owner",
        "support_owner",
        "launch_owner",
    }
    assert all(signoff["status"] == "pending" for signoff in first["required_signoffs"])


def test_generate_release_readiness_gate_is_actionable_no_go_for_incomplete_tact_spec() -> None:
    gate = generate_release_readiness_gate(
        {
            "schema_version": "tact-spec-preview/v1",
            "kind": "tact.project_spec",
            "source": {"idea_id": "bu-incomplete-gate"},
            "project": {"title": "Thin Spec"},
            "solution": {"suggested_stack": {}},
            "execution": {},
            "evaluation": {"recommendation": "no", "overall_score": 31.0},
        }
    )

    assert gate["summary"]["decision"] == "no-go"
    assert gate["summary"]["go"] is False
    assert gate["summary"]["workflow_context"] == "primary workflow"
    assert gate["summary"]["target_user"] == "primary user"
    assert gate["summary"]["blocker_count"] >= 7
    assert {blocker["dimension_id"] for blocker in gate["blockers"]} >= {
        "scope",
        "implementation",
        "security",
        "observability",
        "rollback",
        "support",
        "launch_evidence",
    }
    assert any("evaluation.recommendation" in blocker["missing_evidence"] for blocker in gate["blockers"])
    assert any(
        signoff["role"] == "launch_owner" and signoff["status"] == "blocked"
        for signoff in gate["required_signoffs"]
    )


def test_render_release_readiness_gate_markdown_lists_dimensions_blockers_and_signoffs() -> None:
    gate = generate_release_readiness_gate(_complete_tact_spec())

    first = render_release_readiness_gate_markdown(gate)
    second = render_release_readiness_gate_markdown(gate)

    assert first == second
    assert first.startswith("# Agent Release Gate Release Readiness Gate")
    assert f"- Schema version: {RELEASE_READINESS_GATE_SCHEMA_VERSION}" in first
    assert "- Decision: go" in first
    assert "## Readiness Dimensions" in first
    assert "### scope: Scope" in first
    assert "### launch_evidence: Launch Evidence" in first
    assert "## Blockers" in first
    assert "None." in first
    assert "## Required Signoffs" in first
    assert "### SO6: launch_owner" in first


def test_render_release_readiness_gate_csv_lists_summary_and_check_rows() -> None:
    gate = generate_release_readiness_gate(_complete_tact_spec())

    first = render_release_readiness_gate_csv(gate)
    second = render_release_readiness_gate_csv(gate)
    reader = csv.DictReader(io.StringIO(first))
    rows = list(reader)

    assert first == second
    assert reader.fieldnames == list(RELEASE_READINESS_GATE_CSV_COLUMNS)
    assert first.splitlines()[0] == ",".join(RELEASE_READINESS_GATE_CSV_COLUMNS)

    summary_row = rows[0]
    assert summary_row["section"] == "summary"
    assert summary_row["type"] == "gate"
    assert summary_row["source_idea_id"] == "bu-release-gate"
    assert summary_row["title"] == "Agent Release Gate"
    assert summary_row["decision"] == "go"
    assert summary_row["go"] == "true"
    assert summary_row["workflow_context"] == "release approval for generated TactSpec projects"

    scope_row = next(row for row in rows if row["section"] == "readiness" and row["item_id"] == "scope")
    assert scope_row["type"] == "check"
    assert scope_row["dimension_id"] == "scope"
    assert scope_row["name"] == "Scope"
    assert scope_row["status"] == "ready"
    assert scope_row["required"] == "true"
    assert scope_row["owner"] == "product_owner"
    assert "project.workflow_context=release approval for generated TactSpec projects" in scope_row["evidence"]

    assert [row["type"] for row in rows] == ["gate"] + ["check"] * 7
    assert summary_row["name"] == "Agent Release Gate"
    assert summary_row["owner"] == "launch_owner"
    assert summary_row["blocker_risk"] == ""
    assert summary_row["next_action"] == (
        "Record final go/no-go decision with all required owner signoffs."
    )


def test_render_release_readiness_gate_csv_includes_blocker_rows_for_no_go() -> None:
    gate = generate_release_readiness_gate({})
    rows = list(csv.DictReader(io.StringIO(render_release_readiness_gate_csv(gate))))

    assert len(rows) == 8
    assert rows[0]["type"] == "gate"
    assert rows[0]["status"] == "no-go"
    assert rows[0]["blocker_risk"]
    assert rows[0]["next_action"] == (
        "Resolve release blockers before recording the final go/no-go decision."
    )

    blocker_row = next(row for row in rows if row["type"] == "check" and row["status"] == "blocked")
    assert blocker_row["owner"]
    assert blocker_row["blocker_risk"]
    assert blocker_row["next_action"]


def test_render_release_readiness_gate_json_is_stable_parseable_and_complete() -> None:
    gate = generate_release_readiness_gate(_complete_tact_spec())

    first = render_release_readiness_gate_json(gate)
    second = render_release_readiness_gate_json(gate)
    parsed = json.loads(first)

    assert first == second
    assert first.endswith("\n")
    assert not first.endswith("\n\n")
    assert first.splitlines()[1] == '  "blockers": [],'
    assert parsed == gate
    assert parsed["schema_version"] == RELEASE_READINESS_GATE_SCHEMA_VERSION
    assert parsed["kind"] == "max.release_readiness_gate"
    assert parsed["source"]["idea_id"] == "bu-release-gate"
    assert parsed["summary"]["decision"] == "go"
    assert parsed["summary"]["go"] is True
    assert [dimension["id"] for dimension in parsed["readiness_dimensions"]] == [
        "scope",
        "implementation",
        "security",
        "observability",
        "rollback",
        "support",
        "launch_evidence",
    ]
    assert parsed["blockers"] == []
    assert {signoff["role"] for signoff in parsed["required_signoffs"]} >= {
        "product_owner",
        "launch_owner",
    }


def test_release_readiness_gate_handles_missing_optional_fields() -> None:
    gate = generate_release_readiness_gate({})
    markdown = render_release_readiness_gate_markdown(gate)

    assert gate["source"]["system"] == "max"
    assert gate["source"]["type"] == "tact_spec_preview"
    assert gate["summary"]["title"] == "Untitled TactSpec"
    assert gate["summary"]["decision"] == "no-go"
    assert len(gate["readiness_dimensions"]) == 7
    assert len(gate["required_signoffs"]) == 6
    assert "# Untitled TactSpec Release Readiness Gate" in markdown


def test_release_readiness_gate_is_importable_from_spec_package() -> None:
    gate = exported_generate(_complete_tact_spec())
    markdown = exported_render(gate)
    csv_text = exported_render_csv(gate)
    json_text = exported_render_json(gate)

    assert gate["schema_version"] == RELEASE_READINESS_GATE_SCHEMA_VERSION
    assert markdown.startswith("# Agent Release Gate Release Readiness Gate")
    assert csv_text.startswith(",".join(RELEASE_READINESS_GATE_CSV_COLUMNS))
    assert json.loads(json_text)["kind"] == "max.release_readiness_gate"
