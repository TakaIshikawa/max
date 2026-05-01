from __future__ import annotations

from max.spec import generate_incident_response_plan as exported_generate
from max.spec import render_incident_response_plan_markdown as exported_render
from max.spec.incident_response_plan import (
    INCIDENT_RESPONSE_PLAN_SCHEMA_VERSION,
    generate_incident_response_plan,
    render_incident_response_plan_markdown,
)


def _security_heavy_tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-ir-sec",
            "status": "approved",
            "domain": "customer-success",
            "category": "application",
        },
        "project": {
            "title": "Renewal Risk Console",
            "summary": "Coordinate renewal escalations across Salesforce and Slack.",
            "target_users": "customer success teams",
            "specific_user": "customer success operator",
            "buyer": "customer success director",
            "workflow_context": "Salesforce account review to Slack renewal alert",
        },
        "problem": {
            "statement": "Teams copy customer account data into Slack without audit review.",
            "current_workaround": "Manual Salesforce exports with customer emails.",
        },
        "solution": {
            "technical_approach": (
                "FastAPI webhook API with OAuth, SSO, scoped tokens, RBAC roles, "
                "audit logs, rate limits, and encrypted secret storage."
            ),
            "suggested_stack": {
                "backend": "FastAPI",
                "crm": "Salesforce",
                "messaging": "Slack",
                "auth": "OAuth",
                "database": "Postgres",
            },
        },
        "execution": {
            "validation_plan": "Run OAuth sandbox sync and audit log review.",
            "risks": [
                "Customer data exposure from Slack misrouting may require notification.",
                "OAuth token leak or webhook signature bypass could allow unauthorized access.",
            ],
        },
        "evaluation": {
            "weaknesses": ["Security and privacy review is required before production data access."],
        },
        "acceptance_criteria": {
            "functional_criteria": [{"id": "AC-F1", "statement": "Operator can send a Slack alert."}],
            "non_functional_criteria": [
                {"id": "AC-NF1", "statement": "Secrets are redacted from logs."}
            ],
        },
        "evidence": {
            "insight_ids": ["ins-security"],
            "signal_ids": ["sig-renewal-risk"],
            "source_idea_ids": ["src-support"],
        },
    }


def _operational_heavy_tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {"idea_id": "bu-ir-ops", "status": "pilot"},
        "project": {
            "title": "Agent Workflow Guard",
            "target_users": "platform teams",
            "specific_user": "platform engineer",
            "buyer": "engineering manager",
            "workflow_context": "CI deployment gate for agent-authored pull requests",
        },
        "solution": {
            "technical_approach": "Python CLI with GitHub checks, Slack escalation, and Datadog dashboards.",
            "suggested_stack": {
                "language": "python",
                "framework": "typer",
                "ci": "github-actions",
                "observability": "datadog",
            },
        },
        "execution": {
            "validation_plan": "Run synthetic workflow fixtures against GitHub and Datadog.",
            "risks": [
                "GitHub API outage may block release gates.",
                "Datadog alert latency may delay rollback during SLO breaches.",
                "Dependency timeouts could leave jobs queued.",
            ],
        },
        "evaluation": {"weaknesses": ["Integration reliability must be validated."]},
        "acceptance_criteria": {
            "functional_criteria": [{"id": "AC-F1", "statement": "GitHub check output is published."}]
        },
        "evidence": {"signal_ids": ["sig-release-gates"]},
    }


