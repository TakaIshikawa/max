from __future__ import annotations

import csv
import io
import json

from max.spec import generate_incident_response_plan as exported_generate
from max.spec import render_incident_response_plan_csv as exported_render_csv
from max.spec import render_incident_response_plan_json as exported_render_json
from max.spec import render_incident_response_plan_markdown as exported_render
from max.spec.incident_response_plan import (
    INCIDENT_RESPONSE_PLAN_CSV_COLUMNS,
    INCIDENT_RESPONSE_PLAN_SCHEMA_VERSION,
    generate_incident_response_plan,
    render_incident_response_plan_csv,
    render_incident_response_plan_json,
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


def test_render_incident_response_plan_csv_has_stable_headers_and_operational_rows() -> None:
    plan = generate_incident_response_plan(_security_heavy_tact_spec())

    first = render_incident_response_plan_csv(plan)
    second = render_incident_response_plan_csv(plan)
    reader = csv.DictReader(io.StringIO(first))
    rows = list(reader)

    assert first == second
    assert first.endswith("\n")
    assert reader.fieldnames == list(INCIDENT_RESPONSE_PLAN_CSV_COLUMNS)
    assert first.splitlines()[0] == ",".join(INCIDENT_RESPONSE_PLAN_CSV_COLUMNS)
    assert [row["section"] for row in rows] == [
        *["severity_levels"] * len(plan["severity_levels"]),
        *["incident_classes"] * len(plan["incident_classes"]),
        *["escalation_roles"] * len(plan["escalation_roles"]),
        *["triage_steps"] * len(plan["triage_steps"]),
        *["containment_actions"] * len(plan["containment_actions"]),
        *["communication_checkpoints"] * len(plan["communication_checkpoints"]),
        *["postmortem_requirements"] * len(plan["postmortem_requirements"]),
        *["gaps"] * len(plan["gaps"]),
    ]
    assert {row["section"] for row in rows} >= {
        "severity_levels",
        "incident_classes",
        "escalation_roles",
        "triage_steps",
        "containment_actions",
        "communication_checkpoints",
        "postmortem_requirements",
    }
    assert all(row["source_idea_id"] == "bu-ir-sec" for row in rows)
    assert all(row["title"] == "Renewal Risk Console" for row in rows)

    scenario_row = next(
        row for row in rows if row["section"] == "incident_classes" and row["item_id"] == "INC4"
    )
    assert scenario_row["type"] == "scenario"
    assert scenario_row["category"] == "security_incident"
    assert scenario_row["severity"] == "SEV1"
    assert "OAuth token leak" in scenario_row["trigger"]
    assert scenario_row["detection_signals"] == "execution.risks; evaluation.weaknesses; security_review"
    assert scenario_row["response_refs"] == "TRI4; CON4; COM2"

    response_row = next(
        row for row in rows if row["section"] == "containment_actions" and row["item_id"] == "CON4"
    )
    assert response_row["owner"] == "security_owner"
    assert response_row["incident_class_refs"] == "INC4"
    assert "Rotate affected credentials" in response_row["response_steps"]

    communication_row = next(
        row for row in rows if row["section"] == "communication_checkpoints" and row["item_id"] == "COM5"
    )
    assert communication_row["type"] == "communication"
    assert communication_row["communication_timing"] == (
        "Before external security or privacy statements"
    )
    assert "notification obligations" in communication_row["message_guidance"]

    recovery_row = next(
        row
        for row in rows
        if row["section"] == "postmortem_requirements" and row["item_id"] == "PM5"
    )
    assert recovery_row["type"] == "recovery_criterion"
    assert recovery_row["owner"] == "security_owner"
    assert "credential rotation evidence" in recovery_row["recovery_criteria"]


def test_render_incident_response_plan_csv_escapes_fields_with_punctuation() -> None:
    plan = generate_incident_response_plan(_security_heavy_tact_spec())
    plan["incident_classes"][0]["title"] = 'Workflow, outage "critical"'

    csv_text = render_incident_response_plan_csv(plan)
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    scenario_row = next(
        row for row in rows if row["section"] == "incident_classes" and row["item_id"] == "INC1"
    )

    assert '"Workflow, outage ""critical"""' in csv_text
    assert scenario_row["name"] == 'Workflow, outage "critical"'


def test_render_incident_response_plan_csv_handles_sparse_optional_sections() -> None:
    plan = {
        "source": {"idea_id": "bu-ir-sparse"},
        "summary": {"title": "Sparse IR Plan"},
        "severity_levels": [{"id": "SEV1", "level": "critical"}],
        "incident_classes": None,
        "escalation_roles": [],
        "triage_steps": None,
        "containment_actions": [],
        "communication_checkpoints": None,
        "postmortem_requirements": [],
        "gaps": [{"id": "GAP1", "category": "missing_observability"}],
    }

    rows = list(csv.DictReader(io.StringIO(render_incident_response_plan_csv(plan))))

    assert [row["section"] for row in rows] == ["severity_levels", "gaps"]
    assert rows[0]["source_idea_id"] == "bu-ir-sparse"
    assert rows[0]["title"] == "Sparse IR Plan"
    assert rows[0]["item_id"] == "SEV1"
    assert rows[0]["severity"] == "SEV1"
    assert rows[0]["description"] == ""
    assert rows[1]["type"] == "gap"
    assert rows[1]["category"] == "missing_observability"


def test_render_incident_response_plan_csv_does_not_change_markdown_rendering() -> None:
    plan = generate_incident_response_plan(_operational_heavy_tact_spec())
    before = render_incident_response_plan_markdown(plan)

    csv_text = render_incident_response_plan_csv(plan)
    after = render_incident_response_plan_markdown(plan)

    assert csv_text.startswith(",".join(INCIDENT_RESPONSE_PLAN_CSV_COLUMNS))
    assert after == before
    assert before.startswith("# Agent Workflow Guard Incident Response Plan")


def test_render_incident_response_plan_json_is_stable_parseable_and_complete() -> None:
    plan = generate_incident_response_plan(_security_heavy_tact_spec())

    first = render_incident_response_plan_json(plan)
    second = render_incident_response_plan_json(plan)
    parsed = json.loads(first)

    assert first == second
    assert first.endswith("\n")
    assert not first.endswith("\n\n")
    assert first.splitlines()[1] == '  "communication_checkpoints": ['
    assert parsed == plan
    assert parsed["schema_version"] == INCIDENT_RESPONSE_PLAN_SCHEMA_VERSION
    assert parsed["kind"] == "max.incident_response_plan"
    assert parsed["source"]["idea_id"] == "bu-ir-sec"
    assert any(item["category"] == "security_incident" for item in parsed["incident_classes"])
    assert any(role["role"] == "security_owner" for role in parsed["escalation_roles"])
    assert parsed["triage_steps"][0]["task"]
    assert parsed["containment_actions"][0]["incident_class_refs"]
    assert parsed["communication_checkpoints"][0]["message_guidance"]
    assert parsed["postmortem_requirements"][0]["requirement"]
    assert parsed["evidence_references"] == plan["evidence_references"]


def test_incident_response_plan_is_importable_from_spec_package() -> None:
    plan = exported_generate(_operational_heavy_tact_spec())
    markdown = exported_render(plan)
    csv_text = exported_render_csv(plan)
    json_text = exported_render_json(plan)

    assert plan["schema_version"] == INCIDENT_RESPONSE_PLAN_SCHEMA_VERSION
    assert markdown.startswith("# Agent Workflow Guard Incident Response Plan")
    assert csv_text.startswith(",".join(INCIDENT_RESPONSE_PLAN_CSV_COLUMNS))
    assert json.loads(json_text)["kind"] == "max.incident_response_plan"
