from __future__ import annotations

import json

from max.analysis import generate_design_brief_operational_metrics_review_plan as exported_generate
from max.analysis.design_brief_operational_metrics_review_plan import (
    KIND,
    SCHEMA_VERSION,
    generate_design_brief_operational_metrics_review_plan,
)


def test_operational_metrics_review_plan_emits_sorted_metric_rows() -> None:
    brief = {
        "metadata": {
            "operational_metrics_review_plan": {
                "review_cadence": "weekly",
                "kpis": [
                    {"metric": "Webhook failures", "baseline": "2%", "target": "<1%", "owner": "ops", "evidence": ["grafana"]},
                    {"metric": "API latency", "baseline": "250ms", "target_threshold": "200ms", "alert_owner": "sre", "evidence": ["apm"]},
                ],
            }
        }
    }

    plan = generate_design_brief_operational_metrics_review_plan(brief)

    assert plan == generate_design_brief_operational_metrics_review_plan(brief)
    assert json.loads(json.dumps(plan)) == plan
    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert [row["metric"] for row in plan["metric_reviews"]] == ["API latency", "Webhook failures"]
    assert plan["metric_reviews"][0]["baseline"] == "250ms"
    assert plan["summary"]["readiness_status"] == "ready"
    assert exported_generate({})["kind"] == KIND


def test_operational_metrics_review_plan_reports_owner_threshold_and_cadence_gaps() -> None:
    plan = generate_design_brief_operational_metrics_review_plan(
        {"operational_metrics_review_plan": {"metrics": [{"name": "Queue depth"}]}}
    )

    assert plan["summary"]["readiness_status"] == "blocked"
    assert [gap["id"] for gap in plan["review_gaps"]] == [
        "queue_depth_missing_alert_owner",
        "queue_depth_missing_target_threshold",
        "queue_depth_missing_review_cadence",
    ]
