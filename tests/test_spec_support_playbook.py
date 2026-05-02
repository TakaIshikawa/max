"""Tests for TactSpec support playbook generation."""

from __future__ import annotations

import json
import csv
import io

from max.spec import generate_support_playbook as exported_generate
from max.spec import render_support_playbook_csv as exported_render_csv
from max.spec import render_support_playbook_markdown as exported_render
from max.spec.generator import generate_spec_preview
from max.spec.support_playbook import (
    CSV_COLUMNS,
    SUPPORT_PLAYBOOK_SCHEMA_VERSION,
    generate_support_playbook,
    render_support_playbook_csv,
    render_support_playbook_markdown,
)


def test_generate_support_playbook_has_stable_schema_shape(sample_unit, sample_evaluation) -> None:
    spec = generate_spec_preview(sample_unit, sample_evaluation)

    first = generate_support_playbook(sample_unit, sample_evaluation, spec)
    second = generate_support_playbook(sample_unit, sample_evaluation, spec)

    assert first == second
    assert first["schema_version"] == SUPPORT_PLAYBOOK_SCHEMA_VERSION
    assert first["kind"] == "max.support_playbook"
    assert first["idea_id"] == "bu-test001"
    assert first["source"]["tact_spec_schema_version"] == "tact-spec-preview/v1"
    assert first["idea_summary"] == {
        "title": "MCP Test Framework",
        "one_liner": "Standardized testing for MCP servers",
        "target_user": "MCP server maintainer",
        "buyer": "developer platform lead",
        "workflow_context": "pre-release CI validation",
        "primary_scope": "A CLI tool that validates MCP server implementations",
        "current_workaround": "manual protocol testing",
        "validation_plan": "run against five open-source MCP servers",
        "recommendation": "yes",
        "overall_score": 78.0,
        "support_goal": "Help MCP server maintainer complete pre-release CI validation.",
    }
    assert set(first) == {
        "schema_version",
        "kind",
        "idea_id",
        "source",
        "idea_summary",
        "support_scenarios",
        "triage_questions",
        "escalation_paths",
        "known_limitations",
        "troubleshooting_checklist",
        "evidence_risk_notes",
    }
    assert [scenario["id"] for scenario in first["support_scenarios"]] == [
        "SC1",
        "SC2",
        "SC3",
        "SC4",
    ]
    assert [path["id"] for path in first["escalation_paths"]] == [
        "ESC1",
        "ESC2",
        "ESC3",
        "ESC4",
    ]
    assert any(item["id"] == "CHK6" for item in first["troubleshooting_checklist"])
    assert any(note["note"] == "protocol churn" for note in first["evidence_risk_notes"])
    assert any(
        "signal:sig-test001" in note["evidence_links"] for note in first["evidence_risk_notes"]
    )


def test_generate_support_playbook_is_json_serializable(sample_unit, sample_evaluation) -> None:
    playbook = generate_support_playbook(sample_unit, sample_evaluation)

    assert json.loads(json.dumps(playbook))["idea_id"] == "bu-test001"


def test_render_support_playbook_markdown_is_deterministic(sample_unit, sample_evaluation) -> None:
    playbook = generate_support_playbook(sample_unit, sample_evaluation)

    first = render_support_playbook_markdown(playbook)
    second = render_support_playbook_markdown(playbook)

    assert first == second
    assert first.startswith("# MCP Test Framework Support Playbook")
    assert f"- Schema version: {SUPPORT_PLAYBOOK_SCHEMA_VERSION}" in first
    assert "## Likely Support Scenarios" in first
    assert "## Triage Questions" in first
    assert "## Escalation Paths" in first
    assert "## Known Limitations" in first
    assert "## Troubleshooting Checklist" in first
    assert "## Evidence-Linked Risk Notes" in first
    assert "### SC1: User cannot complete primary workflow" in first
    assert "### TQ5: Does it match a known risk?" in first
    assert "### ESC4: launch_owner (critical)" in first
    assert "protocol churn" in first
    assert "signal:sig-test001" in first


