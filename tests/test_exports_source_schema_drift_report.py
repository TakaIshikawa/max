from __future__ import annotations

import json

from max.exports.source_schema_drift_report import build_source_schema_drift_report, render_source_schema_drift_report_json, render_source_schema_drift_report_markdown


def test_source_schema_drift_report_detects_missing_new_and_type_change() -> None:
    report = build_source_schema_drift_report(
        [{"source": "github", "field": "id", "observed_type": "string", "sample_count": 4}, {"source": "github", "field": "url", "observed_type": "string"}, {"source": "github", "field": "extra", "observed_type": "object"}],
        baseline={"github": {"id": "integer", "title": "string", "url": "string"}},
    )

    assert [row["drift_kind"] for row in report["drift_rows"]] == ["missing_field", "type_change", "new_field"]
    assert report["summary"]["drift_count"] == 3
    assert json.loads(render_source_schema_drift_report_json(report))["kind"] == report["kind"]
    assert "github title: missing_field" in render_source_schema_drift_report_markdown(report)


def test_source_schema_drift_report_ignores_optional_allowlist() -> None:
    report = build_source_schema_drift_report(
        [{"source": "github", "field": "id", "observed_type": "integer"}],
        baseline={"github": {"id": "integer", "optional": "string"}},
        optional_allowlist=["optional"],
    )

    assert report["drift_rows"] == []
