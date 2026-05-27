from __future__ import annotations

import json

from max.api.source_adapter_config_drift_status import source_adapter_config_drift_status_to_json


def test_source_adapter_config_drift_status_detects_sorts_and_summarizes() -> None:
    report = json.loads(
        source_adapter_config_drift_status_to_json(
            {
                "adapters": [
                    {"adapter": "REST", "source": "jira", "deployed_config_hash": "same", "expected_config_hash": "same"},
                    {"adapter": "GraphQL", "source": "github", "deployed_config_hash": "old", "expected_config_hash": "new", "last_checked_at": "2026-05-27T00:00:00Z"},
                    {"adapter": None, "source": None, "deployed_config_hash": 123, "expected_config_hash": ""},
                ],
                "metadata": {"source_schema_version": "input.v1"},
            }
        )
    )

    assert report["schema_version"].endswith(".v1")
    assert report["kind"] == "max.api.source_adapter_config_drift_status"
    assert [row["adapter"] for row in report["rows"]] == ["graphql", "rest", "unknown_adapter"]
    assert report["rows"][0]["drifted"] is True
    assert report["rows"][0]["remediation"] == "redeploy adapter config"
    assert report["summary"]["drifted_count"] == 1
    assert report["summary"]["healthy_count"] == 2
    assert report["drifted_adapters"] == [report["rows"][0]]
    assert json.loads(json.dumps(report, sort_keys=True)) == report
