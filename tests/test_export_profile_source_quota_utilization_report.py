from __future__ import annotations

from max.exports.profile_source_quota_utilization_report import (
    generate_profile_source_quota_utilization_report,
)


def test_profile_source_quota_utilization_groups_usage_and_sorts_by_utilization() -> None:
    report = generate_profile_source_quota_utilization_report(
        [
            {"profile": "growth", "source": "github", "used": 30},
            {"profile": "growth", "source": "github", "count": 20},
            {"profile": "core", "source_adapter": "rss", "tokens": 90},
            {"profile": "core", "source": "hn", "usage": 5},
            ["malformed"],
        ],
        {
            ("growth", "github"): 100,
            "core:rss": 100,
            "core": {"hn": 10},
        },
    )

    assert [row["profile"] + "/" + row["source"] for row in report["quota_rows"]] == [
        "core/rss",
        "core/hn",
        "growth/github",
    ]
    assert report["quota_rows"][0]["utilization_pct"] == 90.0
    assert report["quota_rows"][1]["remaining"] == 5
    assert report["quota_rows"][2] == {
        "profile": "growth",
        "source": "github",
        "used": 50,
        "quota": 100,
        "remaining": 50,
        "utilization_pct": 50.0,
        "quota_missing": False,
    }


def test_profile_source_quota_utilization_represents_missing_quota() -> None:
    report = generate_profile_source_quota_utilization_report(
        [{"profile_id": "p1", "adapter": "postman", "used": 7}],
        {},
    )

    assert report["summary"]["missing_quota_count"] == 1
    assert report["quota_rows"][0]["quota"] is None
    assert report["quota_rows"][0]["remaining"] is None
    assert report["quota_rows"][0]["utilization_pct"] is None
    assert report["quota_rows"][0]["quota_missing"] is True
