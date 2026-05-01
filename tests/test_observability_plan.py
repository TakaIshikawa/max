from __future__ import annotations

from max.spec import generate_observability_plan as exported_generate
from max.spec import render_observability_plan_markdown as exported_render
from max.spec.observability_plan import (
    OBSERVABILITY_PLAN_SCHEMA_VERSION,
    generate_observability_plan,
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

    assert plan["schema_version"] == OBSERVABILITY_PLAN_SCHEMA_VERSION
    assert markdown.startswith("# Agent Workflow Guard Observability Plan")
