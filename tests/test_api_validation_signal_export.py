from __future__ import annotations

import json

from max.api.validation_signal_export import (
    SCHEMA_VERSION,
    validation_signal_export_to_json,
)
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode


def _make_unit(unit_id: str = "bu-api-export001") -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title="API Validation Signal Test",
        one_liner="Test JSON export for API",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="API needs structured validation exports",
        solution="Provide JSON endpoint renderer",
        value_proposition="Enable external integrations",
    )


def _make_experiment(
    experiment_id: str = "vexp-api001",
    idea_id: str = "bu-api-export001",
    evidence_urls: list[str] | None = None,
    confidence_delta: float = 0.35,
) -> dict:
    return {
        "id": experiment_id,
        "idea_id": idea_id,
        "hypothesis": "API consumers will adopt JSON exports",
        "method": "Prototype integration test",
        "success_metric": "5 external systems integrate successfully",
        "status": "completed",
        "completed_at": "2026-04-30T12:00:00+00:00",
        "result_summary": "6 systems integrated within 2 weeks",
        "evidence_urls": evidence_urls if evidence_urls is not None else ["https://example.com/integration-notes"],
        "confidence_delta": confidence_delta,
    }


def test_validation_signal_export_to_json_returns_valid_json() -> None:
    unit = _make_unit()
    experiment = _make_experiment()

    json_output = validation_signal_export_to_json(experiment, unit)

    # Verify it's valid JSON
    parsed = json.loads(json_output)
    assert isinstance(parsed, dict)
    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == "max.api.validation_signal_export"


def test_validation_signal_export_includes_signal_fields() -> None:
    unit = _make_unit()
    experiment = _make_experiment()

    json_output = validation_signal_export_to_json(experiment, unit)
    parsed = json.loads(json_output)

    assert "signal" in parsed
    signal = parsed["signal"]
    assert signal["source_type"] == "experiment"
    assert signal["source_adapter"] == "validation_experiment"
    assert "API Validation Signal Test" in signal["title"]
    assert signal["url"] == "max://validation-experiments/vexp-api001"
    assert "validation" in signal["tags"]
    assert "experiment" in signal["tags"]
    assert signal["credibility"] == 0.8


def test_validation_signal_export_includes_validation_data() -> None:
    unit = _make_unit()
    experiment = _make_experiment()

    json_output = validation_signal_export_to_json(experiment, unit)
    parsed = json.loads(json_output)

    assert "validation_data" in parsed
    data = parsed["validation_data"]
    assert data["experiment_id"] == "vexp-api001"
    assert data["idea_id"] == "bu-api-export001"
    assert data["idea_title"] == "API Validation Signal Test"
    assert data["hypothesis"] == "API consumers will adopt JSON exports"
    assert data["method"] == "Prototype integration test"
    assert data["status"] == "completed"
    assert data["success_metric"] == "5 external systems integrate successfully"
    assert data["result_summary"] == "6 systems integrated within 2 weeks"
    assert data["confidence_delta"] == 0.35
    assert data["evidence_urls"] == ["https://example.com/integration-notes"]
    assert data["completed_at"] == "2026-04-30T12:00:00+00:00"


def test_validation_signal_export_includes_aggregation_metrics() -> None:
    unit = _make_unit()
    experiment = _make_experiment(confidence_delta=0.4)

    json_output = validation_signal_export_to_json(experiment, unit)
    parsed = json.loads(json_output)

    assert "aggregation_metrics" in parsed
    metrics = parsed["aggregation_metrics"]
    assert metrics["has_positive_confidence_delta"] is True
    assert metrics["has_evidence_urls"] is True
    assert metrics["evidence_url_count"] == 1
    assert metrics["is_completed"] is True
    assert metrics["credibility_score"] == 0.8
    assert metrics["signal_quality_score"] > 0.8  # Should be boosted by confidence and evidence


def test_validation_signal_export_aggregation_metrics_with_no_evidence() -> None:
    unit = _make_unit()
    experiment = _make_experiment(evidence_urls=[], confidence_delta=0.0)

    json_output = validation_signal_export_to_json(experiment, unit)
    parsed = json.loads(json_output)

    metrics = parsed["aggregation_metrics"]
    assert metrics["has_positive_confidence_delta"] is False
    assert metrics["has_evidence_urls"] is False
    assert metrics["evidence_url_count"] == 0
    assert metrics["signal_quality_score"] == 0.8  # Only base credibility


def test_validation_signal_export_aggregation_metrics_with_multiple_evidence_urls() -> None:
    unit = _make_unit()
    experiment = _make_experiment(
        evidence_urls=[
            "https://example.com/notes1",
            "https://example.com/notes2",
            "https://example.com/results",
        ],
        confidence_delta=0.45,
    )

    json_output = validation_signal_export_to_json(experiment, unit)
    parsed = json.loads(json_output)

    metrics = parsed["aggregation_metrics"]
    assert metrics["has_positive_confidence_delta"] is True
    assert metrics["has_evidence_urls"] is True
    assert metrics["evidence_url_count"] == 3
    assert metrics["signal_quality_score"] == 1.0  # Maxed out: 0.8 + 0.2 (evidence)


def test_validation_signal_export_handles_missing_optional_fields() -> None:
    unit = _make_unit()
    experiment = {
        "id": "vexp-minimal",
        "idea_id": "bu-api-export001",
        "hypothesis": "",
        "method": "",
        "status": "planned",
        "evidence_urls": [],
    }

    json_output = validation_signal_export_to_json(experiment, unit)
    parsed = json.loads(json_output)

    data = parsed["validation_data"]
    assert data["hypothesis"] == ""
    assert data["method"] == ""
    assert data["status"] == "planned"
    assert data["success_metric"] == ""
    assert data["result_summary"] == ""
    assert data["confidence_delta"] is None
    assert data["evidence_urls"] == []
    assert data["completed_at"] is None

    metrics = parsed["aggregation_metrics"]
    assert metrics["has_positive_confidence_delta"] is False
    assert metrics["is_completed"] is False


def test_validation_signal_export_json_deterministic() -> None:
    unit = _make_unit()
    experiment = _make_experiment()

    first = validation_signal_export_to_json(experiment, unit)
    second = validation_signal_export_to_json(experiment, unit)

    assert first == second


def test_validation_signal_export_json_sorted_keys() -> None:
    unit = _make_unit()
    experiment = _make_experiment()

    json_output = validation_signal_export_to_json(experiment, unit)

    # Verify keys are sorted for determinism
    parsed = json.loads(json_output)
    # Re-serialize without sort_keys to compare structure
    unsorted = json.dumps(parsed, indent=2)

    # If keys weren't sorted, re-sorting would change the output
    resorted = json.dumps(parsed, indent=2, sort_keys=True)
    assert json_output == resorted
