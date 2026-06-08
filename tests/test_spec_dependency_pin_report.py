from __future__ import annotations

from max.exports import generate_spec_dependency_pin_report as exported
from max.exports.spec_dependency_pin_report import generate_spec_dependency_pin_report


def test_spec_dependency_pin_report_classifies_dependency_versions() -> None:
    report = generate_spec_dependency_pin_report(
        [
            {"spec_id": "spec-a", "dependencies": {"fastapi": "0.110.0", "uvicorn": "^0.29.0", "redis": "latest", "missing": ""}},
            {"spec_id": "spec-b", "dependencies": [{"name": "pydantic", "version": "2.7.1"}]},
        ]
    )

    assert exported is generate_spec_dependency_pin_report
    assert report["summary"]["noncompliant_count"] == 1
    row = report["rows"][0]
    assert row["spec_id"] == "spec-a"
    assert row["pinned_count"] == 1
    assert row["ranged_count"] == 1
    assert row["floating_count"] == 1
    assert row["missing_count"] == 1
    assert row["offending_dependencies"] == ["missing", "redis", "uvicorn"]

