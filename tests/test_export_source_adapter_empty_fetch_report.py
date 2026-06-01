from __future__ import annotations

import json

from max.exports.source_adapter_empty_fetch_report import generate_source_adapter_empty_fetch_report


def test_report_treats_zero_fetched_count_as_empty_fetch() -> None:
    report = generate_source_adapter_empty_fetch_report(
        [
            {"adapter": "aws", "profile": "ml", "fetched_count": 0},
            {"adapter": "aws", "profile": "ml", "fetched_count": 3},
        ],
        empty_rate_threshold=0.5,
    )

    assert json.loads(json.dumps(report)) == report
    row = report["rows"][0]
    assert row["attempt_count"] == 2
    assert row["empty_attempt_count"] == 1
    assert row["empty_rate"] == 0.5
    assert row["flagged"] is True


def test_report_aggregates_by_adapter_and_profile() -> None:
    report = generate_source_adapter_empty_fetch_report(
        [
            {"adapter": "aws", "profile": "ml", "fetched_count": 0},
            {"adapter": "aws", "profile": "storage", "fetched_count": 0},
            {"adapter": "aws", "profile": "storage", "fetched_count": 2},
        ],
        empty_rate_threshold=0.6,
    )

    pairs = {(row["adapter"], row["profile"]): row for row in report["rows"]}
    assert pairs[("aws", "ml")]["empty_rate"] == 1.0
    assert pairs[("aws", "storage")]["empty_rate"] == 0.5
    assert report["summary"]["pair_count"] == 2


def test_report_flags_pairs_meeting_or_exceeding_threshold() -> None:
    report = generate_source_adapter_empty_fetch_report(
        [
            {"adapter": "zeta", "profile": "ops", "fetched_count": 0},
            {"adapter": "alpha", "profile": "ops", "fetched_count": 0},
            {"adapter": "beta", "profile": "ops", "fetched_count": 2},
        ],
        empty_rate_threshold=1.0,
    )

    assert [(row["adapter"], row["profile"]) for row in report["flagged_pairs"]] == [("alpha", "ops"), ("zeta", "ops")]
