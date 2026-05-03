from __future__ import annotations

import csv
from io import StringIO

from max.spec import generate_observability_plan as exported_generate
from max.spec import render_observability_plan_csv as exported_render_csv
from max.spec import render_observability_plan_markdown as exported_render
from max.spec.observability_plan import (
    OBSERVABILITY_PLAN_SCHEMA_VERSION,
    OBSERVABILITY_PLAN_CSV_COLUMNS,
    generate_observability_plan,
    render_observability_plan_csv,
    render_observability_plan_markdown,
)


def _rich_tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-obs",
            "status": "approved",
            "domain": "developer-tools",
            "category": "agent-safety",
        },
        "project": {
            "title": "Agent Workflow Guard",
            "summary": "CI guardrails for autonomous code changes.",
            "value_proposition": "Reduce risky agent releases before deployment.",
            "target_users": "engineering teams",
            "specific_user": "platform engineer",
            "buyer": "engineering manager",
            "workflow_context": "CI deployment gate for agent-authored pull requests",
        },
        "problem": {
            "statement": "Teams cannot see agent workflow regressions before release.",
            "current_workaround": "Manual review of generated diffs.",
            "why_now": "Agent code changes are increasing.",
        },
        "solution": {
            "approach": "Run workflow fixtures and publish a release gate.",
            "technical_approach": "Python CLI with GitHub check output.",
            "suggested_stack": {"language": "python", "framework": "typer", "ci": "github-actions"},
            "composability_notes": "Keep GitHub integration behind an adapter.",
        },
        "execution": {
            "mvp_scope": ["CLI runner", "GitHub check output"],
            "validation_plan": "Run with three pilot teams using synthetic workflow fixtures.",
            "risks": [
                "GitHub API outages may block release gates",
                "Customer workflow fixtures may include secrets",
            ],
        },
        "evidence": {
            "rationale": "Signals show teams need repeatable pre-release evidence.",
            "insight_ids": ["ins-obs"],
            "signal_ids": ["sig-ci", "sig-risk"],
            "source_idea_ids": ["bu-source"],
        },
        "evaluation": {
            "overall_score": 82.0,
            "recommendation": "yes",
            "strengths": ["Clear buyer and urgent workflow"],
            "weaknesses": ["Integration reliability must be validated"],
            "dimensions": {
                "build_effort": {"value": 6.0, "confidence": 0.7, "reasoning": "Known stack."},
            },
        },
        "acceptance_criteria": {
            "functional_criteria": [
                {"id": "AC-F1", "statement": "CLI completes the release gate workflow."},
                {"id": "AC-F2", "statement": "GitHub check output is published."},
            ],
            "non_functional_criteria": [
                {"id": "AC-NF1", "statement": "Failures are recoverable and documented."}
            ],
        },
    }


def test_generate_observability_plan_is_stable_and_complete_for_rich_tact_spec() -> None:
    first = generate_observability_plan(_rich_tact_spec())
    second = generate_observability_plan(_rich_tact_spec())

    assert first == second
    assert first["schema_version"] == OBSERVABILITY_PLAN_SCHEMA_VERSION
    assert first["kind"] == "max.observability_plan"
    assert first["source"]["idea_id"] == "bu-obs"
    assert first["summary"]["title"] == "Agent Workflow Guard"
    assert first["summary"]["stack"] == "ci=github-actions, framework=typer, language=python"
    assert first["summary"]["acceptance_criteria_count"] == 3
    assert set(first) == {
        "schema_version",
        "kind",
        "source",
        "summary",
        "metrics",
        "events",
        "logs",
        "traces",
        "slos",
        "alerts",
        "dashboards",
        "owners",
        "rollout_validation_checks",
        "evidence_references",
    }
    assert {metric["name"] for metric in first["metrics"]} >= {
        "primary_workflow_success_rate",
        "primary_workflow_latency_p95_ms",
        "qualified_activation_count",
        "acceptance_criteria_pass_rate",
        "open_launch_risk_count",
    }
    assert {event["name"] for event in first["events"]} >= {
        "workflow_started",
        "workflow_completed",
        "workflow_failed",
        "validation_feedback_submitted",
    }
    assert first["logs"]
    assert first["traces"]
    assert first["slos"]
    assert first["alerts"]
    assert first["dashboards"]
    assert first["owners"]
    assert first["rollout_validation_checks"]


def test_generate_observability_plan_handles_sparse_specs_with_fallbacks() -> None:
    plan = generate_observability_plan(
        {
            "schema_version": "tact-spec-preview/v1",
            "kind": "tact.project_spec",
            "source": {"idea_id": "bu-sparse"},
            "project": {"title": ""},
            "solution": {"suggested_stack": {}},
            "execution": {"mvp_scope": [], "risks": []},
            "evidence": {},
            "evaluation": None,
        }
    )

    assert plan["summary"]["title"] == "bu-sparse"
    assert plan["summary"]["workflow_context"] == "primary workflow"
    assert plan["summary"]["stack"] == "unspecified"
    assert plan["evidence_references"] == [
        {
            "id": "spec:fallback",
            "type": "fallback",
            "summary": "No evidence references were provided; observability recommendations use conservative fallback instrumentation.",
        }
    ]
    assert all(item["evidence_reference_ids"] == ["spec:fallback"] for item in plan["metrics"])
    assert any(metric["name"] == "primary_workflow_error_rate" for metric in plan["metrics"])
    assert any(alert["name"] == "High workflow error rate" for alert in plan["alerts"])
    assert not any(metric["name"] == "open_launch_risk_count" for metric in plan["metrics"])


