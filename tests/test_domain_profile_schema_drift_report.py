from __future__ import annotations

from max.exports import generate_domain_profile_schema_drift_report as exported
from max.exports.domain_profile_schema_drift_report import generate_domain_profile_schema_drift_report


def test_domain_profile_schema_drift_report_groups_findings() -> None:
    report = generate_domain_profile_schema_drift_report(
        [
            {"profile": "fintech", "schema_version": "v2", "findings": [{"type": "missing_field", "field": "risk"}, {"type": "type_mismatch", "field": "score"}]},
            {"profile": "retail", "schema_version": "v2", "findings": [{"type": "unknown_field", "field": "legacy"}, {"type": "deprecated_field", "field": "old"}]},
        ]
    )

    assert exported is generate_domain_profile_schema_drift_report
    assert report["rows"][0] == {"profile": "fintech", "schema_version": "v2", "missing_fields": 1, "unknown_fields": 0, "type_mismatches": 1, "deprecated_fields": 0, "issue_fields": ["risk", "score"], "status": "drifted"}
    assert report["rows"][1]["status"] == "compatible"


def test_domain_profile_schema_drift_report_empty_input() -> None:
    assert generate_domain_profile_schema_drift_report([])["rows"] == []
