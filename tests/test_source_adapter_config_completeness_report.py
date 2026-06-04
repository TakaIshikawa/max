from __future__ import annotations

import json

from max.exports.source_adapter_config_completeness_report import (
    generate_source_adapter_config_completeness_report,
    render_source_adapter_config_completeness_report_json,
)


def test_complete_adapter_preserves_extra_config_keys() -> None:
    report = generate_source_adapter_config_completeness_report(
        [{"adapter": "github", "token": "ghp_123", "org": "acme", "extra": "kept"}],
        {"github": ["token", "org"]},
    )

    row = report["adapters"][0]
    assert report["summary"]["complete_count"] == 1
    assert row["complete"] is True
    assert row["config"]["extra"] == "kept"
    assert json.loads(render_source_adapter_config_completeness_report_json(report))["kind"] == "max.source_adapter_config_completeness_report"


def test_absent_none_and_blank_values_are_missing() -> None:
    report = generate_source_adapter_config_completeness_report(
        [{"adapter": "rss", "url": "", "token": None}],
        {"rss": ["url", "token", "owner"]},
    )

    row = report["adapters"][0]
    assert row["missing_keys"] == ["url", "token", "owner"]
    assert row["missing_key_count"] == 3
    assert report["summary"]["incomplete_count"] == 1


def test_worst_adapters_are_ordered_deterministically() -> None:
    report = generate_source_adapter_config_completeness_report(
        [
            {"adapter": "beta", "one": ""},
            {"adapter": "alpha"},
            {"adapter": "gamma", "one": "ok", "two": "ok"},
        ],
        {"alpha": ["one", "two"], "beta": ["one", "two"], "gamma": ["one", "two"]},
    )

    assert [row["adapter"] for row in report["adapters"]] == ["alpha", "beta", "gamma"]
    assert report["missing_key_counts"] == [
        {"adapter": "alpha", "missing_key_count": 2},
        {"adapter": "beta", "missing_key_count": 2},
    ]