def test_render_support_playbook_csv_has_stable_header_and_rows(
    sample_unit, sample_evaluation
) -> None:
    spec = generate_spec_preview(sample_unit, sample_evaluation)
    playbook = generate_support_playbook(sample_unit, sample_evaluation, spec)

    first = render_support_playbook_csv(playbook)
    second = render_support_playbook_csv(playbook)
    reader = csv.DictReader(io.StringIO(first))
    rows = list(reader)

    assert first == second
    assert reader.fieldnames == list(CSV_COLUMNS)
    assert first.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert len(rows) == (
        len(playbook["support_scenarios"])
        + len(playbook["triage_questions"])
        + len(playbook["escalation_paths"])
        + len(playbook["known_limitations"])
        + len(playbook["troubleshooting_checklist"])
        + len(playbook["evidence_risk_notes"])
        + 1
    )
    assert {row["section"] for row in rows} == {
        "support_scenarios",
        "triage_questions",
        "escalation_paths",
        "known_limitations",
        "troubleshooting_checklist",
        "evidence_risk_notes",
        "source_flags",
    }
    assert all(row["idea_id"] == "bu-test001" for row in rows)
    assert all(row["evaluation_available"] == "true" for row in rows)
    assert all(row["tact_spec_available"] == "true" for row in rows)
    assert all(row["tact_spec_schema_version"] == "tact-spec-preview/v1" for row in rows)

    scenario_row = next(
        row for row in rows if row["section"] == "support_scenarios" and row["item_id"] == "SC1"
    )
    assert scenario_row["title_or_question"] == "User cannot complete primary workflow"
    assert (
        scenario_row["trigger"]
        == "MCP server maintainer reports that pre-release CI validation is blocked."
    )
    assert (
        scenario_row["action"]
        == "Confirm the exact step, collect the failing input, and run the troubleshooting checklist."
    )
    assert scenario_row["owner_or_path"] == "TQ1, TQ2, TQ3"
    assert (
        scenario_row["expected_outcome"]
        == "Restore the user path or escalate with reproduction evidence."
    )
    assert scenario_row["related_evidence"] == "idea.workflow_context; idea.validation_plan"

    escalation_row = next(
        row for row in rows if row["section"] == "escalation_paths" and row["item_id"] == "ESC4"
    )
    assert escalation_row["owner_or_path"] == "launch_owner"
    assert (
        escalation_row["trigger"]
        == "A high-confidence risk note materializes or customer data integrity may be affected."
    )
    assert (
        escalation_row["action"]
        == "Start incident review, pause rollout if needed, and notify the buyer."
    )
    assert escalation_row["expected_outcome"] == "1 hour"

    risk_row = next(
        row
        for row in rows
        if row["section"] == "evidence_risk_notes" and row["title_or_question"] == "protocol churn"
    )
    assert risk_row["action"] == "Escalate if this appears in a customer ticket or validation run."
    assert "signal:sig-test001" in risk_row["related_evidence"]

    source_row = next(row for row in rows if row["section"] == "source_flags")
    assert source_row["item_id"] == "source"
    assert source_row["title_or_question"] == "Source availability"
    assert source_row["expected_outcome"] == "tact.project_spec"


def test_render_support_playbook_csv_preserves_triage_limitations_and_checklist(
    sample_unit, sample_evaluation
) -> None:
    playbook = generate_support_playbook(sample_unit, sample_evaluation)
    rows = list(csv.DictReader(io.StringIO(render_support_playbook_csv(playbook))))

    triage_row = next(
        row for row in rows if row["section"] == "triage_questions" and row["item_id"] == "TQ5"
    )
    assert triage_row["title_or_question"] == "Does it match a known risk?"
    assert triage_row["trigger"] == "Compare the ticket against RN1 and any linked evidence."
    assert triage_row["action"] == "Compare the ticket against RN1 and any linked evidence."
    assert triage_row["owner_or_path"] == "product_owner"
    assert triage_row["related_evidence"] == "evidence_risk_notes"

    limitation_row = next(
        row for row in rows if row["section"] == "known_limitations" and row["item_id"] == "LIM1"
    )
    assert limitation_row["title_or_question"] == "First-release scope"
    assert limitation_row["trigger"] == "A CLI tool that validates MCP server implementations"
    assert (
        limitation_row["action"]
        == "Treat requests outside this scope as product feedback unless they block the documented workflow."
    )
    assert limitation_row["related_evidence"] == "execution.mvp_scope; unit.solution"

    checklist_row = next(
        row
        for row in rows
        if row["section"] == "troubleshooting_checklist" and row["item_id"] == "CHK6"
    )
    assert checklist_row["title_or_question"] == "Attach matching evidence-linked risk note."
    assert checklist_row["action"] == "Attach matching evidence-linked risk note."
    assert checklist_row["owner_or_path"] == "product_owner"
    assert (
        checklist_row["expected_outcome"]
        == "Ticket links to risk note or explicitly states no known risk matched."
    )


