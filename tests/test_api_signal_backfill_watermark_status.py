from __future__ import annotations

import json

from max.api.signal_backfill_watermark_status import signal_backfill_watermark_status_to_json


def test_signal_backfill_watermark_status_computes_lag_and_sorts() -> None:
    parsed = json.loads(
        signal_backfill_watermark_status_to_json(
            {
                "adapters": [
                    {"adapter": "ok", "lag_minutes": 0},
                    {"adapter": "warn", "current_watermark_at": "2026-06-04T10:00:00Z"},
                    {"adapter": "critical", "lag_minutes": 300, "pending_signal_count": 3},
                ]
            },
            as_of="2026-06-04T12:00:00Z",
            warning_lag_minutes=60,
            critical_lag_minutes=240,
        )
    )

    assert [row["adapter"] for row in parsed["adapters"]] == ["critical", "warn", "ok"]
    assert parsed["adapters"][1]["lag_minutes"] == 120
    assert parsed["summary"]["total_pending_signal_count"] == 3
    assert parsed["summary"]["max_lag_minutes"] == 300


def test_signal_backfill_watermark_status_empty_payload_is_ok() -> None:
    parsed = json.loads(signal_backfill_watermark_status_to_json({}, as_of="2026-06-04T12:00:00Z"))
    assert parsed["status"] == "ok"
    assert parsed["summary"]["adapter_count"] == 0
    assert parsed["adapters"] == []
