from __future__ import annotations

from max.api import design_brief_go_to_market_to_json


def test_design_brief_go_to_market_renderer_returns_expected_sections() -> None:
    payload = design_brief_go_to_market_to_json(
        {
            "schema_version": "max.design_brief.go_to_market.v1",
            "kind": "max.design_brief.go_to_market_strategy",
            "design_brief": {"id": "brief-1", "title": "Workflow Launch"},
            "summary": {"segment_count": 1, "channel_count": 1, "messaging_count": 1},
            "market_segments": [{"id": "SEG01", "name": "Operators"}],
            "positioning_statements": [{"id": "POS01", "statement": "Faster ops"}],
            "distribution_channels": [{"id": "CH01", "name": "Direct sales"}],
            "key_messaging": [{"id": "MSG01", "message": "Reduce rework"}],
            "launch_timeline": [{"id": "T01", "milestone": "Pilot"}],
        }
    )

    assert payload["kind"] == "max.api.design_brief_go_to_market"
    assert payload["strategy"]["market_segments"][0]["name"] == "Operators"
    assert payload["channels"][0]["name"] == "Direct sales"
    assert payload["timeline"][0]["milestone"] == "Pilot"
    assert payload["metrics"] == {
        "segment_count": 1,
        "channel_count": 1,
        "messaging_count": 1,
        "timeline_milestone_count": 1,
    }
    assert payload["metadata"]["design_brief"]["id"] == "brief-1"
