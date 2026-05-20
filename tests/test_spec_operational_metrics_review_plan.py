from __future__ import annotations

import json

from max.spec import generate_operational_metrics_review_plan as exported_generator
from max.spec.operational_metrics_review_plan import KIND, SCHEMA_VERSION, generate_operational_metrics_review_plan


def test_operational_metrics_review_plan_uses_metric_hints() -> None:
    plan = generate_operational_metrics_review_plan(
        {
            "metadata": {
                "operational_metrics_review": {
                    "metrics": [{"name": "sync latency", "owner": "ops", "target": "< 5m", "threshold": "> 10m", "review_cadence": "daily"}],
                    "escalation_triggers": ["latency breach"],
                }
            }
        }
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["metric_inventory"][0]["name"] == "sync latency"
    assert plan["baseline_expectations"][0]["target"] == "< 5m"
    assert plan["alert_thresholds"][0]["threshold"] == "> 10m"
    assert plan["review_cadence"]["cadence"] == "daily"
    assert exported_generator({})["kind"] == KIND


def test_operational_metrics_review_plan_defaults_are_stable_and_json_serializable() -> None:
    first = generate_operational_metrics_review_plan({})
    second = generate_operational_metrics_review_plan({})

    assert first == second
    assert [item["name"] for item in first["metric_inventory"]] == ["activation rate", "reliability", "support volume"]
    assert first["escalation_triggers"]
    assert json.loads(json.dumps(first))["kind"] == KIND
