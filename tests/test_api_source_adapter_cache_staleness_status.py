from __future__ import annotations

import json

from max.api.source_adapter_cache_staleness_status import source_adapter_cache_staleness_status_to_json


def test_source_adapter_cache_staleness_status_age_thresholds_and_ratios() -> None:
    parsed = json.loads(
        source_adapter_cache_staleness_status_to_json(
            {
                "adapters": [
                    {"adapter": "ok", "cache_written_at": "2026-06-04T11:50:00Z", "ttl_minutes": 60, "hit_count": 0, "stale_hit_count": 3},
                    {"adapter": "ttl", "cache_written_at": "2026-06-04T10:00:00Z", "ttl_minutes": 30, "hit_count": 100, "stale_hit_count": 1},
                    {"adapter": "rate", "cache_written_at": "2026-06-04T11:00:00Z", "ttl_minutes": 120, "hit_count": 100, "stale_hit_count": 25},
                ]
            },
            as_of="2026-06-04T12:00:00Z",
            warning_stale_hit_rate=0.05,
            critical_stale_hit_rate=0.2,
        )
    )

    assert [row["adapter"] for row in parsed["adapters"]] == ["rate", "ttl", "ok"]
    assert parsed["adapters"][0]["stale_hit_rate"] == 0.25
    assert parsed["adapters"][1]["cache_age_minutes"] == 120
    assert parsed["adapters"][2]["stale_hit_rate"] == 0.0
    assert parsed["summary"]["total_stale_hit_count"] == 29
