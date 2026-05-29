from __future__ import annotations

import json

from max.exports import generate_prompt_redaction_leak_report, render_prompt_redaction_leak_report_markdown
from max.exports.prompt_redaction_leak_report import render_prompt_redaction_leak_report_json


def test_prompt_redaction_leak_groups_and_escalates_sensitive_fields() -> None:
    report = generate_prompt_redaction_leak_report(
        [
            {"profile": "p1", "prompt_template": "reply", "field_name": "api_key", "redaction_failed": True, "seen_at": "2026-05-01"},
            {"profile": "p1", "prompt_template": "reply", "field_name": "api_key", "sensitive_token": "x", "seen_at": "2026-05-02"},
            {"profile": "p1", "prompt_template": "reply", "field_name": "nickname", "leaked": True},
        ]
    )
    assert report["rows"][0]["field_name"] == "api_key"
    assert report["rows"][0]["severity"] == "critical"
    assert report["rows"][0]["leak_count"] == 2
    assert "api_key" in render_prompt_redaction_leak_report_markdown(report)
    json.loads(render_prompt_redaction_leak_report_json(report))
