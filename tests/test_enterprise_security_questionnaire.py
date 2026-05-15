from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports import build_enterprise_security_questionnaire_export
from max.exports.enterprise_security_questionnaire import (
    render_enterprise_security_questionnaire_json,
    render_enterprise_security_questionnaire_markdown,
)


def _unit(metadata: dict) -> MagicMock:
    unit = MagicMock()
    unit.metadata = metadata
    return unit


def _store(units: list[MagicMock]) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units
    return store


def test_sections_cover_security_privacy_compliance_availability_and_data_handling() -> None:
    report = build_enterprise_security_questionnaire_export(_store([_unit({
        "security_questionnaire": {
            "encryption": {"answer": "AES-256 at rest and TLS in transit", "evidence_references": ["sec-1"]},
            "soc2": "Type II available",
            "retention": "Customer configurable",
        }
    })]))

    assert [section["section"] for section in report["sections"]] == ["security", "privacy", "compliance", "availability", "data_handling"]
    encryption = report["sections"][0]["answers"][0]
    assert encryption["answer_status"] == "known"
    assert encryption["evidence_references"] == ["sec-1"]
    assert report["summary"]["unknown_answer_count"] > 0


def test_unknown_answers_are_explicit_and_outputs_parse() -> None:
    report = build_enterprise_security_questionnaire_export(_store([]), domain="enterprise")

    assert report["sections"][0]["answers"][0]["answer"] == "Unknown"
    assert "Unknown" in render_enterprise_security_questionnaire_markdown(report)
    assert json.loads(render_enterprise_security_questionnaire_json(report))["source"]["domain_filter"] == "enterprise"
