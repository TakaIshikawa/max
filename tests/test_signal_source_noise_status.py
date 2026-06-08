from __future__ import annotations

import json

from max.api import signal_source_noise_status_to_json as exported
from max.api.signal_source_noise_status import signal_source_noise_status_to_json


def test_signal_source_noise_status_handles_empty_samples() -> None:
    report = json.loads(signal_source_noise_status_to_json([]))

    assert exported is signal_source_noise_status_to_json
    assert report["summary"]["status"] == "clean"
    assert report["summary"]["total_signals"] == 0
    assert report["sources"] == []


def test_signal_source_noise_status_groups_rates_by_source_and_profile() -> None:
    report = json.loads(signal_source_noise_status_to_json([{"source": "rss", "profile": "core", "signal_count": 3, "noisy": True}, {"source": "rss", "profile": "core", "signal_count": 1, "duplicate": True}]))

    assert report["sources"][0]["total_signals"] == 4
    assert report["sources"][0]["noisy_signals"] == 3
    assert report["sources"][0]["duplicate_signals"] == 1
    assert report["sources"][0]["noise_rate"] == 75
    assert report["sources"][0]["status"] == "unusable"


def test_signal_source_noise_status_uses_configurable_thresholds() -> None:
    report = json.loads(signal_source_noise_status_to_json([{"source": "crm", "profile": "core", "noisy": True}, {"source": "crm", "profile": "core"}], noisy_threshold=40, unusable_threshold=90))

    assert report["sources"][0]["status"] == "noisy"
    assert report["summary"]["status"] == "noisy"
