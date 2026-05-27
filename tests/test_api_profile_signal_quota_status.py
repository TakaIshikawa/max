from __future__ import annotations

import json

from max.api.profile_signal_quota_status import profile_signal_quota_status_to_json


def test_profile_signal_quota_status_computes_remaining_usage_and_summary() -> None:
    report = json.loads(profile_signal_quota_status_to_json({"profiles": [{"profile": "alpha", "quota": 10, "consumed": 12}, {"profile": "beta", "quota": 8, "consumed": 4}, {"profile": "bad", "quota": -1, "consumed": "x"}]}))

    assert report["rows"][0]["profile"] == "alpha"
    assert report["rows"][0]["remaining"] == 0
    assert report["rows"][0]["usage_ratio"] == 1.2
    assert report["rows"][0]["exhausted"] is True
    assert report["summary"]["total_quota"] == 18
    assert report["summary"]["total_consumed"] == 16
    assert report["summary"]["exhausted_count"] == 1
    assert report["summary"]["highest_usage_ratio"] == 1.2
