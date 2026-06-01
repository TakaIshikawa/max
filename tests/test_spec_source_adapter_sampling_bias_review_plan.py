from __future__ import annotations

from max.spec.source_adapter_sampling_bias_review_plan import generate_source_adapter_sampling_bias_review_plan


def test_sampling_bias_plan_marks_overrepresented_adapters() -> None:
    plan = generate_source_adapter_sampling_bias_review_plan({
        "metadata": {
            "source_adapter_sampling_bias": {
                "max_share": 0.4,
                "adapters": [
                    {"id": "b", "adapter": "blog", "sample_count": 70, "newest_signal_at": "2026-05-30T00:00:00Z"},
                    {"id": "f", "adapter": "forum", "sample_count": 30, "newest_signal_at": "2026-05-30T00:00:00Z"},
                ],
            }
        }
    })

    finding = plan["sampling_bias_findings"][0]
    assert finding["type"] == "overrepresented_source"
    assert finding["adapter"] == "blog"
    assert finding["severity"] == "high"


def test_sampling_bias_plan_actions_for_missing_segments_and_stale_samples() -> None:
    plan = generate_source_adapter_sampling_bias_review_plan({
        "metadata": {
            "source_adapter_sampling_bias": {
                "target_segments": ["enterprise", "oss"],
                "stale_after_days": 10,
                "as_of": "2026-06-01T00:00:00Z",
                "adapters": [
                    {"id": "docs", "adapter": "Docs", "sample_count": 20, "segments": ["oss"], "newest_signal_at": "2026-05-01T00:00:00Z"},
                ],
            }
        }
    })

    types = {item["type"] for item in plan["sampling_bias_findings"]}
    assert {"missing_target_segments", "stale_samples"} <= types
    actions = {item["type"]: item["action"] for item in plan["rebalance_actions"]}
    assert "missing segments" in actions["missing_target_segments"]
    assert "Refresh adapter ingestion" in actions["stale_samples"]


def test_sampling_bias_findings_sort_by_severity_adapter_and_id() -> None:
    plan = generate_source_adapter_sampling_bias_review_plan({
        "metadata": {
            "source_adapter_sampling_bias": {
                "max_share": 0.2,
                "min_volume": 10,
                "adapters": [
                    {"id": "z", "adapter": "Zeta", "sample_count": 1, "share": 0.1},
                    {"id": "b", "adapter": "Beta", "sample_count": 50, "share": 0.5},
                    {"id": "a", "adapter": "Alpha", "sample_count": 50, "share": 0.5},
                ],
            }
        }
    })

    assert [(item["severity"], item["adapter"], item["id"]) for item in plan["sampling_bias_findings"]] == [
        ("high", "Alpha", "a:overrepresented_source"),
        ("high", "Beta", "b:overrepresented_source"),
        ("low", "Zeta", "z:low_volume_adapter"),
    ]


def test_sampling_bias_empty_input_produces_baseline_monitoring_plan() -> None:
    plan = generate_source_adapter_sampling_bias_review_plan({})

    assert plan["sampling_bias_findings"] == []
    assert plan["rebalance_actions"] == [{"id": "SBA1", "type": "baseline_monitoring", "action": "Continue monitoring adapter sample mix against configured thresholds."}]
    assert plan["summary"]["adapter_count"] == 0
