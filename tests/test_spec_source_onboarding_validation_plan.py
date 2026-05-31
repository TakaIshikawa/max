from __future__ import annotations

import json

from max.spec.source_onboarding_validation_plan import generate_source_onboarding_validation_plan


def test_source_onboarding_validation_plan_flags_missing_credentials_and_categories() -> None:
    plan = generate_source_onboarding_validation_plan(
        {"source": "jobs", "owner": "ingest", "credentials": ["token"], "provided_credentials": [], "categories": ["jobs"], "normalization_fields": ["id"], "sample_queries": ["python"]},
        {"required_categories": ["jobs", "funding"], "normalization_fields": ["id", "url"]},
    )

    assert plan["source_identity"] == {"source": "jobs", "owner": "ingest"}
    assert "missing credential: token" in plan["blockers"]
    assert "missing profile category: funding" in plan["blockers"]
    assert [field["field"] for field in plan["normalization_contract"]] == ["id", "url"]
    json.dumps(plan)
