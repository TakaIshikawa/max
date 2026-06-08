from __future__ import annotations

from max.exports import generate_source_adapter_pagination_anomaly_report as exported
from max.exports.source_adapter_pagination_anomaly_report import generate_source_adapter_pagination_anomaly_report


def test_pagination_anomaly_report_flags_repeated_cursors_empty_streaks_and_skips() -> None:
    report = generate_source_adapter_pagination_anomaly_report(
        [
            {"adapter": "rss", "profile": "growth", "page": 1, "cursor": "a", "fetched_count": 10},
            {"adapter": "rss", "profile": "growth", "page": 2, "cursor": "a", "fetched_count": 0},
            {"adapter": "rss", "profile": "growth", "page": 4, "cursor": "c", "fetched_count": 0},
            {"adapter": "rss", "profile": "growth", "page": 5, "cursor": "d", "fetched_count": 0},
        ],
        repeated_cursor_threshold=1,
        empty_streak_threshold=3,
        skipped_range_threshold=1,
    )

    assert exported is generate_source_adapter_pagination_anomaly_report
    row = report["rows"][0]
    assert row["status"] == "anomalous"
    assert row["repeated_cursors"] == [{"cursor": "a", "count": 2}]
    assert row["repeated_cursor_count"] == 1
    assert row["max_empty_page_streak"] == 3
    assert row["skipped_ranges"] == [{"from_page": 3, "to_page": 3, "missing_count": 1}]


def test_pagination_anomaly_report_groups_and_orders_deterministically() -> None:
    report = generate_source_adapter_pagination_anomaly_report(
        [
            {"adapter": "zeta", "profile": "ops", "page": 1, "cursor": "z1", "fetched_count": 2},
            {"adapter": "alpha", "profile": "ops", "page": 1, "cursor": "a1", "fetched_count": 0},
            {"adapter": "alpha", "profile": "ops", "page": 2, "cursor": "a2", "fetched_count": 3},
        ]
    )

    assert [(row["adapter"], row["profile"], row["status"]) for row in report["rows"]] == [
        ("alpha", "ops", "ok"),
        ("zeta", "ops", "ok"),
    ]
    assert report["summary"]["pair_count"] == 2


def test_pagination_anomaly_report_marks_subthreshold_signals_as_watch() -> None:
    report = generate_source_adapter_pagination_anomaly_report(
        [
            {"adapter": "api", "profile": "default", "page": 1, "cursor": "a", "fetched_count": 1},
            {"adapter": "api", "profile": "default", "page": 2, "cursor": "a", "fetched_count": 0},
        ],
        repeated_cursor_threshold=3,
        empty_streak_threshold=3,
    )

    assert report["rows"][0]["status"] == "watch"
    assert report["summary"]["watch_count"] == 1
