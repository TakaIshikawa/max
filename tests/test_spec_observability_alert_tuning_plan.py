from __future__ import annotations

from max.spec.observability_alert_tuning_plan import (
    generate_observability_alert_tuning_plan,
    render_observability_alert_tuning_plan_markdown,
)


def test_alert_tuning_sorts_by_severity_and_classifies_noisy_alerts() -> None:
    plan = generate_observability_alert_tuning_plan(
        {
            "project": {"title": "Payments Observability"},
            "alerts": [
                {"name": "low_queue_depth", "severity": "info", "page_count": 1, "actionable_rate": 0.9, "owner": "platform"},
                {"name": "api_5xx", "severity": "critical", "page_count": 14, "actionable_rate": 0.1, "owner": "sre"},
                {"name": "latency_p95", "severity": "warning", "page_count": 3, "actionable_rate": 0.8, "owner": "api"},
            ],
        }
    )

    assert [row["name"] for row in plan["alert_classifications"]] == ["api_5xx", "latency_p95", "low_queue_depth"]
    assert plan["noisy_alerts"][0]["name"] == "api_5xx"
    assert plan["threshold_updates"][0]["recommended_change"] == "threshold_update"
    assert plan["summary"]["noisy_alert_count"] == 1


def test_alert_tuning_deduplicates_alerts_stably() -> None:
    plan = generate_observability_alert_tuning_plan(
        {
            "alerts": [
                {"name": "api_5xx", "severity": "warning", "page_count": 12},
                {"name": "api_5xx", "severity": "critical", "page_count": 4},
            ]
        }
    )

    assert [row["name"] for row in plan["alert_classifications"]] == ["api_5xx"]
    assert plan["alert_classifications"][0]["severity"] == "critical"
    assert plan["summary"]["alert_count"] == 1


def test_alert_tuning_markdown_sections_are_stable() -> None:
    plan = generate_observability_alert_tuning_plan(
        {
            "project": {"title": "Payments Observability"},
            "alerts": [{"name": "api_5xx", "severity": "critical", "page_count": 14, "actionable_rate": 0.1}],
            "missing_alerts": [{"name": "checkout_success_rate", "severity": "critical", "description": "No alert for failed checkout attempts."}],
            "rollout_safeguards": ["shadow tuned threshold for seven days"],
            "evidence": {"signal_ids": ["alert-1"]},
        }
    )

    first = render_observability_alert_tuning_plan_markdown(plan)
    second = render_observability_alert_tuning_plan_markdown(plan)

    assert first == second
    assert first.startswith("# Payments Observability Observability Alert Tuning Plan")
    assert "## Noisy Alerts" in first
    assert "## Coverage Gaps" in first
    assert "No alert for failed checkout attempts." in first
    assert "## Threshold Updates" in first
    assert "## Rollout Validation" in first
    assert "signal:alert-1" in first
