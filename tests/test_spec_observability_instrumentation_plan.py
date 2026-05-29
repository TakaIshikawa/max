from __future__ import annotations

from max.spec import generate_observability_instrumentation_plan


def test_observability_instrumentation_plan_rich_inputs() -> None:
    plan = generate_observability_instrumentation_plan({"metadata": {"observability_instrumentation": {"service": "billing", "metrics": ["invoice latency"], "logs": ["invoice result"], "traces": ["payment span"], "alerts": ["burn alert"], "dashboards": ["billing overview"]}}})

    assert plan["summary"]["service"] == "billing"
    assert plan["metrics"][0]["name"] == "invoice latency"
    assert plan["logs"][0]["name"] == "invoice result"
    assert plan["traces"][0]["name"] == "payment span"
    assert plan["alerts"][0]["name"] == "burn alert"
    assert plan["dashboards"][0]["name"] == "billing overview"


def test_observability_instrumentation_plan_sparse_defaults() -> None:
    plan = generate_observability_instrumentation_plan({})

    assert plan["metrics"]
    assert plan["maintenance"]
    assert plan["verification"]
