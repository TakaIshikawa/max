from __future__ import annotations

import json

from max.api import idea_spec_conversion_funnel_status_to_json


def test_idea_spec_conversion_funnel_status_reports_counts_and_rate() -> None:
    data = json.loads(idea_spec_conversion_funnel_status_to_json({"generated_count": 20, "evaluated_count": 18, "approved_count": 8, "spec_generated_count": 6, "published_count": 5, "minimum_conversion_rate": 0.2}))

    assert data["status"] == "ok"
    assert data["generated_count"] == 20
    assert data["evaluated_count"] == 18
    assert data["approved_count"] == 8
    assert data["spec_generated_count"] == 6
    assert data["published_count"] == 5
    assert data["conversion_rate"] == 0.25


def test_idea_spec_conversion_funnel_status_warns_below_minimum_and_handles_empty() -> None:
    warning = json.loads(idea_spec_conversion_funnel_status_to_json({"generated_count": 10, "published_count": 1, "minimum_conversion_rate": 0.5}))
    empty = json.loads(idea_spec_conversion_funnel_status_to_json({}))

    assert warning["status"] == "warning"
    assert warning["conversion_rate"] == 0.1
    assert empty["status"] == "ok"
    assert empty["conversion_rate"] == 0.0
