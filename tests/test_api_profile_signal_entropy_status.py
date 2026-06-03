from __future__ import annotations

import json

from max.api.profile_signal_entropy_status import profile_signal_entropy_status_to_json


def test_profile_signal_entropy_status_accepts_mapping_and_classifies() -> None:
    report = json.loads(profile_signal_entropy_status_to_json({"profiles": {"balanced": {"source_counts": {"a": 5, "b": 5, "c": 5}}, "thin": {"source_counts": {"a": 10}}, "low": {"source_counts": {"a": 9, "b": 1}}}}, warning_entropy=1.0, critical_entropy=0.5))

    assert [row["profile"] for row in report["profile_rows"]] == ["thin", "low", "balanced"]
    assert report["profile_rows"][0]["entropy"] == 0.0
    assert report["profile_rows"][0]["status"] == "critical"
    assert report["profile_rows"][2]["dominant_share"] == 0.3333


def test_profile_signal_entropy_status_accepts_list_and_zero_total() -> None:
    report = json.loads(profile_signal_entropy_status_to_json({"profiles": [{"profile": "empty", "source_counts": {"a": 0}}]}))

    assert report["profile_rows"][0]["total_signals"] == 0
    assert report["profile_rows"][0]["status"] == "critical"
