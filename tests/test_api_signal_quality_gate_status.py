from __future__ import annotations

import json

from max.api.signal_quality_gate_status import KIND, SCHEMA_VERSION, signal_quality_gate_status_to_json


def test_signal_quality_gate_status_derives_counts_and_source_rollups() -> None:
    payload = {
        "quality_checks": [
            {"check_id": "fresh", "name": "Freshness", "source": "rss", "status": "pass"},
            {"check_id": "dup", "name": "Duplicate suppression", "source": "rss", "status": "warn", "remediation": "Tune dedupe"},
            {"check_id": "policy", "name": "Policy", "source": "github", "status": "failed", "message": "PII"},
        ]
    }

    parsed = json.loads(signal_quality_gate_status_to_json(payload))

    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == KIND
    assert parsed["summary"] == {"failed_count": 1, "passed_count": 1, "total_count": 3, "warning_count": 1}
    assert [row["check_id"] for row in parsed["checks"]] == ["dup", "fresh", "policy"]
    assert parsed["failed_checks"] == [{"check_id": "policy", "message": "PII", "name": "Policy", "source": "github"}]
    assert parsed["warning_checks"][0]["check_id"] == "dup"
    assert parsed["by_source"] == [
        {"failed_count": 1, "passed_count": 0, "source": "github", "warning_count": 0},
        {"failed_count": 0, "passed_count": 1, "source": "rss", "warning_count": 1},
    ]
    assert [row["id"] for row in parsed["remediation_actions"]] == ["remediate-dup", "remediate-policy"]
    assert signal_quality_gate_status_to_json(payload) == signal_quality_gate_status_to_json({"checks": list(reversed(payload["quality_checks"]))})


def test_signal_quality_gate_status_honors_explicit_sections() -> None:
    parsed = json.loads(
        signal_quality_gate_status_to_json(
            {
                "checks": [{}],
                "summary": {"failed_count": 4},
                "failed_checks": [{"check_id": "x"}],
                "warning_checks": [{"check_id": "w"}],
                "by_source": [{"source": "manual", "failed_count": 2}],
                "remediation_actions": [{"id": "act"}],
            }
        )
    )

    assert parsed["summary"]["failed_count"] == 4
    assert parsed["failed_checks"][0]["check_id"] == "x"
    assert parsed["warning_checks"][0]["check_id"] == "w"
    assert parsed["by_source"][0]["source"] == "manual"
    assert parsed["remediation_actions"][0]["id"] == "act"
