from __future__ import annotations

import csv
import json
from io import StringIO

from max.spec import generate_threat_model as exported_generate
from max.spec import render_threat_model_csv as exported_render_csv
from max.spec import render_threat_model_markdown as exported_render
from max.spec.generator import generate_spec_preview
from max.spec.threat_model import (
    THREAT_MODEL_CSV_COLUMNS,
    THREAT_MODEL_SCHEMA_VERSION,
    generate_threat_model,
    render_threat_model_csv,
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
    assert threat_model["review_gate"]["decision"] == "needs_security_review"
    assert "utility evaluation is missing" in threat_model["review_gate"]["blocking_reasons"]
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


def test_render_threat_model_csv_has_stable_header_and_flattened_generated_rows(
    sample_unit,
    sample_evaluation,
) -> None:
    threat_model = generate_threat_model(sample_unit, sample_evaluation)

    first = render_threat_model_csv(threat_model)
    second = render_threat_model_csv(threat_model)
    rows = list(csv.DictReader(StringIO(first)))

    assert first == second
    assert first.endswith("\n")
    assert first.splitlines()[0] == ",".join(THREAT_MODEL_CSV_COLUMNS)
    assert reader_fieldnames(first) == list(THREAT_MODEL_CSV_COLUMNS)
    assert len(rows) == len(threat_model["threat_scenarios"])

    credential_row = next(row for row in rows if row["threat_id"] == "THR3")
    assert credential_row["idea_id"] == "bu-test001"
    assert credential_row["title"] == "MCP Test Framework"
    assert credential_row["asset"] == "Credentials and integration secrets"
    assert credential_row["threat"] == "Credential leakage enables service impersonation"
    assert credential_row["severity"] == "high"
    assert credential_row["attack_vector"].startswith("A token, API key, webhook secret")
    assert credential_row["mitigation_ids"] == "MIT3"
    assert "MIT3: Keep secrets out of code, logs, and client state" in credential_row[
        "mitigation_details"
    ]
    assert "THR3" in credential_row["residual_risk"]
    assert credential_row["evidence"]
    assert credential_row["source"] == credential_row["evidence"]


def test_render_threat_model_csv_flattens_multiple_threats_with_context() -> None:
    threat_model = {
        "idea_id": "bu-csv-threats",
        "scope": {
            "title": "CSV Threat Console",
            "workflow_context": "analyst triage",
            "stack": "FastAPI",
            "evidence": ["signal:sig-csv"],
        },
        "threat_scenarios": [
            {
                "id": "THR10",
                "title": "Webhook replay",
                "severity": "high",
                "affected_asset": "Webhook endpoint",
                "actor": "external attacker",
                "attack_vector": "Replay a signed callback.",
                "likelihood": "medium",
                "impact": "high",
                "mitigation": "Apply MIT10.",
                "mitigation_ids": ["MIT10"],
                "detection": "Alert on duplicate callback identifiers.",
                "evidence": ["solution.webhooks"],
                "status": "open",
            },
            {
                "id": "THR11",
                "title": "Operator over-export",
                "severity": "medium",
                "affected_asset": "Customer export",
                "attack_path": "Export records without scoped review.",
                "mitigation": "Apply MIT11.",
                "mitigation_ids": ["MIT11"],
                "evidence": ["execution.risks"],
                "status": "open",
            },
        ],
        "mitigations": [
            {
                "id": "MIT10",
                "title": "Reject replayed webhooks",
                "action": "Store callback identifiers and reject duplicates.",
                "owner": "integration_owner",
            },
            {
                "id": "MIT11",
                "title": "Require export approval",
                "action": "Gate exports behind role and purpose checks.",
                "owner": "data_owner",
            },
        ],
        "residual_risks": [
            {
                "id": "RR10",
                "title": "Vendor retry behavior can change",
                "severity": "medium",
                "description": "Retries may bypass local assumptions.",
                "source_refs": ["threat_scenarios.THR10"],
            },
            {
                "id": "RR11",
                "title": "Manual approval drift",
                "severity": "low",
                "description": "Operators may approve stale exports.",
                "source_refs": ["THR11"],
            },
        ],
    }

    rows = list(csv.DictReader(StringIO(render_threat_model_csv(threat_model))))

    assert [row["threat_id"] for row in rows] == ["THR10", "THR11"]
    assert rows[0]["actor"] == "external attacker"
    assert rows[0]["attack_vector"] == "Replay a signed callback."
    assert rows[0]["likelihood"] == "medium"
    assert rows[0]["impact"] == "high"
    assert rows[0]["detection"] == "Alert on duplicate callback identifiers."
    assert rows[0]["residual_risk_ids"] == "RR10"
    assert "Store callback identifiers" in rows[0]["mitigation_details"]
    assert rows[1]["attack_vector"] == "Export records without scoped review."
    assert rows[1]["residual_risk_ids"] == "RR11"
    assert "Gate exports behind role and purpose checks" in rows[1]["mitigation_details"]


def test_render_threat_model_csv_escapes_commas_quotes_and_newlines(
    sample_unit,
    sample_evaluation,
) -> None:
    threat_model = generate_threat_model(sample_unit, sample_evaluation)
    threat_model["threat_scenarios"][0]["title"] = 'Replay "token", then pivot'
    threat_model["threat_scenarios"][0]["attack_path"] = "Send callback,\nreuse token."
    first_mitigation_id = threat_model["threat_scenarios"][0]["mitigation_ids"][0]
    first_mitigation = next(
        item for item in threat_model["mitigations"] if item["id"] == first_mitigation_id
    )
    first_mitigation["action"] = 'Check "nonce", timestamp,\nand signature.'

    csv_text = render_threat_model_csv(threat_model)
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert '"Replay ""token"", then pivot"' in csv_text
    assert '"Send callback,\nreuse token."' in csv_text
    assert 'Check ""nonce"", timestamp,\nand signature.' in csv_text
    assert rows[0]["threat"] == 'Replay "token", then pivot'
    assert rows[0]["attack_vector"] == "Send callback,\nreuse token."
    assert 'Check "nonce", timestamp,\nand signature.' in rows[0]["mitigation_details"]


def test_render_threat_model_csv_handles_empty_threat_lists() -> None:
    csv_text = render_threat_model_csv(
        {
            "idea_id": "bu-empty-threats",
            "scope": {
                "title": "Empty Threat Model",
                "workflow_context": "primary workflow",
                "stack": "unspecified",
            },
            "threat_scenarios": [],
            "mitigations": [],
            "residual_risks": [],
        }
    )

    assert csv_text == ",".join(THREAT_MODEL_CSV_COLUMNS) + "\n"
    assert list(csv.DictReader(StringIO(csv_text))) == []


def test_threat_model_is_importable_from_spec_package(sample_unit, sample_evaluation) -> None:
    threat_model = exported_generate(sample_unit, sample_evaluation)
    markdown = exported_render(threat_model)
    csv_text = exported_render_csv(threat_model)

    assert threat_model["schema_version"] == THREAT_MODEL_SCHEMA_VERSION
    assert markdown.startswith("# MCP Test Framework Threat Model")
    assert csv_text.startswith(",".join(THREAT_MODEL_CSV_COLUMNS))


def reader_fieldnames(csv_text: str) -> list[str] | None:
    return csv.DictReader(StringIO(csv_text)).fieldnames
