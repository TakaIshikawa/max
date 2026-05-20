from __future__ import annotations

import json

from max.api.source_ingestion_coverage import (
    KIND,
    SCHEMA_VERSION,
    source_ingestion_coverage_to_json,
)


def test_source_ingestion_coverage_to_json_normalizes_and_sorts_sources() -> None:
    payload = {
        "schema_version": "max.source_ingestion_coverage.v1",
        "kind": "max.source_ingestion_coverage",
        "run": {
            "id": "run-001",
            "status": "completed",
            "profile": "nightly",
            "domain": "payments",
            "started_at": "2026-05-20T00:00:00",
            "completed_at": "2026-05-20T00:10:00",
        },
        "sources": [
            {
                "source_id": "src-zendesk",
                "name": "Zendesk",
                "type": "ticketing",
                "status": "healthy",
                "signal_count": "7",
            },
            {
                "source_id": "src-billing",
                "name": "Billing",
                "source_type": "warehouse",
                "status": "stale",
                "signals_count": 4,
                "last_seen_at": "2026-05-18T00:00:00",
                "cadence": "daily",
            },
            {
                "source_id": "src-admin",
                "name": "Admin",
                "enabled": False,
                "signal_count": 0,
                "metadata": {"disabled_reason": "credential rotation", "owner": "ops"},
            },
            {
                "source_id": "src-api",
                "name": "API",
                "status": "errored",
                "signal_count": 2,
                "errors": [{"message": "timeout", "code": "ETIMEDOUT"}],
            },
        ],
    }

    output = source_ingestion_coverage_to_json(payload)
    parsed = json.loads(output)

    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == KIND
    assert parsed["run_summary"]["run_id"] == "run-001"
    assert [row["source_id"] for row in parsed["coverage_by_source"]] == [
        "src-admin",
        "src-api",
        "src-billing",
        "src-zendesk",
    ]
    assert parsed["disabled_sources"] == [
        {
            "name": "Admin",
            "owner": "ops",
            "reason": "credential rotation",
            "source_id": "src-admin",
        }
    ]
    assert parsed["stale_sources"] == [
        {
            "expected_cadence": "daily",
            "last_ingested_at": "2026-05-18T00:00:00",
            "name": "Billing",
            "source_id": "src-billing",
        }
    ]
    assert parsed["signal_counts"] == {
        "by_source": {
            "src-admin": 0,
            "src-api": 2,
            "src-billing": 4,
            "src-zendesk": 7,
        },
        "total": 13,
    }
    assert parsed["error_counts"] == {
        "by_source": {
            "src-admin": 0,
            "src-api": 1,
            "src-billing": 0,
            "src-zendesk": 0,
        },
        "total": 1,
    }
    assert parsed["metadata"]["source_kind"] == "max.source_ingestion_coverage"
    assert parsed["metadata"]["disabled_source_count"] == 1
    assert parsed["metadata"]["stale_source_count"] == 1
    assert output == source_ingestion_coverage_to_json(payload)


def test_source_ingestion_coverage_to_json_defaults_missing_optional_fields() -> None:
    parsed = json.loads(source_ingestion_coverage_to_json({"source_coverage": [{}]}))

    assert parsed["run_summary"]["run_id"] is None
    assert parsed["coverage_by_source"] == [
        {
            "enabled": True,
            "error_count": 0,
            "errors": [],
            "expected_cadence": None,
            "last_ingested_at": None,
            "metadata": {},
            "name": None,
            "signal_count": 0,
            "source_id": "S1",
            "stale": False,
            "status": "unknown",
            "type": None,
        }
    ]
    assert parsed["disabled_sources"] == []
    assert parsed["stale_sources"] == []
    assert parsed["signal_counts"] == {"by_source": {"S1": 0}, "total": 0}
    assert parsed["error_counts"] == {"by_source": {"S1": 0}, "total": 0}
    assert parsed["metadata"]["source_schema_version"] is None
