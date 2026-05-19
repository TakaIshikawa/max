from __future__ import annotations

import csv
from io import StringIO

from max.spec.api_deprecation_plan import (
    API_DEPRECATION_PLAN_CSV_COLUMNS,
    API_DEPRECATION_PLAN_SCHEMA_VERSION,
    generate_api_deprecation_plan,
    render_api_deprecation_plan_csv,
    render_api_deprecation_plan_markdown,
)


def test_api_deprecation_plan_shape() -> None:
    plan = generate_api_deprecation_plan(_spec(["mobile-app"], 120))
    rows = list(csv.DictReader(StringIO(render_api_deprecation_plan_csv(plan))))

    assert plan["schema_version"] == API_DEPRECATION_PLAN_SCHEMA_VERSION
    assert plan["kind"] == "max.api_deprecation_plan"
    assert {"deprecated_endpoints", "known_consumers", "replacement_guidance", "notice_timeline", "compatibility_window", "monitoring", "extension_criteria", "evidence"} <= set(plan)
    assert plan["summary"]["endpoint_count"] == 2
    assert plan["summary"]["escalation_required"] is False
    assert "## Replacement Guidance" in render_api_deprecation_plan_markdown(plan)
    assert render_api_deprecation_plan_csv(plan).splitlines()[0] == ",".join(API_DEPRECATION_PLAN_CSV_COLUMNS)
    assert rows[0]["section"] == "deprecated_endpoints"


def test_api_deprecation_plan_escalates_unknown_consumers_or_short_notice() -> None:
    plan = generate_api_deprecation_plan(_spec([], 30))

    assert plan["summary"]["escalation_required"] is True
    assert plan["known_consumers"][0]["severity"] == "critical"
    assert plan["notice_timeline"][0]["severity"] == "high"


def _spec(consumers: list[str], notice_days: int) -> dict:
    return {"source": {"idea_id": "api-dep"}, "project": {"title": "API Deprecation"}, "api_deprecation": {"endpoints": ["/v1/orders", "/v1/customers"], "known_consumers": consumers, "replacement": "/v2/orders", "notice_days": notice_days}}
