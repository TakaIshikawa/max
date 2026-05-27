from __future__ import annotations

from max.spec.production_access_request_plan import generate_production_access_request_plan


def test_production_access_request_plan_complete_metadata_has_checks() -> None:
    plan = generate_production_access_request_plan({"metadata": {"production_access_request": {"requester": "Nia", "systems": ["billing"], "business_justification": "debug incident", "duration": "2 hours", "approvers": ["manager"], "access_level": "read-only"}}})

    assert plan["blockers"] == []
    assert plan["recertification"]["recertification_date"] == "at access expiry"
    assert plan["approvers"][0]["name"] == "manager"


def test_production_access_request_plan_missing_required_fields_create_blockers() -> None:
    plan = generate_production_access_request_plan({"metadata": {"production_access_request": {}}})

    assert [row["name"] for row in plan["blockers"]] == ["missing requester", "missing approver", "missing duration", "missing business justification"]


def test_production_access_request_plan_privileged_access_has_stronger_checks() -> None:
    plan = generate_production_access_request_plan({"metadata": {"production_access_request": {"access_level": "admin"}}})

    assert plan["summary"]["privileged_access"] is True
    assert "session recording" in plan["validation_checks"][0]
