from __future__ import annotations

import json

from max.api import evaluation_judge_disagreement_status_to_json


def test_evaluation_judge_disagreement_status_computes_rates_and_preserves_split() -> None:
    data = json.loads(evaluation_judge_disagreement_status_to_json({"evaluations": [{"profile": "core", "dimension": "quality", "judge_count": 10, "disagreement_count": 4, "score_stddev": 0.5, "recommendation_split": {"reject": 2, "approve": 8}}, {"profile": "core", "dimension": "novelty", "judge_count": 10, "disagreement_count": 2, "score_stddev": 1.2}, {"profile": "ops", "dimension": "risk", "judge_count": 0, "disagreement_count": 3}]}))
    assert data["summary"] == {"status": "critical", "dimension_count": 3, "unstable_dimension_count": 2, "critical_count": 1, "warning_count": 1, "max_disagreement_rate": 0.4}
    assert [row["dimension"] for row in data["evaluations"]] == ["quality", "novelty", "risk"]
    assert data["evaluations"][0]["recommendation_split"] == {"approve": 8, "reject": 2}
    assert data["evaluations"][2]["disagreement_rate"] == 0.0
