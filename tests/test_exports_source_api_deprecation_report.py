from __future__ import annotations

import json

from max.exports import build_source_api_deprecation_report, render_source_api_deprecation_report_json


def test_source_api_deprecation_report_classifies_sunset_severity() -> None:
    report = build_source_api_deprecation_report([
        {"source": "past", "adapter": "api", "version": "v1", "deprecated": True, "sunset_at": "2026-05-01"},
        {"source": "soon", "adapter": "api", "version": "v2", "sunset_at": "2026-06-10"},
        {"source": "later", "adapter": "api", "version": "v3", "sunset_at": "2026-09-01"},
        {"source": "missing", "adapter": "api", "version": "v4", "deprecated": True},
        {"source": "ok", "adapter": "api", "version": "v5"},
    ], generated_at="2026-05-27")

    assert [row["severity"] for row in report["rows"]] == ["expired", "deprecated", "sunset_soon", "scheduled", "supported"]
    assert report["rows"][0]["days_until_sunset"] == -26
    assert report["summary"]["deprecated_count"] == 4
    assert json.loads(render_source_api_deprecation_report_json(report))["kind"] == "max.source_api_deprecation_report"
