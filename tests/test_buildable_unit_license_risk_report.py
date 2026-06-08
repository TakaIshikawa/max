from __future__ import annotations

from max.exports import generate_buildable_unit_license_risk_report as exported
from max.exports.buildable_unit_license_risk_report import generate_buildable_unit_license_risk_report


def test_buildable_unit_license_risk_report_buckets_dependency_licenses() -> None:
    report = generate_buildable_unit_license_risk_report(
        [
            {"buildable_unit_id": "unit-a", "profile": "core", "dependencies": [{"name": "fastapi", "license": "MIT"}]},
            {"buildable_unit_id": "unit-b", "profile": "core", "dependencies": [{"name": "copyleft", "license": "GPL"}]},
            {"buildable_unit_id": "unit-c", "profile": "growth", "dependencies": [{"name": "shared", "license": "MPL"}]},
        ]
    )

    assert exported is generate_buildable_unit_license_risk_report
    assert [row["status"] for row in report["rows"]] == ["blocked", "review", "ok"]
    assert report["rows"][0]["highest_risk_dependencies"] == ["copyleft"]
    assert report["summary"]["blocked_count"] == 1

