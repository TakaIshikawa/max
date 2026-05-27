from __future__ import annotations

from max.spec.inference_latency_degradation_plan import generate_inference_latency_degradation_plan


def test_inference_latency_degradation_plan_flags_p95_and_p99_breaches() -> None:
    plan = generate_inference_latency_degradation_plan(
        {
            "project": {"title": "Chat Runtime"},
            "metadata": {
                "inference_latency": {
                    "model": "gpt-runtime",
                    "provider": "openai",
                    "affected_routes": ["/chat", "/summaries"],
                    "metrics": {"p50": 700, "p95": 3200, "p99": 8100},
                    "targets": {"p95": 2500, "p99": 6000},
                    "owners": ["ml-platform", "sre"],
                }
            },
        }
    )

    assert plan["summary"]["status"] == "breached"
    assert [finding["metric"] for finding in plan["breach_findings"]] == ["p95", "p99"]
    assert plan["latency_profile"]["affected_routes"] == ["/chat", "/summaries"]
    assert any(item["name"] == "Routing mitigation" for item in plan["mitigation"])
    assert any(item["name"] == "Cache fallback" for item in plan["mitigation"])
    assert any(item["name"] == "Model fallback" for item in plan["mitigation"])
    assert plan["owner_handoff"][0]["owner"] == "ml-platform"
    assert any(item["name"] == "Percentile latency alerts" for item in plan["monitoring_checks"])


def test_inference_latency_degradation_plan_uses_defaults_for_missing_metrics() -> None:
    plan = generate_inference_latency_degradation_plan({})

    assert plan["summary"]["status"] == "watch"
    assert plan["breach_findings"] == []
    assert plan["latency_profile"]["model"] == "primary inference model"
    assert plan["latency_profile"]["target_ms"]["p95"] == 2500
    assert plan["latency_profile"]["affected_routes"] == ["primary inference route"]
