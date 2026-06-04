from __future__ import annotations

import json

from max.api.buildable_unit_stack_compliance_status import buildable_unit_stack_compliance_status_to_json


def test_buildable_unit_stack_compliance_status_flags_missing_and_unsupported() -> None:
    report = json.loads(
        buildable_unit_stack_compliance_status_to_json(
            [
                {"unit_id": "ok", "runtime": "python", "deployment_target": "worker"},
                {"unit_id": "unsupported", "runtime": "ruby", "deployment_target": "worker"},
                {"unit_id": "missing", "runtime": "go"},
            ],
            allowed_runtimes={"python", "go"},
        )
    )

    assert [row["unit_id"] for row in report["units"]] == ["missing", "unsupported", "ok"]
    assert report["units"][0]["violations"] == ["missing_deployment_target"]
    assert report["units"][1]["violations"] == ["unsupported_runtime"]