def test_render_observability_plan_markdown_is_deterministic_and_traceable() -> None:
    plan = generate_observability_plan(_rich_tact_spec())

    first = render_observability_plan_markdown(plan)
    second = render_observability_plan_markdown(plan)

    assert first == second
    assert first.startswith("# Agent Workflow Guard Observability Plan")
    assert f"- Schema version: {OBSERVABILITY_PLAN_SCHEMA_VERSION}" in first
    assert "## Metrics" in first
    assert "## Events" in first
    assert "## Logs" in first
    assert "## Traces" in first
    assert "## SLOs" in first
    assert "## Alerts" in first
    assert "## Dashboards" in first
    assert "## Owners" in first
    assert "## Rollout Validation Checks" in first
    assert "## Evidence References" in first
    assert (
        "- Evidence references: `insight:ins-obs`, `signal:sig-ci`, `signal:sig-risk`, `idea:bu-source`, `spec:evidence_rationale`"
        in first
    )
    assert "### signal:sig-ci" in first


def test_render_observability_plan_csv_is_parseable_and_sectioned() -> None:
    plan = generate_observability_plan(_rich_tact_spec())

    csv_output = render_observability_plan_csv(plan)
    rows = list(csv.DictReader(StringIO(csv_output)))

    assert csv.DictReader(StringIO(csv_output)).fieldnames == OBSERVABILITY_PLAN_CSV_COLUMNS
    assert rows
    assert {row["section"] for row in rows} >= {
        "telemetry",
        "dashboards",
        "alerts",
        "ownership",
        "instrumentation_gaps",
        "review_cadence",
    }

    metric = next(row for row in rows if row["item_id"] == "MET1")
    assert metric["section"] == "telemetry"
    assert metric["type"] == "metric"
    assert metric["name"] == "primary_workflow_success_rate"
    assert metric["owner"] == "engineering_owner"
    assert metric["source_idea_id"] == "bu-obs"
    assert metric["title"] == "Agent Workflow Guard"
    assert metric["evidence_references"] == (
        "insight:ins-obs; signal:sig-ci; signal:sig-risk; idea:bu-source; spec:evidence_rationale"
    )

    alert = next(row for row in rows if row["item_id"] == "AL1")
    assert alert["section"] == "alerts"
    assert alert["type"] == "alert"
    assert alert["name"] == "High workflow error rate"
    assert alert["severity"] == "page"
    assert alert["signals"] == "MET3; LOG2"

    dashboard = next(row for row in rows if row["item_id"] == "DB1")
    assert dashboard["section"] == "dashboards"
    assert dashboard["type"] == "dashboard"
    assert dashboard["name"] == "Service Health"
    assert "primary_workflow_latency_p95_ms" in dashboard["panels"]

    owner = next(row for row in rows if row["item_id"] == "OWN2")
    assert owner["section"] == "ownership"
    assert owner["suggested_owner"] == "python / typer service owner"

    gap = next(row for row in rows if row["item_id"] == "RVC1")
    assert gap["section"] == "instrumentation_gaps"
    assert gap["status"] == "pending"
    assert gap["signals"] == "MET1; MET2; MET3; MET4"

    cadence = next(row for row in rows if row["section"] == "review_cadence")
    assert cadence["cadence"] == (
        "Daily during pilot, weekly before rollout expansion, and after every page alert."
    )


def test_observability_plan_source_and_evidence_traceability() -> None:
    plan = generate_observability_plan(_rich_tact_spec())

    assert plan["source"] == {
        "system": "max",
        "type": "idea",
        "idea_id": "bu-obs",
        "status": "approved",
        "domain": "developer-tools",
        "category": "agent-safety",
        "tact_spec_schema_version": "tact-spec-preview/v1",
        "tact_spec_kind": "tact.project_spec",
    }
    assert [reference["id"] for reference in plan["evidence_references"]] == [
        "insight:ins-obs",
        "signal:sig-ci",
        "signal:sig-risk",
        "idea:bu-source",
        "spec:evidence_rationale",
    ]
    assert all("evidence_reference_ids" in metric for metric in plan["metrics"])
    assert (
        "execution.risks"
        in next(metric for metric in plan["metrics"] if metric["id"] == "MET3")["derived_from"]
    )
    assert any(
        check["signal_ids"] == ["MET8", "AL4", "LOG4"]
        for check in plan["rollout_validation_checks"]
    )


def test_observability_plan_is_importable_from_spec_package() -> None:
    plan = exported_generate(_rich_tact_spec())
    markdown = exported_render(plan)
    csv_output = exported_render_csv(plan)

    assert plan["schema_version"] == OBSERVABILITY_PLAN_SCHEMA_VERSION
    assert markdown.startswith("# Agent Workflow Guard Observability Plan")
    assert csv_output.startswith("section,type,source_idea_id")
