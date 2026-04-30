from __future__ import annotations

from max.spec import (
    generate_architecture_decision_record,
    render_architecture_decision_record_markdown,
)
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


def test_architecture_decision_record_functions_are_importable_from_spec_package() -> None:
    assert callable(generate_architecture_decision_record)
    assert callable(render_architecture_decision_record_markdown)
