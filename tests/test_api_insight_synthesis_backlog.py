from __future__ import annotations

import json

from max.api.insight_synthesis_backlog import KIND, SCHEMA_VERSION, insight_synthesis_backlog_to_json


def test_insight_synthesis_backlog_derives_grouping_and_staleness() -> None:
    payload = {
        "signal_batches": [
            {"id": "b2", "source_id": "github", "profile_id": "growth", "signals_count": 3, "received_at": "2026-05-01T00:00:00Z", "estimated_tokens": 200, "blockers": ["missing evidence"]},
            {"batch_id": "b1", "source": "rss", "profile": "growth", "signal_count": 2, "created_at": "2026-05-20T00:00:00Z", "token_estimate": 100},
        ]
    }

    parsed = json.loads(insight_synthesis_backlog_to_json(payload, as_of="2026-05-21T00:00:00Z"))

    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == KIND
    assert parsed["summary"] == {"blocked_batches": 1, "estimated_tokens": 300, "total_batches": 2, "total_signals": 5}
    assert [row["batch_id"] for row in parsed["backlog_items"]] == ["b1", "b2"]
    assert parsed["by_source"] == [
        {"batch_count": 1, "signal_count": 3, "source": "github", "token_estimate": 200},
        {"batch_count": 1, "signal_count": 2, "source": "rss", "token_estimate": 100},
    ]
    assert parsed["by_profile"] == [{"batch_count": 2, "profile": "growth", "signal_count": 5, "token_estimate": 300}]
    assert parsed["stale_batches"]["0_1d"] == 1
    assert parsed["stale_batches"]["8_30d"] == 1
    assert parsed["blockers"] == [{"batch_id": "b2", "reasons": ["missing evidence"]}]
    assert parsed["token_estimates"]["total"] == 300
    assert insight_synthesis_backlog_to_json(payload, as_of="2026-05-21T00:00:00Z") == insight_synthesis_backlog_to_json({"signal_batches": list(reversed(payload["signal_batches"]))}, as_of="2026-05-21T00:00:00Z")


def test_insight_synthesis_backlog_honors_explicit_sections() -> None:
    parsed = json.loads(
        insight_synthesis_backlog_to_json(
            {
                "backlog_items": [{}],
                "summary": {"total_batches": 5},
                "by_source": [{"source": "manual", "batch_count": 2}],
                "by_profile": [{"profile": "ops", "signal_count": 3}],
                "stale_batches": [{"batch_id": "stale", "age_bucket": "over_30d"}],
                "blockers": [{"batch_id": "b", "reasons": ["quota"]}],
            }
        )
    )

    assert parsed["summary"]["total_batches"] == 5
    assert parsed["by_source"][0]["source"] == "manual"
    assert parsed["by_profile"][0]["profile"] == "ops"
    assert parsed["stale_batches"][0]["batch_id"] == "stale"
    assert parsed["blockers"][0]["reasons"] == ["quota"]
