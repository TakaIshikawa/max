from __future__ import annotations

from max.spec.benchmark_contamination_review_plan import (
    generate_benchmark_contamination_review_plan,
)


def test_benchmark_contamination_review_plan_covers_sources_methods_and_remediation() -> None:
    plan = generate_benchmark_contamination_review_plan(
        {
            "benchmarks": [
                {"benchmark": "support QA gold", "source": "human labels", "overlap_score": 0.02},
                {"benchmark": "billing red team", "source": "prompt fixtures", "overlap_score": 0.2},
            ],
            "risk_threshold": 0.1,
            "contamination_sources": ["training data", "prompt examples", "synthetic fixtures"],
            "detection_methods": ["hash and embedding overlap"],
            "sampling_plan": ["stratified 10% review"],
            "remediation_options": ["replace contaminated examples"],
            "benchmark_replacement": ["source fresh private examples"],
            "disclosure_steps": ["document affected benchmark"],
            "signoff": ["evaluation owner approval"],
        }
    )

    assert plan["title"] == "Benchmark Contamination Review Plan"
    assert set(plan) >= {
        "benchmarks",
        "contamination_sources",
        "detection_methods",
        "thresholds",
        "sampling_plan",
        "high_risk_callouts",
        "remediation_options",
        "benchmark_replacement",
        "disclosure_steps",
        "signoff",
    }
    assert [item["name"] for item in plan["benchmarks"]] == ["billing red team", "support QA gold"]
    assert plan["high_risk_callouts"][0]["benchmark"] == "billing red team"
    assert plan["remediation_options"][0]["name"] == "replace contaminated examples"
    assert plan["benchmark_replacement"][0]["name"] == "source fresh private examples"
    assert plan["disclosure_steps"][0]["name"] == "document affected benchmark"


def test_benchmark_contamination_review_plan_defaults_without_callouts() -> None:
    plan = generate_benchmark_contamination_review_plan({})

    assert plan["schema_version"] == "max.spec.benchmark_contamination_review_plan.v1"
    assert plan["summary"]["benchmark_count"] == 1
    assert plan["benchmarks"][0]["name"] == "evaluation benchmark"
    assert plan["high_risk_callouts"] == []
    assert plan["thresholds"][0]["name"] == "high-risk callout when overlap signal exceeds 0.05"
