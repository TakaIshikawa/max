from __future__ import annotations

from copy import deepcopy

from max.exports import generate_profile_source_mix_shift_report as exported
from max.exports.profile_source_mix_shift_report import generate_profile_source_mix_shift_report


def test_profile_source_mix_shift_report_compares_without_mutating_inputs() -> None:
    payload = {"baseline": {"core": {"docs": 50, "issues": 50}}, "observed": {"core": {"docs": 60, "issues": 40}}}
    original = deepcopy(payload)
    report = generate_profile_source_mix_shift_report(payload)

    assert exported is generate_profile_source_mix_shift_report
    assert payload == original
    assert report["rows"][0]["source_shifts"] == {"docs": 10.0, "issues": -10.0}
    assert report["rows"][0]["total_drift"] == 10.0
    assert report["rows"][0]["status"] == "shifted"


def test_profile_source_mix_shift_report_surfaces_missing_sources() -> None:
    report = generate_profile_source_mix_shift_report(
        {"baseline": [{"profile": "core", "source": "docs", "count": 10}], "observed": []}
    )

    row = report["rows"][0]
    assert row["missing_source_count"] == 1
    assert row["missing_sources"] == ["docs"]
    assert row["status"] == "imbalanced"