def test_generate_incident_response_plan_reflects_security_risks() -> None:
    first = generate_incident_response_plan(_security_heavy_tact_spec())
    second = generate_incident_response_plan(_security_heavy_tact_spec())

    assert first == second
    assert first["schema_version"] == INCIDENT_RESPONSE_PLAN_SCHEMA_VERSION
    assert first["kind"] == "max.incident_response_plan"
    assert first["source"]["idea_id"] == "bu-ir-sec"
    assert first["source"]["evidence_reference_count"] == 3
    assert first["summary"]["title"] == "Renewal Risk Console"
    assert first["summary"]["security_risk_count"] >= 2
    assert set(first) == {
        "schema_version",
        "kind",
        "source",
        "summary",
        "incident_context",
        "severity_levels",
        "incident_classes",
        "escalation_roles",
        "triage_steps",
        "containment_actions",
        "communication_checkpoints",
        "postmortem_requirements",
        "evidence_references",
        "gaps",
    }
    assert {item["category"] for item in first["incident_classes"]} >= {
        "security_incident",
        "data_integrity",
        "dependency_failure",
    }
    security_class = next(
        item for item in first["incident_classes"] if item["category"] == "security_incident"
    )
    assert security_class["default_severity"] == "SEV1"
    assert "OAuth token leak" in security_class["trigger"]
    assert any(role["role"] == "security_owner" for role in first["escalation_roles"])
    assert any(action["category"] == "secure_access" for action in first["containment_actions"])
    assert any(checkpoint["id"] == "COM5" for checkpoint in first["communication_checkpoints"])
    assert any(req["category"] == "security_evidence" for req in first["postmortem_requirements"])
    assert first["gaps"] == []


def test_generate_incident_response_plan_reflects_operational_risks() -> None:
    plan = generate_incident_response_plan(_operational_heavy_tact_spec())

    assert plan["summary"]["operational_risk_count"] >= 3
    assert plan["incident_context"]["integrations"] == ["Datadog", "GitHub", "Slack"]
    assert {item["category"] for item in plan["incident_classes"]} >= {
        "operational_degradation",
        "dependency_failure",
        "workflow_outage",
    }
    operational_class = next(
        item for item in plan["incident_classes"] if item["category"] == "operational_degradation"
    )
    assert operational_class["default_severity"] == "SEV2"
    assert "GitHub API outage" in operational_class["trigger"]
    assert any(action["category"] == "degrade_dependency" for action in plan["containment_actions"])
    assert not any(role["role"] == "security_owner" for role in plan["escalation_roles"])
    assert plan["gaps"] == []


def test_generate_incident_response_plan_handles_minimal_idea_inputs_with_gaps() -> None:
    plan = generate_incident_response_plan(
        {
            "schema_version": "tact-spec-preview/v1",
            "kind": "tact.project_spec",
            "source": {"idea_id": "bu-ir-min"},
            "project": {"title": ""},
            "solution": {"suggested_stack": {}},
            "execution": {"risks": []},
            "evaluation": None,
        }
    )

    assert plan["summary"]["title"] == "bu-ir-min"
    assert plan["summary"]["workflow_context"] == "primary workflow"
    assert plan["summary"]["stack"] == "unspecified"
    assert plan["summary"]["risk_count"] == 0
    assert [item["category"] for item in plan["incident_classes"]] == [
        "workflow_outage",
        "data_integrity",
        "dependency_failure",
    ]
    assert {gap["category"] for gap in plan["gaps"]} >= {
        "missing_validation_plan",
        "missing_acceptance_criteria",
        "missing_observability",
        "missing_evidence_references",
    }


def test_render_incident_response_plan_markdown_is_stable_and_traceable() -> None:
    plan = generate_incident_response_plan(_security_heavy_tact_spec())

    first = render_incident_response_plan_markdown(plan)
    second = render_incident_response_plan_markdown(plan)

    assert first == second
    assert first.startswith("# Renewal Risk Console Incident Response Plan")
    assert f"- Schema version: {INCIDENT_RESPONSE_PLAN_SCHEMA_VERSION}" in first
    assert "- Source idea ID: bu-ir-sec" in first
    assert "- Evidence references: 3" in first
    assert "## Severity Levels" in first
    assert "## Incident Classes" in first
    assert "## Escalation Roles" in first
    assert "## Triage Steps" in first
    assert "## Containment Actions" in first
    assert "## Customer Communication Checkpoints" in first
    assert "## Postmortem Requirements" in first
    assert "## Evidence References" in first
    assert "## Gaps" in first
    assert "### INC4: Security, credential, or access incident" in first
    assert "`insight:ins-security`" in first
    assert "None." in first


def test_incident_response_plan_is_importable_from_spec_package() -> None:
    plan = exported_generate(_operational_heavy_tact_spec())
    markdown = exported_render(plan)

    assert plan["schema_version"] == INCIDENT_RESPONSE_PLAN_SCHEMA_VERSION
    assert markdown.startswith("# Agent Workflow Guard Incident Response Plan")
