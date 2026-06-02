from __future__ import annotations

import json

from max.api import profile_evaluation_weight_entropy_status_to_json


def test_weight_entropy_normalizes_and_reports_violations() -> None:
    report = json.loads(profile_evaluation_weight_entropy_status_to_json({"profiles": [{"profile": "ok", "weights": {"a": 1, "b": 1}, "min_entropy": 1}, {"profile": "bad", "weights": {"a": -1, "b": "x"}}]}))

    ok = {row["profile"]: row for row in report["profiles"]}["ok"]
    bad = {row["profile"]: row for row in report["profiles"]}["bad"]
    assert ok["normalized_weights"] == {"a": 0.5, "b": 0.5}
    assert ok["entropy"] == 1.0
    assert "negative_weight:a" in bad["violations"]
    assert "non_numeric_weight:b" in bad["violations"]
