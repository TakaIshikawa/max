from __future__ import annotations

import json

from max.api import source_adapter_clock_skew_status_to_json


def test_clock_skew_groups_affected_and_exports_pretty_json() -> None:
    parsed = json.loads(source_adapter_clock_skew_status_to_json({"adapters": [
        {"adapter": "z", "source": "feed", "observed_at": "2026-06-01T00:00:00Z", "source_time": "2026-06-01T00:00:20Z", "system_time": "2026-06-01T00:00:00Z", "skew_seconds": 20, "tolerance_seconds": 10},
        {"adapter": "a", "source": "rss", "observed_at": "2026-06-01T00:00:00Z", "source_time": "2026-06-01T00:00:03Z", "system_time": "2026-06-01T00:00:00Z", "skew_seconds": 3, "tolerance_seconds": 10},
        {"adapter": "m", "source": "api", "observed_at": "2026-06-01T00:00:00Z", "source_time": "2026-06-01T00:00:11Z", "system_time": "2026-06-01T00:00:00Z", "skew_seconds": 11, "tolerance_seconds": 10},
    ]}))
    assert parsed["schema_version"] == "max.api.source_adapter_clock_skew_status.v1"
    assert parsed["kind"] == "max.api.source_adapter_clock_skew_status"
    assert parsed["summary"]["status"] == "critical"
    assert [row["status"] for row in parsed["affected_adapters"]] == ["critical", "warning"]
    assert parsed["adapters"][0]["adapter"] == "z"


def test_clock_skew_missing_metadata_is_unknown() -> None:
    parsed = json.loads(source_adapter_clock_skew_status_to_json({"adapters": [{"adapter": "a"}]}))
    assert parsed["summary"]["status"] == "unknown"
    assert parsed["affected_adapters"][0]["status"] == "unknown"
    assert "skew_seconds" in parsed["affected_adapters"][0]["missing_fields"]
