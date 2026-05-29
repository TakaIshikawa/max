from __future__ import annotations

import json

from max.exports import generate_cache_key_churn_report
from max.exports.cache_key_churn_report import render_cache_key_churn_report_json


def test_cache_key_churn_report_flags_high_churn() -> None:
    report = generate_cache_key_churn_report(
        [
            {"namespace": "profiles", "key": "user:1"},
            {"namespace": "profiles", "key": "user:2"},
            {"namespace": "profiles", "key": "user:3"},
            {"namespace": "profiles", "key": "user:4"},
        ],
        churn_threshold=0.3,
    )

    assert report["summary"]["action_required_count"] == 1
    assert report["namespace_rows"][0]["namespace"] == "profiles"
    assert report["namespace_rows"][0]["churn_ratio"] == 1.0
    assert report["namespace_rows"][0]["action_required"] is True
    json.loads(render_cache_key_churn_report_json(report))


def test_cache_key_churn_report_marks_stable_namespace() -> None:
    report = generate_cache_key_churn_report(
        [
            {"namespace": "catalog", "key": "page:1"},
            {"namespace": "catalog", "key": "page:1"},
            {"namespace": "catalog", "key": "page:1"},
            {"namespace": "catalog", "key": "page:2"},
        ],
        churn_threshold=0.5,
    )

    row = report["namespace_rows"][0]
    assert row["unique_key_count"] == 2
    assert row["total_events"] == 4
    assert row["churn_ratio"] == 0.5
    assert row["action_required"] is False


def test_cache_key_churn_report_uses_sparse_fallback_labels() -> None:
    report = generate_cache_key_churn_report([{}, {"cache_namespace": "derived", "cache_key": "k1"}])

    assert [row["namespace"] for row in report["namespace_rows"]] == ["derived", "unknown-namespace"]
    assert report["namespace_rows"][1]["unique_key_count"] == 1


def test_cache_key_churn_report_has_deterministic_ordering() -> None:
    report = generate_cache_key_churn_report(
        [
            {"namespace": "zeta", "key": "a"},
            {"namespace": "alpha", "key": "a"},
            {"namespace": "alpha", "key": "b"},
            {"namespace": "zeta", "key": "a"},
        ],
        churn_threshold=0.9,
    )

    assert [row["namespace"] for row in report["namespace_rows"]] == ["alpha", "zeta"]
