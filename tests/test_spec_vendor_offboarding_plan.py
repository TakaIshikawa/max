from __future__ import annotations

import pytest

from max.spec.vendor_offboarding_plan import generate_vendor_offboarding_plan


def test_vendor_offboarding_plan_includes_ordered_phases() -> None:
    plan = generate_vendor_offboarding_plan(_spec())

    assert plan["summary"]["vendor"] == "Legacy CRM"
    assert set(plan) >= {"dependency_review", "credential_revocation", "data_return_deletion", "communication_steps", "evidence_capture", "final_approval"}
    assert plan["final_approval"][0]["status"] == "blocked"


def test_vendor_offboarding_plan_surfaces_blockers() -> None:
    plan = generate_vendor_offboarding_plan(_spec())

    assert "active api key" in [item["name"] for item in plan["blockers"]]
    assert "customer export retained" in [item["name"] for item in plan["blockers"]]
    assert "billing workflow" in [item["name"] for item in plan["blockers"]]
    assert "missing owner attestations" in [item["name"] for item in plan["blockers"]]


def test_vendor_offboarding_plan_allows_ready_final_approval_without_blockers() -> None:
    spec = _spec()
    spec["metadata"]["vendor_offboarding"].update({"credentials": ["revoked key"], "retained_data": [], "downstream_dependencies": [], "owner_attestations": ["security signed"]})

    assert generate_vendor_offboarding_plan(spec)["final_approval"][0]["status"] == "ready"


def test_vendor_offboarding_plan_requires_vendor_and_owner() -> None:
    with pytest.raises(ValueError, match="vendor name"):
        generate_vendor_offboarding_plan({"metadata": {"vendor_offboarding": {"owner": "ops"}}})


def test_vendor_offboarding_plan_is_deterministic() -> None:
    assert generate_vendor_offboarding_plan(_spec()) == generate_vendor_offboarding_plan(_spec())


def _spec() -> dict:
    return {
        "metadata": {
            "vendor_offboarding": {
                "vendor_name": "Legacy CRM",
                "owner": "vendor owner",
                "credentials": ["revoked token", "active api key"],
                "retained_data": ["customer export retained"],
                "downstream_dependencies": ["billing workflow"],
                "owner_attestations": [],
            }
        }
    }
