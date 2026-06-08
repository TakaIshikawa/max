from __future__ import annotations

import json

from max.api.buildable_unit_license_risk_status import buildable_unit_license_risk_status_to_json


def test_buildable_unit_license_risk_status_allows_safe_dependencies() -> None:
    report = json.loads(buildable_unit_license_risk_status_to_json({"units": [{"unit_id": "u1", "dependencies": [{"name": "fastapi", "license": "MIT"}]}]}))

    assert report["units"][0]["risk_level"] == "allowed"


def test_buildable_unit_license_risk_status_warns_for_review_decisions() -> None:
    report = json.loads(buildable_unit_license_risk_status_to_json({"units": [{"unit_id": "u1", "dependencies": [{"name": "shared", "license": "MPL"}]}]}))

    assert report["summary"]["status"] == "warning"
    assert report["units"][0]["dependencies"][0]["policy_decision"] == "review"


def test_buildable_unit_license_risk_status_blocks_blocked_and_unknown() -> None:
    report = json.loads(buildable_unit_license_risk_status_to_json({"units": [{"unit_id": "ok", "dependencies": [{"name": "a", "license": "Apache-2.0"}]}, {"unit_id": "bad", "dependencies": [{"name": "copyleft", "license": "GPL"}, {"name": "mystery"}]}]}))

    assert report["units"][0]["unit_id"] == "bad"
    assert report["units"][0]["blocked_dependency_count"] == 2
    assert report["summary"]["blocked_dependency_count"] == 2
