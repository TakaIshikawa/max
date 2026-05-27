from __future__ import annotations

from max.exports import generate_buildable_unit_dependency_freshness_report


def test_buildable_unit_dependency_freshness_report_flags_stale_and_missing_metadata() -> None:
    report = generate_buildable_unit_dependency_freshness_report(
        [
            {
                "unit_id": "u1",
                "dependencies": [
                    {"name": "fastapi", "version": "1", "ecosystem": "pypi", "checked_at": "2026-05-01"},
                    {"name": "react", "version": "19", "ecosystem": "npm"},
                ],
            }
        ],
        as_of="2026-05-27",
        stale_after_days=14,
    )

    assert report["summary"]["dependency_count"] == 2
    assert report["summary"]["missing_metadata_count"] == 1
    assert report["summary"]["stale_metadata_count"] == 1
    assert {row["issue_type"] for row in report["findings"]} == {"missing_freshness_metadata", "stale_dependency_metadata"}

