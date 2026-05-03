from __future__ import annotations

import csv
from io import StringIO

from max.spec import (
    generate_architecture_decision_record,
    render_architecture_decision_record_csv,
    render_architecture_decision_record_markdown,
)
from max.spec.adr import ARCHITECTURE_DECISION_RECORD_CSV_COLUMNS
from max.types.buildable_unit import BuildableUnit


def test_generate_architecture_decision_record_uses_unit_and_evaluation_without_store(
    sample_unit,
    sample_evaluation,
) -> None:
    sample_unit.status = "approved"

    record = generate_architecture_decision_record(
        sample_unit,
        sample_evaluation,
        supporting_insights=[
            {
                "id": "ins-supporting",
                "title": "Maintainers need release gates",
                "summary": "Maintainers want automated checks before publishing MCP servers.",
                "url": "https://example.com/supporting",
            }
        ],
    )

    assert record["schema_version"] == "max-adr/v1"
    assert record["kind"] == "max.architecture_decision_record"
    assert record["idea_id"] == sample_unit.id
    assert record["status"] == "accepted"
    assert record["context"]["problem"] == sample_unit.problem
    assert record["decision"]["technical_approach"] == sample_unit.tech_approach

    alternatives = {alternative["name"]: alternative["outcome"] for alternative in record["considered_alternatives"]}
    assert alternatives["Build the proposed MVP"] == "selected"
    assert alternatives["Do nothing"] == "rejected"
    assert alternatives["Continue current workaround"] == "rejected"

    evidence_keys = {(link["type"], link["id"]) for link in record["evidence_links"]}
    assert ("insight", "ins-test001") in evidence_keys
    assert ("signal", "sig-test001") in evidence_keys
    assert ("supporting_insight", "ins-supporting") in evidence_keys

    evaluation = record["evaluation_summary"]
    assert evaluation["available"] is True
    assert evaluation["recommendation"] == "yes"
    assert evaluation["overall_score"] == 78.0
    assert len(evaluation["dimensions"]) == 7


def test_render_architecture_decision_record_markdown_includes_required_sections(
    sample_unit,
    sample_evaluation,
) -> None:
    sample_unit.status = "approved"
    record = generate_architecture_decision_record(sample_unit, sample_evaluation)

    markdown = render_architecture_decision_record_markdown(record)

    assert markdown.startswith("# ADR: MCP Test Framework")
    assert "## Context" in markdown
    assert "## Decision" in markdown
    assert "## Considered Alternatives" in markdown
    assert "## Consequences" in markdown
    assert "## Evidence Links" in markdown
    assert "## Evaluation Summary" in markdown
    assert "- Status: accepted" in markdown
    assert "- insight:ins-test001 - Inspiring insight reference." in markdown
    assert "- signal:sig-test001 - Evidence signal reference." in markdown
    assert "- Recommendation: yes" in markdown
    assert "- pain_severity: 8.0/10 (confidence 0.70) - test" in markdown


def test_architecture_decision_record_handles_missing_optional_fields() -> None:
    unit = BuildableUnit(
        id="bu-minimal",
        title="Minimal ADR Idea",
        one_liner="Small idea",
        category="feature",
        problem="No concise implementation decision exists.",
        solution="Generate a short ADR.",
        value_proposition="Improve handoffs.",
        status="approved",
    )

    record = generate_architecture_decision_record(unit, None)
    markdown = render_architecture_decision_record_markdown(record)

    assert record["status"] == "proposed"
    assert record["decision"]["technical_approach"] == "Technical approach is not specified yet."
    assert record["decision"]["composability_notes"] == "No composability notes were provided."
    assert record["evaluation_summary"]["available"] is False
    assert record["evaluation_summary"]["summary"] == "No utility evaluation was provided."
    assert record["consequences"]["negative"] == [
        "No explicit risks or weaknesses were provided; validate assumptions before broad launch."
    ]
    assert "No evidence links were provided." in markdown
    assert "- Buyer: none" in markdown
    assert "- Workflow context: none" in markdown
    assert "- Evaluation available: False" in markdown
    assert "- Recommendation: none" in markdown


