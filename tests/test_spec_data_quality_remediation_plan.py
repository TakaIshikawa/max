from __future__ import annotations

from max.spec.data_quality_remediation_plan import KIND, SCHEMA_VERSION, generate_data_quality_remediation_plan


def test_data_quality_remediation_plan_sorts_customer_impact_and_severity() -> None:
    plan = generate_data_quality_remediation_plan(
        {
            "project": {"title": "Customer Analytics"},
            "metadata": {
                "data_quality_remediation": {
                    "datasets": ["events", "accounts"],
                    "owners": {"events": "analytics"},
                    "findings": [
                        {"name": "internal label typo", "severity": "low", "dataset": "accounts"},
                        {"name": "missing paid events", "severity": "high", "dataset": "events", "customer_impacting": True},
                        {"name": "duplicate account rows", "severity": "critical", "dataset": "accounts"},
                    ],
                }
            },
        }
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert [item["finding"] for item in plan["remediation_workstreams"]] == [
        "missing paid events",
        "duplicate account rows",
        "internal label typo",
    ]
    assert plan["remediation_workstreams"][0]["owner"] == "analytics"


def test_data_quality_remediation_plan_defaults_dataset_and_finding() -> None:
    plan = generate_data_quality_remediation_plan({})

    assert plan["affected_assets"] == [{"id": "AS1", "dataset": "primary dataset", "owner": "data_owner", "evidence_reference_ids": []}]
    assert plan["remediation_workstreams"][0]["dataset"] == "primary dataset"
    assert plan["remediation_workstreams"][0]["finding"] == "data quality review pending"
    assert plan["exit_criteria"][0]["criterion"] == "All high and customer-impacting findings are closed with reviewer signoff."


def test_data_quality_remediation_plan_converts_metrics_to_validation_checks() -> None:
    plan = generate_data_quality_remediation_plan(
        {
            "findings": [{"name": "null account ids", "severity": "medium"}],
            "metrics": [{"name": "null account id rate", "operator": "<=", "threshold": "0.1%"}],
            "evidence": {"signal_ids": ["dq-1"]},
        }
    )

    assert plan["validation_checks"][1]["type"] == "metric_threshold"
    assert plan["validation_checks"][1]["check"] == "Confirm null account id rate <= 0.1%."
    assert plan["exit_criteria"] == [
        {
            "id": "EC1",
            "criterion": "null account id rate remains <= 0.1% for the agreed validation window.",
            "owner": "data_owner",
            "evidence_reference_ids": ["EV1"],
        }
    ]
