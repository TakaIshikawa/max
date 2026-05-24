from __future__ import annotations

import json

from max.api import prompt_redaction_coverage_status_to_json


def test_prompt_redaction_coverage_status_lists_uncovered_fields() -> None:
    parsed = json.loads(
        prompt_redaction_coverage_status_to_json(
            {
                "templates": [
                    {"id": "covered", "sensitive_fields": ["email"], "redaction_rules": ["email"]},
                    {"id": "partial", "sensitive_fields": ["email", "ssn"], "redaction_rules": ["email"]},
                    {"id": "exposed", "sensitive_fields": ["token"], "coverage_ratio": -2},
                ]
            }
        )
    )

    assert [row["status"] for row in parsed["templates"]] == ["exposed", "partial", "covered"]
    assert parsed["templates"][0]["coverage_ratio"] == 0.0
    assert parsed["uncovered_fields"][0]["template_id"] == "exposed"

