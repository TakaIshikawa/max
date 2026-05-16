from __future__ import annotations

from max.spec.data_quality_monitoring_plan import generate_data_quality_monitoring_plan


def test_data_quality_monitoring_plan_covers_required_sections() -> None:
    plan = generate_data_quality_monitoring_plan(
        {
            "project": {"title": "Revenue Warehouse"},
            "data": {
                "critical_datasets": ["invoices", "accounts"],
                "business_criticality": "high",
                "data_sensitivity": "restricted PII",
                "quality_dimensions": ["validity", "freshness"],
            },
            "operations": {
                "alert_routing": ["#data-ops", "pagerduty"],
                "remediation_playbooks": ["playbook://warehouse-backfill"],
            },
            "evidence": {"signal_ids": ["dq-1"]},
        }
    )

    assert plan["kind"] == "max.data_quality_monitoring_plan"
    assert plan["summary"]["monitoring_priority"] == "critical"
    assert plan["datasets"] == ["accounts", "invoices"]
    assert plan["dimensions"] == ["freshness", "validity"]
    assert {"datasets", "dimensions", "checks", "thresholds", "alerts", "remediation", "evidence"} <= set(plan)
    assert plan["alerts"]["notify_after_minutes"] == 5
    assert plan["evidence"] == ["signal:dq-1"]


def test_data_quality_monitoring_plan_defaults_missing_inputs() -> None:
    plan = generate_data_quality_monitoring_plan({})

    assert plan["summary"]["title"] == "Unknown"
    assert plan["datasets"] == ["Unknown"]
    assert plan["summary"]["monitoring_priority"] == "low"
    assert plan["alerts"]["routing"] == []
    assert plan["remediation"] == []


def test_data_quality_monitoring_plan_is_deterministic() -> None:
    payload = {"data": {"critical_datasets": ["z", "a", "z"], "business_criticality": "medium"}}

    assert generate_data_quality_monitoring_plan(payload) == generate_data_quality_monitoring_plan(payload)
    assert generate_data_quality_monitoring_plan(payload)["datasets"] == ["a", "z"]
