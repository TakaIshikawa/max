from __future__ import annotations

import json

from max.exports.source_adapter_version_skew_report import build_source_adapter_version_skew_report, render_source_adapter_version_skew_report_json, render_source_adapter_version_skew_report_markdown


def test_source_adapter_version_skew_report_detects_patch_major_and_unknown() -> None:
    report = build_source_adapter_version_skew_report([
        {"adapter": "github", "expected_version": "1.2.0", "version": "1.2.1", "environment": "prod"},
        {"adapter": "github", "expected_version": "1.2.0", "version": "1.2.0", "environment": "stage"},
        {"adapter": "slack", "expected_version": "1.2.0", "version": "2.0.0", "environment": "prod"},
        {"adapter": "slack", "expected_version": "1.2.0", "version": "1.2.0", "environment": "stage"},
        {"adapter": "jira", "version": "", "environment": "prod"},
    ])

    assert [row["adapter"] for row in report["skew_rows"]] == ["slack", "jira", "github"]
    assert [row["skew_severity"] for row in report["skew_rows"]] == ["major_minor", "unknown", "patch"]
    assert report["summary"]["unknown_version_count"] == 1
    assert json.loads(render_source_adapter_version_skew_report_json(report))["summary"]["skewed_adapter_count"] == 3
    assert "github: 1.2.0, 1.2.1 (patch)" in render_source_adapter_version_skew_report_markdown(report)
