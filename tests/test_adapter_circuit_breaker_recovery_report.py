from __future__ import annotations

import json

from max.exports.adapter_circuit_breaker_recovery_report import (
    KIND,
    build_adapter_circuit_breaker_recovery_report,
    render_adapter_circuit_breaker_recovery_report_json,
    render_adapter_circuit_breaker_recovery_report_markdown,
)


def test_adapter_circuit_breaker_recovery_report_sorts_by_action_severity_adapter_source() -> None:
    report = build_adapter_circuit_breaker_recovery_report(
        [
            {"adapter": "zendesk", "source": "tickets", "state": "closed"},
            {"adapter": "github", "source": "issues", "state": "half-open", "failed_probe_count": 4},
            {"adapter": "asana", "source": "tasks", "state": "open", "failed_probe_count": 1},
            {"adapter": "github", "source": "prs", "state": "open", "failed_probe_count": 2},
        ]
    )

    assert report["kind"] == KIND
    assert [row["adapter"] for row in report["adapter_states"]] == ["asana", "github", "github", "zendesk"]
    assert [row["source"] for row in report["recovery_actions"]] == ["tasks", "issues", "prs"]
    assert set(report) >= {
        "schema_version",
        "kind",
        "generated_at",
        "title",
        "summary",
        "adapter_states",
        "recovery_actions",
        "state_totals",
    }


def test_adapter_circuit_breaker_recovery_report_defaults_missing_fields() -> None:
    report = build_adapter_circuit_breaker_recovery_report({})

    row = report["adapter_states"][0]
    assert row["adapter"] == "adapter-1"
    assert row["source"] == "unknown-source"
    assert row["state"] == "closed"
    assert row["recovery_latency_seconds"] == 0.0
    assert row["failed_probe_count"] == 0
    assert row["requires_operator_action"] is False
    assert report["state_totals"] == [{"count": 1, "state": "closed"}]


def test_adapter_circuit_breaker_recovery_report_classifies_operator_actions() -> None:
    report = build_adapter_circuit_breaker_recovery_report(
        {
            "circuit_breakers": [
                {"adapter_name": "linear", "source_id": "bugs", "circuit_state": "half_open", "failed_probes": "3"},
                {"adapter": "slack", "source": "alerts", "state": "closed", "action_required": "true"},
            ]
        }
    )

    assert report["summary"]["requires_action_count"] == 2
    assert report["summary"]["failed_probe_count"] == 3
    assert [row["adapter"] for row in report["recovery_actions"]] == ["linear", "slack"]


def test_adapter_circuit_breaker_recovery_report_markdown_and_json_rendering() -> None:
    report = build_adapter_circuit_breaker_recovery_report(
        [{"adapter": "github", "source": "issues", "state": "open", "failed_probe_count": 2}]
    )

    markdown = render_adapter_circuit_breaker_recovery_report_markdown(report)
    assert "ACTION REQUIRED: github / issues is open" in markdown
    assert "- Requiring action: 1" in markdown

    rendered_json = render_adapter_circuit_breaker_recovery_report_json(report)
    assert rendered_json.endswith("\n")
    assert json.loads(rendered_json)["summary"]["open_count"] == 1
