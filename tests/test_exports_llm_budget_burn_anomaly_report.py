from __future__ import annotations

from max.exports.llm_budget_burn_anomaly_report import generate_llm_budget_burn_anomaly_report


def test_groups_by_pipeline_stage() -> None:
    report = generate_llm_budget_burn_anomaly_report([{"stage": "synthesis", "cost": 1, "expected_cost": 1}, {"stage": "synthesis", "tokens": 100, "expected_tokens": 100}])
    assert report["rows"][0]["pipeline_stage"] == "synthesis"
    assert report["rows"][0]["observed_cost"] == 1.0
    assert report["rows"][0]["observed_tokens"] == 100


def test_variance_ratio_is_zero_safe_without_expected_budget() -> None:
    report = generate_llm_budget_burn_anomaly_report([{"stage": "embed", "cost": 5, "tokens": 1000}])
    assert report["rows"][0]["variance_ratio"] == 0.0
    assert report["rows"][0]["anomaly_risk"] == "low"


def test_rows_include_expected_fields_and_risk() -> None:
    report = generate_llm_budget_burn_anomaly_report([{"stage": "a", "observed_cost": 3, "expected_cost": 1, "observed_tokens": 120, "expected_tokens": 100}])
    row = report["rows"][0]
    assert {"observed_cost", "expected_cost", "observed_tokens", "expected_tokens", "variance_ratio", "anomaly_risk"} <= set(row)
    assert row["variance_ratio"] == 2.0
    assert row["anomaly_risk"] == "high"
