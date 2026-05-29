from __future__ import annotations

import json

from max.exports import build_source_cost_efficiency_report
from max.exports.source_cost_efficiency_report import (
    render_source_cost_efficiency_report_json,
    render_source_cost_efficiency_report_markdown,
)


def test_source_cost_efficiency_report_normalizes_aliases_and_rates() -> None:
    report = build_source_cost_efficiency_report(
        [
            {"source_adapter": "github", "fetch_cost_usd": "4", "tokens": "1000", "signals": 8, "accepted_signals": 4, "insights": 2, "ideas": 1},
            {"adapter": "github", "spend_usd": 2, "total_tokens": 500, "signal_count": 2, "accepted_signal_count": 1, "insight_count": 1, "idea_count": 0},
            {"source": "expensive", "cost_usd": 12, "token_count": 10, "signal_count": 5, "accepted_signal_count": 1},
            {"source": "empty", "usd_cost": 7, "token_spend": 20, "emitted_signal_count": 0, "accepted_count": 0},
        ]
    )

    rows = {row["source"]: row for row in report["efficiency_rows"]}
    assert rows["github"]["cost_usd"] == 6
    assert rows["github"]["token_count"] == 1500
    assert rows["github"]["signal_count"] == 10
    assert rows["github"]["accepted_signal_count"] == 5
    assert rows["github"]["cost_per_signal"] == 0.6
    assert rows["github"]["cost_per_accepted_signal"] == 1.2
    assert rows["github"]["insight_yield_rate"] == 0.6
    assert rows["github"]["idea_yield_rate"] == 0.2
    assert rows["github"]["efficiency_status"] == "efficient"
    assert rows["expensive"]["efficiency_status"] == "inefficient"
    assert rows["empty"]["cost_per_signal"] == 0.0
    assert rows["empty"]["cost_per_accepted_signal"] == 0.0
    assert rows["empty"]["efficiency_status"] == "no_yield"
    assert report["summary"]["source_count"] == 3
    assert json.loads(render_source_cost_efficiency_report_json(report))["kind"] == "max.source_cost_efficiency_report"
    assert "github: $1.2000/accepted signal" in render_source_cost_efficiency_report_markdown(report)