def test_render_architecture_decision_record_csv_is_parseable_and_deterministic(
    sample_unit,
    sample_evaluation,
) -> None:
    sample_unit.status = "approved"
    record = generate_architecture_decision_record(sample_unit, sample_evaluation)

    rendered = render_architecture_decision_record_csv(record)
    rows = list(csv.DictReader(StringIO(rendered)))

    assert rendered == render_architecture_decision_record_csv(record)
    assert csv.DictReader(StringIO(rendered)).fieldnames == list(
        ARCHITECTURE_DECISION_RECORD_CSV_COLUMNS
    )
    assert {row["section"] for row in rows} >= {
        "decision_summary",
        "context",
        "option",
        "decision_driver",
        "consequence",
        "risk",
        "follow_up_action",
    }
    assert rows[0]["idea_id"] == sample_unit.id
    assert rows[0]["adr_status"] == "accepted"
    assert rows[0]["selected_option"] == "Build the proposed MVP"
    assert rows[0]["recommendation"] == "yes"
    assert rows[0]["score"] == "78.0"

    option_rows = [row for row in rows if row["section"] == "option"]
    assert [row["title"] for row in option_rows][:2] == [
        "Build the proposed MVP",
        "Do nothing",
    ]
    assert option_rows[0]["impact"] == "selected"

    driver_rows = [row for row in rows if row["section"] == "decision_driver"]
    assert any(row["evidence_id"] == "ins-test001" for row in driver_rows)
    assert any(row["item_id"] == "dimension.pain_severity" for row in driver_rows)


def test_render_architecture_decision_record_csv_handles_sparse_record_with_header() -> None:
    rendered = render_architecture_decision_record_csv({"idea_id": "adr-sparse"})
    reader = csv.DictReader(StringIO(rendered))

    assert reader.fieldnames == list(ARCHITECTURE_DECISION_RECORD_CSV_COLUMNS)
    assert list(reader) == []


def test_render_architecture_decision_record_csv_escapes_commas_newlines_and_quotes() -> None:
    record = {
        "idea_id": "idea,quoted",
        "status": "accepted",
        "source": {"idea_id": "source-1", "system": "max", "type": "idea"},
        "context": {
            "title": 'ADR "Quoted"',
            "problem": "Problem with comma, newline\nand quotes",
        },
        "decision": {"summary": 'Choose "CSV", safely', "selected_approach": "CSV export"},
        "considered_alternatives": [
            {
                "name": 'Export "rich" CSV',
                "description": "Rows include commas, quotes, and\nnewlines.",
                "rationale": "Reviewers filter it",
                "outcome": "selected",
            }
        ],
        "consequences": {
            "positive": ["Comparable, traceable artifact"],
            "negative": ['Spreadsheet users may edit "source" cells'],
            "follow_up_actions": ["Review escaped cells\nbefore launch"],
        },
        "evidence_links": [
            {
                "type": "insight",
                "id": "ins,1",
                "summary": 'Evidence says "compare options"\nnow.',
            }
        ],
        "evaluation_summary": {"recommendation": "yes", "overall_score": 88.5},
    }

    rendered = render_architecture_decision_record_csv(record)
    rows = list(csv.DictReader(StringIO(rendered)))

    assert '"idea,quoted"' in rendered
    assert '""rich""' in rendered
    assert rows[0]["title"] == 'ADR "Quoted"'
    assert rows[1]["description"] == 'Problem with comma, newline and quotes'
    assert [row for row in rows if row["section"] == "option"][0]["description"] == (
        "Rows include commas, quotes, and newlines."
    )
    assert [row for row in rows if row["section"] == "decision_driver"][0]["evidence_id"] == "ins,1"


def test_architecture_decision_record_functions_are_importable_from_spec_package() -> None:
    assert callable(generate_architecture_decision_record)
    assert callable(render_architecture_decision_record_markdown)
    assert callable(render_architecture_decision_record_csv)
