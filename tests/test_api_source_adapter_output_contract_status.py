from __future__ import annotations

import json

from max.api import source_adapter_output_contract_status_to_json


def test_source_adapter_output_contract_status_summarizes_and_sorts_non_compliance() -> None:
    payload = {
        "schema_version": "source.v1",
        "kind": "source",
        "expected_schema_version": "contract.v2",
        "required_fields": ["id", "title"],
        "adapters": [
            {"adapter": "healthy", "schema_version": "contract.v2", "fields": ["id", "title"]},
            {"adapter": "missing", "schema_version": "contract.v2", "fields": ["id"]},
            {"adapter": "mismatch", "schema_version": "contract.v1", "fields": ["id", "title"]},
            {"adapter": "invalid", "schema_version": "contract.v2", "fields": ["id", "title"], "invalid_payload_count": 3},
        ],
    }

    rendered = json.loads(source_adapter_output_contract_status_to_json(payload))

    assert rendered["schema_version"] == "max.api.source_adapter_output_contract_status.v1"
    assert rendered["kind"] == "max.api.source_adapter_output_contract_status"
    assert rendered["summary"]["adapter_count"] == 4
    assert rendered["summary"]["non_compliant_count"] == 3
    assert rendered["summary"]["critical_count"] == 2
    assert rendered["summary"]["status"] == "critical"
    assert [row["adapter"] for row in rendered["non_compliant_adapters"]] == ["mismatch", "missing", "invalid"]
    assert rendered["source_metadata"]["source_kind"] == "source"


def test_source_adapter_output_contract_status_empty_input() -> None:
    rendered = json.loads(source_adapter_output_contract_status_to_json({}))

    assert rendered["summary"]["status"] == "no_data"
    assert rendered["adapters"] == []
    assert rendered["non_compliant_adapters"] == []
