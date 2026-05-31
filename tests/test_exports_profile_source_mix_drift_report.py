from __future__ import annotations

from max.exports.profile_source_mix_drift_report import generate_profile_source_mix_drift_report


def test_profile_source_mix_drift_calculates_actual_expected_and_severity() -> None:
    report = generate_profile_source_mix_drift_report(
        [{"profile": "p1", "source": "github"} for _ in range(9)] + [{"profile": "p1", "source": "hn"}],
        {"p1": {"github": 0.5, "hn": 0.5}},
        min_sample_size=5,
        warn_threshold=0.2,
        critical_threshold=0.35,
    )

    row = report["rows"][0]
    assert row["source"] == "github"
    assert row["expected_share"] == 0.5
    assert row["actual_share"] == 0.9
    assert row["severity"] == "critical"


def test_profile_source_mix_drift_marks_small_samples_informational() -> None:
    report = generate_profile_source_mix_drift_report([{"profile": "p1", "source": "github"}], {"p1": {"github": 0.1}}, min_sample_size=5)

    assert report["rows"][0]["severity"] == "info"
