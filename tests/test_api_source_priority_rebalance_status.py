from __future__ import annotations

import json

from max.api import source_priority_rebalance_status_to_json


def test_source_priority_rebalance_status_clamps_aliases_and_summarizes() -> None:
    parsed = json.loads(source_priority_rebalance_status_to_json({"allocations": [{"source_id": "docs", "current_share": 1.2, "target_share": 0.7}, {"id": "news", "current_percentage": -0.1, "recommended_percentage": 0.2}, {"source": "forum", "share": 0.4, "recommended_share": 0.41}]}))

    assert parsed["schema_version"] == "max.api.source_priority_rebalance_status.v1"
    assert parsed["kind"] == "max.api.source_priority_rebalance_status"
    assert parsed["summary"] == {"decrease_count": 1, "hold_count": 1, "increase_count": 1, "source_count": 3, "status": "rebalance_required"}
    assert [row["source"] for row in parsed["top_rebalance_actions"]] == ["docs", "news", "forum"]
    assert parsed["sources"][0]["current_fetch_share"] == 1.0
    assert parsed["sources"][1]["recommended_fetch_share"] == 0.2
