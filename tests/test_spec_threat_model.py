from __future__ import annotations

import json

from max.spec import generate_threat_model as exported_generate
from max.spec import render_threat_model_markdown as exported_render
from max.spec.generator import generate_spec_preview
from max.spec.threat_model import (
    THREAT_MODEL_SCHEMA_VERSION,
    generate_threat_model,
    render_threat_model_markdown,
)
from max.types.buildable_unit import BuildableCategory, BuildableUnit


def test_generate_threat_model_is_stable_and_json_serializable(
    sample_unit,
    sample_evaluation,
) -> None:
    spec_preview = generate_spec_preview(sample_unit, sample_evaluation)

    first = generate_threat_model(sample_unit, sample_evaluation, spec_preview)
    second = generate_threat_model(sample_unit, sample_evaluation, spec_preview)

    assert first == second
    json.dumps(first, sort_keys=True)
    assert first["schema_version"] == THREAT_MODEL_SCHEMA_VERSION
    assert first["kind"] == "max.threat_model"
    assert first["idea_id"] == "bu-test001"
    assert set(first) == {
        "schema_version",
        "kind",
        "idea_id",
        "scope",
        "assets",
        "trust_boundaries",
        "threat_scenarios",
        "mitigations",
        "residual_risks",
        "review_gate",
    }
    assert first["scope"]["title"] == "MCP Test Framework"
    assert first["scope"]["evidence"] == ["insight:ins-test001", "signal:sig-test001"]
    assert first["assets"]
    assert first["trust_boundaries"]
    assert first["mitigations"]
    assert first["residual_risks"]


def test_threat_scenarios_include_required_security_fields(
    sample_unit,
    sample_evaluation,
) -> None:
    threat_model = generate_threat_model(sample_unit, sample_evaluation)

    assert threat_model["threat_scenarios"]
    assert any(item["severity"] == "high" for item in threat_model["threat_scenarios"])
    for scenario in threat_model["threat_scenarios"]:
        assert scenario["severity"] in {"critical", "high", "medium", "low"}
        assert scenario["affected_asset"]
        assert scenario["attack_path"]
        assert scenario["mitigation"]
        assert scenario["evidence"]


def test_generate_threat_model_handles_sparse_buildable_unit() -> None:
    unit = BuildableUnit(
        id="bu-sparse-threat",
        title="",
        one_liner="",
        category=BuildableCategory.APPLICATION,
        problem="Manual workflow",
        solution="Small app",
        value_proposition="Reduce manual work",
    )

    threat_model = generate_threat_model(unit)

    json.dumps(threat_model, sort_keys=True)
    assert threat_model["idea_id"] == "bu-sparse-threat"
    assert threat_model["scope"]["workflow_context"] == "primary workflow"
    assert threat_model["scope"]["stack"] == "unspecified"
    assert threat_model["review_gate"]["decision"] == "hold"
    assert "utility evaluation is missing" in threat_model["review_gate"]["blocking_reasons"]
    assert "authentication boundary is not explicit" in threat_model["review_gate"]["blocking_reasons"]
    assert any(item["type"] == "data" for item in threat_model["assets"])


def test_render_threat_model_markdown_has_stable_sections_and_high_scenarios(
    sample_unit,
    sample_evaluation,
) -> None:
    threat_model = generate_threat_model(sample_unit, sample_evaluation)
    high_scenario_titles = [
        item["title"] for item in threat_model["threat_scenarios"] if item["severity"] == "high"
    ]

    first = render_threat_model_markdown(threat_model)
    second = render_threat_model_markdown(threat_model)

    assert first == second
    assert first.startswith("# MCP Test Framework Threat Model")
    for heading in [
        "## Scope",
        "## Assets",
        "## Trust Boundaries",
        "## Threat Scenarios",
        "## Mitigations",
        "## Residual Risks",
        "## Review Gate",
    ]:
        assert heading in first
    for title in high_scenario_titles:
        assert title in first


def test_threat_model_is_importable_from_spec_package(sample_unit, sample_evaluation) -> None:
    threat_model = exported_generate(sample_unit, sample_evaluation)
    markdown = exported_render(threat_model)

    assert threat_model["schema_version"] == THREAT_MODEL_SCHEMA_VERSION
    assert markdown.startswith("# MCP Test Framework Threat Model")
