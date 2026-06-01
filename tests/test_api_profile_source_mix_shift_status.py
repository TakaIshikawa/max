from __future__ import annotations

import json

from max.api import profile_source_mix_shift_status_to_json


def test_profile_source_mix_shift_status_balanced_mixes() -> None:
    report = json.loads(profile_source_mix_shift_status_to_json({"profiles": [{"profile": "p1", "current": {"crm": 50, "docs": 50}, "baseline": {"crm": 50, "docs": 50}}]}))
    assert report["summary"]["status"] == "healthy"
    assert report["profiles"][0]["max_shift"] == 0.0


def test_profile_source_mix_shift_status_major_source_shift() -> None:
    report = json.loads(profile_source_mix_shift_status_to_json({"critical_max_shift": 0.3, "profiles": [{"profile": "p1", "current": {"crm": 90, "docs": 10}, "baseline": {"crm": 50, "docs": 50}}]}))
    assert report["summary"]["status"] == "critical"
    assert report["profiles"][0]["sources"][0]["shift"] == 0.4


def test_profile_source_mix_shift_status_missing_baseline_source() -> None:
    report = json.loads(profile_source_mix_shift_status_to_json({"profiles": [{"profile": "p1", "current": {"new": 10}, "baseline": {"old": 10}}]}))
    assert report["profiles"][0]["sources"][0]["direction"] in {"missing_baseline", "missing_current"}


def test_profile_source_mix_shift_status_zero_current_samples() -> None:
    report = json.loads(profile_source_mix_shift_status_to_json({"profiles": [{"profile": "p1", "current": {}, "baseline": {"crm": 10}}]}))
    assert report["profiles"][0]["current_total"] == 0
    assert report["summary"]["status"] == "critical"
