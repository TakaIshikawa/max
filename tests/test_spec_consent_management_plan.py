"""Tests for TactSpec consent management plan generation."""

from __future__ import annotations

import csv
import json
from io import StringIO

from max.spec import generate_consent_management_plan as exported_generate
from max.spec import render_consent_management_plan_csv as exported_render_csv
from max.spec import render_consent_management_plan_markdown as exported_render
from max.spec.consent_management_plan import (
    CSV_COLUMNS,
    KIND,
    SCHEMA_VERSION,
    generate_consent_management_plan,
    render_consent_management_plan_csv,
    render_consent_management_plan_markdown,
)


def _rich_tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-consent",
            "status": "approved",
            "domain": "healthcare",
            "category": "automation",
        },
        "project": {
            "title": "Patient Follow-Up Consent Hub",
            "summary": "Coordinate patient reminders with clear consent.",
            "target_users": "clinic operations teams",
            "specific_user": "clinic coordinator",
            "buyer": "clinic operations director",
            "workflow_context": "patient intake to reminder workflow",
        },
        "solution": {
            "approach": "Collect consent, export reminder reports, and route opt-out requests.",
            "technical_approach": (
                "FastAPI webhook service stores patient email consent, OAuth tokens, audit logs, "
                "OpenAI prompt summaries, Slack notifications, and CSV exports."
            ),
            "suggested_stack": {
                "backend": "FastAPI",
                "database": "Postgres",
                "ai": "OpenAI",
                "messaging": "Slack",
                "crm": "Salesforce",
                "auth": "OAuth",
            },
        },
        "execution": {
            "mvp_scope": [
                "Patient opt-in collection",
                "Slack reminder notifications",
                "CSV export for follow-up reports",
            ],
            "validation_plan": "Use de-identified fixtures and delete pilot consent events after validation.",
            "risks": [
                "Patient consent withdrawal and deletion rules may block launch.",
                "Slack notification payloads could expose patient information.",
            ],
        },
        "evidence": {
            "rationale": "Clinic interviews requested clearer consent evidence.",
            "insight_ids": ["ins-consent"],
            "signal_ids": ["sig-consent"],
            "source_idea_ids": ["idea-consent"],
        },
        "evaluation": {"overall_score": 81, "recommendation": "yes"},
    }


def test_generate_consent_management_plan_has_stable_shape_and_evidence() -> None:
    first = generate_consent_management_plan(_rich_tact_spec())
    second = generate_consent_management_plan(_rich_tact_spec())

    assert first == second
    assert json.loads(json.dumps(first)) == first
    assert first["schema_version"] == SCHEMA_VERSION
    assert first["kind"] == KIND
    assert first["source"]["idea_id"] == "bu-consent"
    assert first["source"]["tact_spec_schema_version"] == "tact-spec-preview/v1"
    assert first["summary"]["title"] == "Patient Follow-Up Consent Hub"
    assert first["summary"]["consent_gate"] == "privacy_review_required"
    assert set(first) == {
        "schema_version",
        "kind",
        "source",
        "summary",
        "consent_surfaces",
        "user_controls",
        "audit_events",
        "retention_notes",
        "owner_actions",
        "evidence_references",
    }

    surface_ids = [surface["surface_id"] for surface in first["consent_surfaces"]]
    assert surface_ids == [
        "account_profile",
        "data_import",
        "integration_authorization",
        "ai_processing",
        "analytics_tracking",
        "communications",
        "exports_and_sharing",
        "regulated_data_notice",
    ]
    assert first["consent_surfaces"][0]["id"] == "CS01"
    assert any(control["name"] == "Integration disconnect control" for control in first["user_controls"])
    assert any(event["event_name"] == "external_consent_scope_changed" for event in first["audit_events"])
    assert any(note["topic"] == "Downstream vendor copies" for note in first["retention_notes"])
    assert [ref["id"] for ref in first["evidence_references"]] == [
        "signal:sig-consent",
        "insight:ins-consent",
        "source_idea:idea-consent",
        "evidence.rationale",
        "source_idea:bu-consent",
        "evaluation",
    ]


def test_sparse_tact_spec_produces_sensible_defaults() -> None:
    plan = generate_consent_management_plan(
        {
            "schema_version": "tact-spec-preview/v1",
            "kind": "tact.project_spec",
            "source": {"idea_id": "bu-sparse-consent"},
            "project": {"title": ""},
            "solution": {"suggested_stack": {}},
            "execution": {"mvp_scope": [], "risks": []},
        }
    )

    assert plan["summary"]["title"] == "bu-sparse-consent"
    assert plan["summary"]["workflow_context"] == "primary workflow"
    assert plan["summary"]["target_user"] == "primary user"
    assert plan["summary"]["buyer"] == "launch sponsor"
    assert plan["summary"]["consent_gate"] == "consent_requirements_needed"
    assert [surface["surface_id"] for surface in plan["consent_surfaces"]] == [
        "core_workflow_consent"
    ]
    assert plan["consent_surfaces"][0]["owner"] == "product_owner"
    assert any(action["id"] == "OA04" for action in plan["owner_actions"])
    assert [ref["id"] for ref in plan["evidence_references"]] == ["source_idea:bu-sparse-consent"]


def test_render_consent_management_plan_markdown_is_deterministic() -> None:
    plan = generate_consent_management_plan(_rich_tact_spec())

    first = render_consent_management_plan_markdown(plan)
    second = render_consent_management_plan_markdown(plan)

    assert first == second
    assert first.startswith("# Patient Follow-Up Consent Hub Consent Management Plan")
    assert f"- Schema version: {SCHEMA_VERSION}" in first
    assert "- Consent gate: privacy_review_required" in first
    for heading in [
        "## Consent Surfaces",
        "## User Controls",
        "## Audit Events",
        "## Retention Notes",
        "## Owner Actions",
        "## Evidence References",
    ]:
        assert heading in first
    assert "### CS03: Third-party integration authorization" in first
    assert "source_idea:bu-consent" in first


def test_render_consent_management_plan_csv_is_parseable_and_stable() -> None:
    plan = generate_consent_management_plan(_rich_tact_spec())

    first = render_consent_management_plan_csv(plan)
    second = render_consent_management_plan_csv(plan)
    rows = list(csv.DictReader(StringIO(first)))

    assert first == second
    assert first.endswith("\n")
    assert csv.DictReader(StringIO(first)).fieldnames == list(CSV_COLUMNS)
    assert rows[0]["schema_version"] == SCHEMA_VERSION
    assert rows[0]["kind"] == KIND
    assert rows[0]["source_idea_id"] == "bu-consent"
    assert rows[0]["title"] == "Patient Follow-Up Consent Hub"
    assert rows[0]["section"] == "consent_surfaces"
    assert rows[0]["item_id"] == "CS01"
    assert rows[0]["name"] == "Account and profile collection"
    assert "signal:sig-consent" in rows[0]["evidence_references"]
    assert any(row["section"] == "evidence_references" and row["item_id"] == "evaluation" for row in rows)


def test_render_consent_management_plan_csv_handles_empty_plan() -> None:
    assert render_consent_management_plan_csv({}) == ",".join(CSV_COLUMNS) + "\n"


def test_consent_management_plan_is_importable_from_spec_package() -> None:
    plan = exported_generate(_rich_tact_spec())
    markdown = exported_render(plan)
    csv_text = exported_render_csv(plan)

    assert plan["schema_version"] == SCHEMA_VERSION
    assert markdown.startswith("# Patient Follow-Up Consent Hub Consent Management Plan")
    assert csv_text.startswith(",".join(CSV_COLUMNS))
