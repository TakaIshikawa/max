from __future__ import annotations

import json

from max.exports.source_payload_parse_failure_report import build_source_payload_parse_failure_report, render_source_payload_parse_failure_report_json, render_source_payload_parse_failure_report_markdown


def test_source_payload_parse_failure_report_groups_and_preserves_reference() -> None:
    report = build_source_payload_parse_failure_report([
        {"source": "github", "endpoint": "/issues", "stage": "decode", "error": "JSON error", "failed_count": 2, "payload_id": "payload-1", "timestamp": "2026-05-26T01:00:00Z", "raw_payload": "ignored"},
        {"source": "github", "endpoint": "/issues", "stage": "decode", "error": "json decode", "failed_count": 3, "payload_id": "payload-2", "timestamp": "2026-05-26T02:00:00Z"},
        {"source": "slack", "endpoint": "/events", "stage": "schema", "error": "missing field", "failed_count": 1, "sample_ref": "payload-3"},
    ])

    assert report["summary"]["failed_count"] == 6
    assert report["failure_rows"][0]["failed_count"] == 5
    assert report["failure_rows"][0]["sample_payload_reference"] == "payload-1"
    assert "raw_payload" not in report["failure_rows"][0]
    assert json.loads(render_source_payload_parse_failure_report_json(report))["summary"]["row_count"] == 2
    assert "github /issues json_decode: 5 failed" in render_source_payload_parse_failure_report_markdown(report)
