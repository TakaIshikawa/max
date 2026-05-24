from __future__ import annotations

import json

from max.api.source_adapter_schema_status import source_adapter_schema_status_to_json


def test_source_adapter_schema_status_normalizes_compatibility_and_fields() -> None:
    parsed = json.loads(
        source_adapter_schema_status_to_json(
            {
                "adapters": [
                    {"adapter": "a", "source": "crm", "expected_schema_version": "v1", "observed_schema_version": "v1", "compatibility": "compatible"},
                    {"adapter": "b", "source": "crm", "expected_schema_version": "v1", "observed_schema_version": "v2", "extra_fields": ["x"]},
                    {"adapter": "c", "source": "web", "expected_schema_version": "v1", "observed_schema_version": "v1", "missing_fields": ["id", "id"]},
                    {"adapter": "d", "source": "web", "compatibility": "mystery"},
                ]
            }
        )
    )

    assert [row["status"] for row in parsed["adapters"]] == ["incompatible", "drifted", "unknown", "compatible"]
    assert parsed["adapters"][0]["missing_fields"] == ["id"]
    assert parsed["summary"]["incompatible_count"] == 1
    assert parsed["incompatible_adapters"][0]["adapter"] == "c"
    assert parsed["source_totals"][1]["source"] == "web"
    assert parsed["source_totals"][1]["incompatible_count"] == 1


def test_source_adapter_schema_status_aliases_schema_totals_and_metadata() -> None:
    parsed = json.loads(source_adapter_schema_status_to_json({"schemas": [{"adapter_name": "a", "source_name": "s", "expected": "v1", "observed": "v1", "compatibility": "compatible"}]}, as_of="now"))

    assert parsed["adapters"][0]["status"] == "compatible"
    assert parsed["schema_totals"][0]["expected_schema_version"] == "v1"
    assert parsed["metadata"]["as_of"] == "now"
