from __future__ import annotations

from max.exports.insight_triangulation_strength_report import generate_insight_triangulation_strength_report


def test_insight_triangulation_strength_report_scores_sources() -> None:
    report = generate_insight_triangulation_strength_report(
        [
            {"insight_id": "strong", "evidence": [{"source": "crm"}, {"source": "docs"}, {"source": "survey"}]},
            {"insight_id": "weak", "evidence": [{"source": "crm"}]},
            {"insight_id": "empty", "evidence": []},
        ]
    )

    assert [row["insight_id"] for row in report["rows"]] == ["empty", "weak", "strong"]
    assert report["rows"][1]["triangulation_strength"] == 0.3333
    assert report["summary"]["weak_insights"] == 2
