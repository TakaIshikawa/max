from __future__ import annotations

import json

from max.spec import generate_dependency_inventory as exported_generate
from max.spec import render_dependency_inventory_markdown as exported_render_markdown
from max.spec.dependency_inventory import (
    DEPENDENCY_INVENTORY_SCHEMA_VERSION,
    generate_dependency_inventory,
    render_dependency_inventory_markdown,
)
from max.spec.generator import generate_spec_preview
from max.types.buildable_unit import BuildableCategory, BuildableUnit


def _dependency_unit() -> BuildableUnit:
    return BuildableUnit(
        id="bu-deps",
        title="Patient Follow-Up Automation",
        one_liner="Automate patient follow-up after intake.",
        category=BuildableCategory.AUTOMATION,
        problem="Teams manually copy patient emails and PII into spreadsheets.",
        solution="A workflow service that syncs patient follow-up status to Salesforce.",
        target_users="humans",
        value_proposition="Reduce missed follow-ups.",
        specific_user="clinic coordinator",
        buyer="clinic operations director",
        workflow_context="patient intake to follow-up queue",
        current_workaround="manual spreadsheet review",
        validation_plan="run against de-identified patient intake fixtures",
        domain_risks=[
            "HIPAA and patient data retention may block launch.",
            "Slack notifications could expose PII.",
        ],
        tech_approach="FastAPI service with Postgres storage, OpenAI summaries, Slack alerts, and OAuth.",
        suggested_stack={
            "backend": "FastAPI",
            "database": "Postgres",
            "ai": "OpenAI",
            "messaging": "Slack",
            "crm": "Salesforce",
        },
        composability_notes="Expose webhook events for downstream operations tools.",
        domain="healthcare",
        status="approved",
    )


def test_generate_dependency_inventory_is_json_ready_and_classifies_sources(
    sample_evaluation,
) -> None:
    unit = _dependency_unit()
    spec = generate_spec_preview(unit, sample_evaluation)

    first = generate_dependency_inventory(unit, sample_evaluation, spec)
    second = generate_dependency_inventory(unit, sample_evaluation, spec)

    assert first == second
    assert json.loads(json.dumps(first)) == first
    assert first["schema_version"] == DEPENDENCY_INVENTORY_SCHEMA_VERSION
    assert first["kind"] == "max.dependency_inventory"
    assert first["idea_id"] == "bu-deps"
    assert first["summary"]["dependency_count"] >= 6
    assert first["summary"]["data_store_count"] >= 1
    assert first["summary"]["external_service_count"] >= 2
    assert first["summary"]["integration_count"] >= 2
    assert first["summary"]["high_risk_count"] >= 1
    assert set(first) == {
        "schema_version",
        "kind",
        "idea_id",
        "source",
        "summary",
        "dependencies",
        "mitigation_actions",
        "missing_input_notes",
    }

    by_name = {item["name"]: item for item in first["dependencies"]}
    assert by_name["Postgres"]["type"] == "data_store"
    assert by_name["Postgres"]["owner"] == "data_owner"
    assert by_name["OpenAI"]["type"] == "external_service"
    assert by_name["Slack"]["type"] == "integration"
    assert by_name["Risk review dependency"]["type"] == "risk_control"
    assert by_name["Risk review dependency"]["risk_level"] == "high"
    assert "unit.suggested_stack.database" in by_name["Postgres"]["source_fields"]
    assert "tact_spec.solution.suggested_stack.database" in by_name["Postgres"]["source_fields"]
    assert all(item["id"].startswith("DEP") for item in first["dependencies"])


def test_render_dependency_inventory_markdown_has_stable_dependency_and_mitigation_sections(
    sample_evaluation,
) -> None:
    unit = _dependency_unit()
    inventory = generate_dependency_inventory(unit, sample_evaluation, generate_spec_preview(unit, sample_evaluation))

    first = render_dependency_inventory_markdown(inventory)
    second = render_dependency_inventory_markdown(inventory)

    assert first == second
    assert first.startswith("# Patient Follow-Up Automation Dependency Inventory")
    assert f"- Schema version: {DEPENDENCY_INVENTORY_SCHEMA_VERSION}" in first
    assert "## Dependencies" in first
    assert "## Mitigation Actions" in first
    assert "## Missing Input Notes" in first
    assert "Postgres" in first
    assert "Risk review dependency" in first
    assert "Assign an accountable owner for each dependency" in first


def test_sparse_inputs_produce_conservative_fallback_dependencies() -> None:
    unit = BuildableUnit(
        id="bu-sparse-deps",
        title="Sparse Idea",
        one_liner="Sparse idea.",
        category=BuildableCategory.FEATURE,
        problem="Unknown operational problem.",
        solution="Unknown solution.",
        target_users="agents",
        value_proposition="Unknown value.",
    )

    inventory = generate_dependency_inventory(unit, None, {"schema_version": "tact-spec-preview/v1"})

    assert inventory["kind"] == "max.dependency_inventory"
    assert inventory["summary"]["dependency_count"] == 2
    assert inventory["summary"]["missing_input_note_count"] == 3
    assert {item["name"] for item in inventory["dependencies"]} == {
        "Implementation runtime",
        "Persistence boundary",
    }
    assert all(item["risk_level"] == "medium" for item in inventory["dependencies"])
    assert inventory["missing_input_notes"][0].startswith("No suggested stack entries")
    markdown = render_dependency_inventory_markdown(inventory)
    assert "fallback dependencies are conservative placeholders" in markdown


def test_dependency_inventory_is_importable_from_spec_package(sample_evaluation) -> None:
    unit = _dependency_unit()
    inventory = exported_generate(unit, sample_evaluation, generate_spec_preview(unit, sample_evaluation))
    markdown = exported_render_markdown(inventory)

    assert inventory["schema_version"] == DEPENDENCY_INVENTORY_SCHEMA_VERSION
    assert markdown.startswith("# Patient Follow-Up Automation Dependency Inventory")
