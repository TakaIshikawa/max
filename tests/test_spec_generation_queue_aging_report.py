from __future__ import annotations

import json

from max.exports import build_spec_generation_queue_aging_report
from max.exports.spec_generation_queue_aging_report import render_spec_generation_queue_aging_report_json, render_spec_generation_queue_aging_report_markdown


def test_spec_generation_queue_aging_filters_and_buckets() -> None:
    report = build_spec_generation_queue_aging_report(
        [
            {"idea_id": "old", "profile": "Core", "status": "approved", "approved_at": "2026-05-10T00:00:00+00:00"},
            {"idea_id": "done", "status": "approved", "spec_id": "sp1"},
            {"idea_id": "draft", "status": "draft"},
        ],
        reference_time="2026-05-27T00:00:00+00:00",
    )

    assert report["summary"]["queue_size"] == 1
    assert report["summary"]["age_buckets"]["15d+"] == 1
    assert report["queued_ideas"][0]["sla_breached"] is True
    assert "owner" in report["queued_ideas"][0]["missing_prerequisite_fields"]


def test_spec_generation_queue_aging_renderers() -> None:
    report = build_spec_generation_queue_aging_report([{"status": "approved"}])

    assert json.loads(render_spec_generation_queue_aging_report_json(report))["summary"]["queue_size"] == 1
    assert "| Idea | Profile |" in render_spec_generation_queue_aging_report_markdown(report)
