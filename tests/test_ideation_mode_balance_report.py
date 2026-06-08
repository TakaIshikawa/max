from __future__ import annotations

from max.exports import generate_ideation_mode_balance_report as exported
from max.exports.ideation_mode_balance_report import generate_ideation_mode_balance_report


def test_ideation_mode_balance_report_compares_observed_to_targets() -> None:
    report = generate_ideation_mode_balance_report(
        [
            {"profile": "core", "ideation_mode": "direct", "count": 8},
            {"profile": "core", "ideation_mode": "refinement", "count": 2},
            {"profile": "growth", "ideation_mode": "direct", "count": 5},
            {"profile": "growth", "ideation_mode": "refinement", "count": 3},
            {"profile": "growth", "ideation_mode": "cross-domain", "count": 2},
        ],
        tolerance=0.05,
    )

    assert exported is generate_ideation_mode_balance_report
    assert report["summary"]["imbalanced_count"] == 1
    core = report["rows"][0]
    assert core["profile"] == "core"
    assert core["missing_modes"] == ["cross-domain"]
    assert "direct" in core["overrepresented_modes"]

