from __future__ import annotations

from max.spec import generate_operational_runbook as exported_generate
from max.spec import render_operational_runbook_markdown as exported_render
from max.spec.operational_runbook import (
    OPERATIONAL_RUNBOOK_SCHEMA_VERSION,
    generate_operational_runbook,
    render_operational_runbook_markdown,
)


def _rich_tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-runbook",
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
        "solution": {
            "approach": "Run workflow fixtures and publish a release gate.",
            "technical_approach": "Python CLI with GitHub checks, Slack escalation, and Datadog dashboards.",
            "suggested_stack": {
                "language": "python",
                "framework": "typer",
                "ci": "github-actions",
                "observability": "datadog",
            },
        },
        "execution": {
            "mvp_scope": ["CLI runner", "GitHub check output", "Slack notification"],
            "validation_plan": "Run with three pilot teams using synthetic workflow fixtures.",
            "risks": [
                "GitHub API outages may block release gates",
                "Customer workflow fixtures may include secrets",
            ],
        },
        "evaluation": {
            "overall_score": 82.0,
            "recommendation": "yes",
            "weaknesses": ["Integration reliability must be validated"],
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


def test_generate_operational_runbook_is_stable_and_complete_for_rich_tact_spec() -> None:
    first = generate_operational_runbook(_rich_tact_spec())
    second = generate_operational_runbook(_rich_tact_spec())

    assert first == second
    assert first["schema_version"] == OPERATIONAL_RUNBOOK_SCHEMA_VERSION
    assert first["kind"] == "max.operational_runbook"
    assert first["source"]["idea_id"] == "bu-runbook"
    assert first["service_overview"]["title"] == "Agent Workflow Guard"
    assert first["service_overview"]["stack"] == (
        "ci=github-actions, framework=typer, language=python, observability=datadog"
    )
    assert set(first) == {
        "schema_version",
        "kind",
        "source",
        "service_overview",
        "deploy_prerequisites",
        "configuration_env_vars",
        "health_checks",
        "rollback_triggers",
        "incident_triage_steps",
        "observability_checks",
        "support_escalation",
        "post_incident_follow_up",
    }
    assert {item["name"] for item in first["configuration_env_vars"]} >= {
        "SERVICE_ENV",
        "LOG_LEVEL",
        "AGENT_WORKFLOW_GUARD_FEATURE_ENABLED",
        "DATADOG_API_TOKEN",
        "GITHUB_API_TOKEN",
        "SLACK_API_TOKEN",
    }
    assert any(check["id"] == "HC2" for check in first["health_checks"])
    assert any(trigger["id"] == "RB1" for trigger in first["rollback_triggers"])
    assert any(step["id"] == "TRI4" for step in first["incident_triage_steps"])
    assert any(check["id"] == "OBS3" for check in first["observability_checks"])
    assert {item["role"] for item in first["support_escalation"]} >= {
        "product_owner",
        "technical_owner",
        "support_owner",
        "incident_commander",
    }
    assert any(item["id"] == "PIR4" for item in first["post_incident_follow_up"])


def test_generate_operational_runbook_handles_missing_optional_fields() -> None:
    runbook = generate_operational_runbook(
        {
            "schema_version": "tact-spec-preview/v1",
            "kind": "tact.project_spec",
            "source": {"idea_id": "bu-sparse-runbook"},
            "project": {"title": ""},
            "solution": {"suggested_stack": {}},
            "execution": {"mvp_scope": [], "risks": []},
            "evaluation": None,
        }
    )

    assert runbook["service_overview"]["title"] == "bu-sparse-runbook"
    assert runbook["service_overview"]["workflow_context"] == "primary workflow"
    assert runbook["service_overview"]["stack"] == "unspecified"
    assert runbook["configuration_env_vars"] == [
        {
            "id": "ENV1",
            "name": "SERVICE_ENV",
            "description": "Deployment environment name such as staging or production.",
            "required": "required",
            "secret": False,
            "example": "production",
            "derived_from": ["service_overview"],
        },
        {
            "id": "ENV2",
            "name": "LOG_LEVEL",
            "description": "Structured log verbosity for normal operation and incidents.",
            "required": "optional",
            "secret": False,
            "example": "INFO",
            "derived_from": ["observability_checks"],
        },
        {
            "id": "ENV3",
            "name": "BU_SPARSE_RUNBOOK_FEATURE_ENABLED",
            "description": "Feature flag or rollout switch used to pause new exposure quickly.",
            "required": "required",
            "secret": False,
            "example": "false until launch approval",
            "derived_from": ["rollback_triggers"],
        },
    ]
    assert not any(item["id"] == "DEP4" for item in runbook["deploy_prerequisites"])
    assert not any(item["id"] == "PIR4" for item in runbook["post_incident_follow_up"])
    assert any(trigger["name"] == "Primary workflow failure" for trigger in runbook["rollback_triggers"])


def test_render_operational_runbook_markdown_is_deterministic_and_traceable() -> None:
    runbook = generate_operational_runbook(_rich_tact_spec())

    first = render_operational_runbook_markdown(runbook)
    second = render_operational_runbook_markdown(runbook)

    assert first == second
    assert first.startswith("# Agent Workflow Guard Operational Runbook")
    assert f"- Schema version: {OPERATIONAL_RUNBOOK_SCHEMA_VERSION}" in first
    assert "## Service Overview" in first
    assert "## Deploy Prerequisites" in first
    assert "## Configuration and Environment Variables" in first
    assert "## Health Checks" in first
    assert "## Rollback Triggers" in first
    assert "## Incident Triage Steps" in first
    assert "## Observability Checks" in first
    assert "## Support Escalation" in first
    assert "## Post-Incident Follow-Up" in first
    assert "### HC2: Primary workflow readiness" in first
    assert "### RB1: Primary workflow failure" in first
    assert "### ESC4: incident_commander" in first


def test_operational_runbook_is_importable_from_spec_package() -> None:
    runbook = exported_generate(_rich_tact_spec())
    markdown = exported_render(runbook)

    assert runbook["schema_version"] == OPERATIONAL_RUNBOOK_SCHEMA_VERSION
    assert markdown.startswith("# Agent Workflow Guard Operational Runbook")
