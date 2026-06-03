from __future__ import annotations

import json

from max.api import signal_source_noise_floor_status_to_json


def test_signal_source_noise_floor_status_computes_noise_rate_and_profiles() -> None:
    data = json.loads(signal_source_noise_floor_status_to_json({"warning_noise_rate": 0.2, "critical_noise_rate": 0.5, "sources": [{"source": "rss", "profiles": ["core", "growth"], "accepted_signals": 4, "rejected_signals": 6, "window_hours": 24}, {"source": "api", "profile": "core", "accepted_signals": 8, "noisy_signals": 2}, {"source": "docs", "accepted_signals": 10, "rejected_signals": 0}]}))

    assert data["status"] == "critical"
    assert data["summary"]["source_count"] == 3
    assert data["summary"]["noisy_source_count"] == 2
    assert data["summary"]["rejected_signal_total"] == 6
    assert data["summary"]["noisy_signal_total"] == 2
    assert [row["source"] for row in data["sources"]] == ["rss", "api", "docs"]
    assert data["sources"][0]["noise_rate"] == 0.6
    assert data["profile_hot_spots"][0] == {"profile": "core", "noisy_source_count": 2}
