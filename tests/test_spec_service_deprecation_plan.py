"""Tests for TactSpec service deprecation plan generation."""

from __future__ import annotations

import csv
from io import StringIO

from max.spec import generate_service_deprecation_plan as exported_generate
from max.spec import render_service_deprecation_plan_csv as exported_render_csv
from max.spec import render_service_deprecation_plan_markdown as exported_render_markdown
from max.spec.service_deprecation_plan import (
    KIND,
    SERVICE_DEPRECATION_PLAN_CSV_COLUMNS,
    SERVICE_DEPRECATION_PLAN_SCHEMA_VERSION,
    generate_service_deprecation_plan,
    render_service_deprecation_plan_csv,
    render_service_deprecation_plan_markdown,
)


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-deprecate",
            "status": "approved",
            "domain": "platform",
            "category": "automation",
        },
        "project": {
            "title": "Legacy Webhook Retirement",
            "summary": "Move webhook delivery to a versioned event router.",
            "specific_user": "integration engineer",
            "buyer": "platform director",
            "workflow_context": "customer webhook delivery",
        },
        "solution": {
            "approach": "Replace direct webhook calls with a versioned event router.",
            "technical_approach": "Python service with versioned event router and adapter layer.",
            "suggested_stack": {"language": "python", "runtime": "workers"},
        },
        "execution": {
            "mvp_scope": ["event router", "legacy adapter", "delivery audit log"],
            "validation_plan": "Replay production fixtures through legacy and replacement delivery paths.",
            "risks": ["Some customers may keep legacy signatures pinned."],
        },
        "evidence": {
            "insight_ids": ["ins-dep"],
            "signal_ids": ["sig-dep"],
            "source_idea_ids": ["idea-parent"],
            "rationale": "Webhook reliability issues require retiring direct delivery.",
        },
        "evaluation": {"overall_score": 81.0, "recommendation": "yes", "weaknesses": []},
    }


def test_generate_service_deprecation_plan_has_stable_shape() -> None:
    first = generate_service_deprecation_plan(_tact_spec())
    second = generate_service_deprecation_plan(_tact_spec())

    assert first == second
    assert first["schema_version"] == SERVICE_DEPRECATION_PLAN_SCHEMA_VERSION
    assert first["kind"] == KIND
    assert first["kind"] == "max.service_deprecation_plan"
    assert first["source"]["idea_id"] == "bu-deprecate"
    assert first["source"]["tact_spec_schema_version"] == "tact-spec-preview/v1"
    assert first["summary"] == {
        "title": "Legacy Webhook Retirement",
        "workflow_context": "customer webhook delivery",
        "target_user": "integration engineer",
        "buyer": "platform director",
        "stack": "language=python, runtime=workers",
        "risk_level": "standard",
        "recommended_timeline": "90-day notice, 30-day parallel run, product rollback review",
        "candidate_count": 4,
        "migration_step_count": 4,
        "rollback_criterion_count": 3,
        "recommendation": "yes",
        "overall_score": 81.0,
    }
    assert set(first) == {
        "schema_version",
        "kind",
        "source",
        "summary",
        "deprecation_candidates",
        "user_impact",
        "compatibility_promises",
        "migration_steps",
        "communications",
        "kill_switches",
        "rollback_criteria",
        "evidence_references",
    }
    assert [item["id"] for item in first["deprecation_candidates"]] == [
        "DEP1",
        "DEP2",
        "DEP3",
        "DEP4",
    ]
    assert [item["id"] for item in first["migration_steps"]] == [
        "MIG1",
        "MIG2",
        "MIG3",
        "MIG4",
    ]
    assert [item["id"] for item in first["rollback_criteria"]] == ["RB1", "RB2", "RB3"]
    assert [reference["id"] for reference in first["evidence_references"]] == [
        "insight:ins-dep",
        "signal:sig-dep",
        "idea:idea-parent",
        "spec:evidence_rationale",
    ]


def test_high_risk_tact_specs_get_conservative_timeline_and_rollback() -> None:
    spec = _tact_spec()
    spec["execution"]["risks"] = [
        "Breaking migration could cause customer downtime.",
        "Compliance reporting depends on legacy delivery audit logs.",
        "Security exception customers need manual review.",
    ]
    spec["evaluation"] = {
        "overall_score": 55.0,
        "recommendation": "hold",
        "weaknesses": ["Legacy customers may block removal."],
    }

    plan = generate_service_deprecation_plan(spec)

    assert plan["summary"]["risk_level"] == "high"
    assert (
        plan["summary"]["recommended_timeline"]
        == "180-day notice, 60-day parallel run, executive rollback review"
    )
    assert plan["compatibility_promises"][0]["promise"].startswith(
        "Maintain existing contracts, redirects, or adapters for 180 days"
    )
    assert plan["kill_switches"][0]["required_before_phase"] == "customer_notice"
    assert plan["rollback_criteria"][0]["threshold"] == (
        "any severity-1 incident or two severity-2 incidents"
    )
    assert "95% acknowledged migration readiness" in plan["rollback_criteria"][1]["threshold"]


