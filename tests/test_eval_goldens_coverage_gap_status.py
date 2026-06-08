from __future__ import annotations

import json

from max.api import eval_goldens_coverage_gap_status_to_json as exported
from max.api.eval_goldens_coverage_gap_status import eval_goldens_coverage_gap_status_to_json


def test_eval_goldens_coverage_gap_status_handles_zero_expected_cases() -> None:
    report = json.loads(eval_goldens_coverage_gap_status_to_json([]))

    assert exported is eval_goldens_coverage_gap_status_to_json
    assert report["summary"]["status"] == "covered"
    assert report["summary"]["coverage_percent"] == 100
    assert report["coverage"] == []


def test_eval_goldens_coverage_gap_status_groups_by_profile_and_dimension() -> None:
    report = json.loads(eval_goldens_coverage_gap_status_to_json([{"profile": "core", "dimension": "quality", "expected_cases": 10, "covered_cases": 4}, {"profile": "core", "dimension": "quality", "expected_cases": 5, "covered_cases": 5}]))

    assert report["coverage"][0]["profile"] == "core"
    assert report["coverage"][0]["dimension"] == "quality"
    assert report["coverage"][0]["expected_cases"] == 15
    assert report["coverage"][0]["missing_cases"] == 6
    assert report["coverage"][0]["coverage_percent"] == 60
    assert report["coverage"][0]["status"] == "thin"


def test_eval_goldens_coverage_gap_status_marks_missing() -> None:
    report = json.loads(eval_goldens_coverage_gap_status_to_json({"goldens": [{"profile": "core", "evaluation_dimension": "faithfulness", "expected": 3, "covered": 0}]}))

    assert report["coverage"][0]["status"] == "missing"
    assert report["summary"]["status"] == "missing"
