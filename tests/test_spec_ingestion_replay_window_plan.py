from __future__ import annotations

from max.spec.ingestion_replay_window_plan import generate_ingestion_replay_window_plan


def test_replay_windows_group_by_source_and_order_chronologically() -> None:
    plan = generate_ingestion_replay_window_plan({"windows": [{"source": "b", "start": "2026-01-02T00:00:00Z", "end": "2026-01-03T00:00:00Z"}, {"source": "a", "start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"}]})
    assert [row["source"] for row in plan["replay_windows"]] == ["a", "b"]
    assert plan["source_groups"][0]["source"] == "a"


def test_large_or_overlapping_windows_get_risk_guidance() -> None:
    plan = generate_ingestion_replay_window_plan({"windows": [{"source": "a", "start": "2026-01-01T00:00:00Z", "end": "2026-01-03T00:00:00Z"}, {"source": "a", "start": "2026-01-02T00:00:00Z", "end": "2026-01-04T00:00:00Z"}]})
    assert all(row["overlap"] for row in plan["replay_windows"])
    assert plan["risk_guidance"]


def test_empty_replay_requests_return_no_replay_plan() -> None:
    plan = generate_ingestion_replay_window_plan({})
    assert plan["summary"]["status"] == "no_replay_needed"
    assert plan["validation_checks"]
