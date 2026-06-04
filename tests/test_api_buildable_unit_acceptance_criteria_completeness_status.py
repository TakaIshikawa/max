from __future__ import annotations

import json

from max.api import buildable_unit_acceptance_criteria_completeness_status_to_json


def test_buildable_unit_acceptance_criteria_completeness_status_classifies_rows() -> None:
    report = json.loads(buildable_unit_acceptance_criteria_completeness_status_to_json({"units": [{"unit_id": "ok", "criteria": ["assert JSON is emitted", "verify pytest passes"]}, {"unit_id": "warn", "acceptance_criteria": ["document behavior"]}, {"id": "crit", "acceptance_criteria": []}]}, minimum_criteria=2))

    assert [row["unit_id"] for row in report["unit_rows"]] == ["crit", "warn", "ok"]
    assert [row["status"] for row in report["unit_rows"]] == ["critical", "warning", "ok"]
    assert report["summary"]["incomplete_units"] == 2


def test_buildable_unit_acceptance_criteria_completeness_status_normalizes_malformed_criteria() -> None:
    report = json.loads(buildable_unit_acceptance_criteria_completeness_status_to_json({"items": [{"id": "one", "criteria": {"bad": "shape"}}]}))

    assert report["unit_rows"][0]["criteria_count"] == 1
    assert report["unit_rows"][0]["status"] == "warning"
