from __future__ import annotations

import json

from max.exports import build_publication_destination_latency_report
from max.exports.publication_destination_latency_report import render_publication_destination_latency_report_json, render_publication_destination_latency_report_markdown


def test_publication_destination_latency_accepts_aliases_and_sorts_breaches() -> None:
    rows = build_publication_destination_latency_report(
        [
            {"destination": "slack", "latency_ms": 1000},
            {"destination": "jira", "duration_ms": 70000},
            {"channel": "email", "started_at": "2026-05-27T00:00:00+00:00", "completed_at": "2026-05-27T00:00:02+00:00"},
        ]
    )

    assert rows[0]["destination"] == "jira"
    assert rows[0]["timeout_count"] == 1
    assert rows[0]["sla_status"] == "breach"
    assert rows[1]["p50_latency_ms"] == 2000


def test_publication_destination_latency_renderers() -> None:
    rows = build_publication_destination_latency_report([{"latency_ms": 5}])

    assert json.loads(render_publication_destination_latency_report_json(rows))[0]["attempt_count"] == 1
    assert "| Destination | Attempts |" in render_publication_destination_latency_report_markdown(rows)
