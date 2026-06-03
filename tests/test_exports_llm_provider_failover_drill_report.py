from __future__ import annotations

from max.exports.llm_provider_failover_drill_report import generate_llm_provider_failover_drill_report


def test_llm_provider_failover_drill_report_classifies_provider_risk() -> None:
    report = generate_llm_provider_failover_drill_report(
        [
            {"provider": "openai", "fallback_provider": "anthropic", "last_drill_at": "2026-05-25T00:00:00Z", "outcome": "failed", "latency_ms": 1000, "error": "timeout"},
            {"provider": "anthropic", "fallback_provider": "openai", "outcome": "success"},
            {"provider": "google", "fallback_provider": "openai", "last_drill_at": "2026-01-01T00:00:00Z", "outcome": "success", "latency_ms": 1000},
            {"provider": "mistral", "fallback_provider": "openai", "last_drill_at": "2026-05-30T00:00:00Z", "outcome": "success", "latency_ms": 9000},
            {"provider": "cohere", "fallback_provider": "openai", "last_drill_at": "2026-05-30T00:00:00Z", "outcome": "passed", "latency_ms": 500},
        ],
        as_of="2026-06-01T00:00:00Z",
        stale_after_days=90,
        slow_latency_ms=5000,
    )

    assert report["summary"] == {
        "provider_count": 5,
        "risky_provider_count": 4,
        "failed_drill_count": 1,
        "stale_drill_count": 1,
    }
    assert [row["provider"] for row in report["provider_rows"]] == ["openai", "anthropic", "google", "mistral", "cohere"]
    assert report["provider_rows"][1]["days_since_drill"] is None
    assert report["provider_rows"][3]["reason"] == "slow_failover"
    assert report["provider_rows"][4]["outcome"] == "success"
