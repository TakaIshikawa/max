from __future__ import annotations

import json

from max.api.source_adapter_schema_compatibility_status import source_adapter_schema_compatibility_status_to_json


def test_source_adapter_schema_compatibility_status_compatible() -> None:
    report = json.loads(source_adapter_schema_compatibility_status_to_json({"adapters": [{"adapter": "rss", "schema_version": "1"}]}))

    assert report["adapters"][0]["status"] == "compatible"


def test_source_adapter_schema_compatibility_status_warning_only_drift() -> None:
    report = json.loads(source_adapter_schema_compatibility_status_to_json({"adapters": [{"adapter": "api", "schema_version": "2", "unsupported_fields": ["extra"]}]}))

    assert report["adapters"][0]["status"] == "degraded"
    assert report["adapters"][0]["unsupported_fields"] == ["extra"]


def test_source_adapter_schema_compatibility_status_incompatible_and_empty() -> None:
    report = json.loads(source_adapter_schema_compatibility_status_to_json({"adapters": [{"adapter": "bad", "schema_version": "3", "missing_required_fields": ["id"]}]}))
    empty = json.loads(source_adapter_schema_compatibility_status_to_json({"adapters": []}))

    assert report["summary"]["status"] == "incompatible"
    assert report["adapters"][0]["compatibility_decision"] == "incompatible"
    assert empty["summary"]["status"] == "compatible"
