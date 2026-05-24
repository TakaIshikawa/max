from __future__ import annotations

import json

from max.api.tact_spec_validation_status import tact_spec_validation_status_to_json


def test_tact_spec_validation_status_normalizes_missing_fields_and_status() -> None:
    parsed = json.loads(
        tact_spec_validation_status_to_json(
            {
                "validations": [
                    {"spec_id": "valid", "validator": "schema", "warning_count": 0},
                    {"spec_id": "warn", "validator": "schema", "warning_count": 2},
                    {"spec_id": "bad", "validator": "tact", "errors": ["x"], "missing_fields": ["owner", "owner", "scope"]},
                    {"spec_id": "skip", "validator": "tact", "skipped": True, "error_count": 4},
                ]
            }
        )
    )

    assert [row["spec_id"] for row in parsed["validations"]] == ["bad", "warn", "valid", "skip"]
    assert parsed["validations"][0]["missing_fields"] == ["owner", "scope"]
    assert parsed["summary"]["invalid_count"] == 1
    assert parsed["summary"]["skipped_count"] == 1
    assert parsed["missing_field_totals"] == [{"field": "owner", "missing_count": 1}, {"field": "scope", "missing_count": 1}]


def test_tact_spec_validation_status_aliases_totals_and_metadata() -> None:
    parsed = json.loads(tact_spec_validation_status_to_json({"specs": [{"id": "s", "validator": "v", "warnings": "1"}]}, as_of="now"))

    assert parsed["validations"][0]["status"] == "warnings"
    assert parsed["validator_totals"][0]["validator"] == "v"
    assert parsed["metadata"]["as_of"] == "now"
