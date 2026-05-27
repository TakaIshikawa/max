from __future__ import annotations

import json

from max.exports.model_eval_regression_report import (
    build_model_eval_regression_report,
    render_model_eval_regression_report_json,
)


def test_model_eval_regression_report_flags_regressions_and_improvements() -> None:
    report = build_model_eval_regression_report(
        {"accuracy": 0.92, "latency_score": 0.8, "toxicity": 0.97},
        {"accuracy": 0.86, "latency_score": 0.87, "toxicity": 0.95},
        threshold=0.03,
    )

    by_metric = {row["metric"]: row for row in report["metrics"]}
    assert by_metric["accuracy"]["is_regression"] is True
    assert by_metric["accuracy"]["regression_amount"] == 0.06
    assert by_metric["latency_score"]["status"] == "improved"
    assert by_metric["toxicity"]["status"] == "stable"
    assert report["summary"]["regression_count"] == 1


def test_model_eval_regression_report_surfaces_missing_metrics() -> None:
    report = build_model_eval_regression_report({"accuracy": 0.9}, {"faithfulness": 0.8})

    assert {row["status"] for row in report["gaps"]} == {"missing_baseline", "missing_current"}
    assert {row["metric"] for row in report["gaps"]} == {"accuracy", "faithfulness"}


def test_model_eval_regression_report_orders_largest_regressions_first() -> None:
    report = build_model_eval_regression_report(
        {"b": 1.0, "a": 1.0, "c": 1.0},
        {"b": 0.8, "a": 0.7, "c": 0.8},
        threshold=0.01,
    )

    assert [row["metric"] for row in report["metrics"]] == ["a", "b", "c"]


def test_model_eval_regression_report_empty_input_and_metadata_are_json_serializable() -> None:
    report = build_model_eval_regression_report({}, {}, metadata={"model": "candidate", "tags": ["eval"]})

    assert report["summary"]["metric_count"] == 0
    assert report["metadata"] == {"model": "candidate", "tags": ["eval"]}
    assert json.loads(render_model_eval_regression_report_json(report))["kind"] == "max.model_eval_regression_report"