def test_render_support_playbook_csv_quotes_special_values() -> None:
    playbook = {
        "idea_id": "idea,csv",
        "source": {
            "idea_id": "idea,csv",
            "evaluation_available": True,
            "tact_spec_available": False,
            "tact_spec_schema_version": "schema/v1",
        },
        "support_scenarios": [
            {
                "id": "SC,1",
                "name": 'Quoted "Scenario"',
                "trigger": "line one\nline two, with comma",
                "first_response": 'Say "hello", then collect logs.',
                "triage_questions": ["TQ1", "TQ2"],
                "resolution_target": "Resolved, documented",
                "evidence_links": ["a,b", "c"],
            }
        ],
    }

    csv_text = render_support_playbook_csv(playbook)
    rows = list(csv.DictReader(io.StringIO(csv_text)))

    assert '"idea,csv"' in csv_text
    assert '"line one line two, with comma"' in csv_text
    assert 'Say ""hello"", then collect logs.' in csv_text
    assert rows[0]["idea_id"] == "idea,csv"
    assert rows[0]["item_id"] == "SC,1"
    assert rows[0]["title_or_question"] == 'Quoted "Scenario"'
    assert rows[0]["trigger"] == "line one line two, with comma"
    assert rows[0]["related_evidence"] == "a,b; c"


def test_render_support_playbook_csv_sparse_playbook_is_header_only() -> None:
    csv_text = render_support_playbook_csv({})

    assert csv_text == ",".join(CSV_COLUMNS) + "\n"
    assert csv.DictReader(io.StringIO(csv_text)).fieldnames == list(CSV_COLUMNS)


def test_render_support_playbook_csv_does_not_change_markdown(
    sample_unit, sample_evaluation
) -> None:
    playbook = generate_support_playbook(sample_unit, sample_evaluation)
    before = render_support_playbook_markdown(playbook)

    render_support_playbook_csv(playbook)

    assert render_support_playbook_markdown(playbook) == before


def test_generate_support_playbook_degrades_without_evaluation_or_spec(sample_unit) -> None:
    playbook = generate_support_playbook(sample_unit)

    assert playbook["source"]["evaluation_available"] is False
    assert playbook["source"]["tact_spec_available"] is False
    assert playbook["source"]["tact_spec_schema_version"] is None
    assert playbook["idea_summary"]["recommendation"] is None
    assert (
        playbook["idea_summary"]["primary_scope"]
        == "A CLI tool that validates MCP server implementations"
    )
    assert any(item["id"] == "LIM3" for item in playbook["known_limitations"])
    assert any(note["source"] == "missing_evaluation" for note in playbook["evidence_risk_notes"])
    assert any(path["id"] == "ESC4" for path in playbook["escalation_paths"])

    markdown = render_support_playbook_markdown(playbook)
    assert "- Evaluation available: false" in markdown
    assert "- Tact spec available: false" in markdown


def test_support_playbook_is_importable_from_spec_package(sample_unit, sample_evaluation) -> None:
    playbook = exported_generate(sample_unit, sample_evaluation)
    markdown = exported_render(playbook)
    csv_text = exported_render_csv(playbook)

    assert playbook["schema_version"] == SUPPORT_PLAYBOOK_SCHEMA_VERSION
    assert markdown.startswith("# MCP Test Framework Support Playbook")
    assert csv_text.startswith(",".join(CSV_COLUMNS))