def test_sparse_tact_specs_use_defaults_and_fallback_evidence() -> None:
    plan = generate_service_deprecation_plan(
        {
            "schema_version": "tact-spec-preview/v1",
            "kind": "tact.project_spec",
            "source": {"idea_id": "bu-sparse"},
            "project": {"title": ""},
            "solution": {"suggested_stack": {}},
            "execution": {"mvp_scope": [], "risks": []},
            "evaluation": None,
            "evidence": {},
        }
    )

    assert plan["summary"]["title"] == "bu-sparse"
    assert plan["summary"]["workflow_context"] == "primary workflow"
    assert plan["summary"]["target_user"] == "primary user"
    assert plan["summary"]["buyer"] == "launch sponsor"
    assert plan["summary"]["stack"] == "unspecified"
    assert plan["summary"]["risk_level"] == "standard"
    assert [reference["id"] for reference in plan["evidence_references"]] == ["spec:fallback"]
    assert all(
        item["evidence_reference_ids"] == ["spec:fallback"]
        for section in (
            "deprecation_candidates",
            "user_impact",
            "compatibility_promises",
            "migration_steps",
            "communications",
            "kill_switches",
            "rollback_criteria",
        )
        for item in plan[section]
    )


def test_markdown_rendering_is_deterministic_and_readable() -> None:
    plan = generate_service_deprecation_plan(_tact_spec())

    first = render_service_deprecation_plan_markdown(plan)
    second = render_service_deprecation_plan_markdown(plan)

    assert first == second
    assert first.endswith("\n")
    assert first.startswith("# Legacy Webhook Retirement Service Deprecation Plan")
    assert f"- Schema version: {SERVICE_DEPRECATION_PLAN_SCHEMA_VERSION}" in first
    assert "- Kind: max.service_deprecation_plan" in first
    assert "- Risk level: standard" in first
    assert "## Deprecation Candidates" in first
    assert "## User Impact" in first
    assert "## Compatibility Promises" in first
    assert "## Migration Steps" in first
    assert "## Communications" in first
    assert "## Kill Switches" in first
    assert "## Rollback Criteria" in first
    assert "## Evidence References" in first
    assert "### RB1: incident_threshold" in first
    assert "`signal:sig-dep`" in first


def test_csv_rendering_has_stable_header_and_rows() -> None:
    plan = generate_service_deprecation_plan(_tact_spec())

    csv_text = render_service_deprecation_plan_csv(plan)
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert csv_text == render_service_deprecation_plan_csv(plan)
    assert csv_text.endswith("\n")
    assert csv_text.splitlines()[0].split(",") == list(SERVICE_DEPRECATION_PLAN_CSV_COLUMNS)
    assert rows[0] == {
        "section": "summary",
        "type": "summary",
        "source_idea_id": "bu-deprecate",
        "source_status": "approved",
        "tact_spec_schema_version": "tact-spec-preview/v1",
        "title": "Legacy Webhook Retirement",
        "workflow_context": "customer webhook delivery",
        "target_user": "integration engineer",
        "buyer": "platform director",
        "risk_level": "standard",
        "timeline": "90-day notice, 30-day parallel run, product rollback review",
        "item_id": "summary",
        "name": "Legacy Webhook Retirement",
        "owner": "",
        "phase": "",
        "severity": "",
        "description": "90-day notice, 30-day parallel run, product rollback review",
        "action": "",
        "promise": "",
        "trigger": "",
        "threshold": "",
        "derived_from": "",
        "evidence_reference_ids": (
            "insight:ins-dep; signal:sig-dep; idea:idea-parent; spec:evidence_rationale"
        ),
        "evidence_type": "",
        "evidence_summary": "",
    }
    assert [row["item_id"] for row in rows if row["section"] == "deprecation_candidates"] == [
        "DEP1",
        "DEP2",
        "DEP3",
        "DEP4",
    ]
    assert any(
        row["section"] == "migration_steps"
        and row["item_id"] == "MIG2"
        and row["phase"] == "migration"
        and "Python service with versioned event router" in row["action"]
        for row in rows
    )
    assert any(
        row["section"] == "rollback_criteria"
        and row["item_id"] == "RB2"
        and "80% acknowledged migration readiness" in row["threshold"]
        for row in rows
    )
    assert [row["item_id"] for row in rows if row["section"] == "evidence_references"] == [
        "insight:ins-dep",
        "signal:sig-dep",
        "idea:idea-parent",
        "spec:evidence_rationale",
    ]


def test_csv_rendering_handles_missing_optional_fields_with_blanks() -> None:
    csv_text = render_service_deprecation_plan_csv(
        {
            "source": {"idea_id": "bu-partial"},
            "summary": {"title": "Partial Deprecation Plan"},
            "deprecation_candidates": [
                {
                    "id": "DEP1",
                    "description": 'Remove "legacy", comma path\nlater.',
                    "evidence_reference_ids": ["spec:fallback"],
                    "derived_from": {"field": "project.workflow_context", "empty": None},
                }
            ],
            "evidence_references": [{"id": "spec:fallback"}],
        }
    )
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert '"Remove ""legacy"", comma path later."' in csv_text
    assert rows[1]["section"] == "deprecation_candidates"
    assert rows[1]["item_id"] == "DEP1"
    assert rows[1]["owner"] == ""
    assert rows[1]["derived_from"] == "field=project.workflow_context"
    assert rows[-1]["section"] == "evidence_references"
    assert rows[-1]["evidence_reference_ids"] == "spec:fallback"
    assert "None" not in csv_text
    assert "{" not in csv_text


def test_service_deprecation_plan_is_importable_from_spec_package() -> None:
    plan = exported_generate(_tact_spec())
    markdown = exported_render_markdown(plan)
    csv_text = exported_render_csv(plan)

    assert plan["schema_version"] == SERVICE_DEPRECATION_PLAN_SCHEMA_VERSION
    assert markdown.startswith("# Legacy Webhook Retirement Service Deprecation Plan")
    assert csv_text.startswith("section,type,source_idea_id")
