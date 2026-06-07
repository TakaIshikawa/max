from __future__ import annotations

from max.exports import generate_idea_spec_conversion_funnel_report


def test_idea_spec_conversion_funnel_groups_by_profile() -> None:
    report = generate_idea_spec_conversion_funnel_report(
        [
            {"profile": "clinical", "stage": "published"},
            {"profile": "clinical", "stage": "approved"},
            {"profile": "aero", "evaluated": True},
        ],
        minimum_conversion_rate=0.4,
    )

    assert report["rows"][0]["profile"] == "aero"
    assert report["rows"][0]["status"] == "below_target"
    clinical = report["rows"][1]
    assert clinical["generated_count"] == 2
    assert clinical["evaluated_count"] == 2
    assert clinical["approved_count"] == 2
    assert clinical["spec_generated_count"] == 1
    assert clinical["published_count"] == 1
    assert clinical["conversion_rate"] == 0.5
    assert clinical["status"] == "healthy"


def test_idea_spec_conversion_funnel_empty() -> None:
    assert generate_idea_spec_conversion_funnel_report([])["summary"]["profile_count"] == 0
