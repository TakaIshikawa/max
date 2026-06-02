from __future__ import annotations

import pytest

from max.spec.publisher_destination_credential_compromise_plan import generate_publisher_destination_credential_compromise_plan


def _spec(scope: str = "critical") -> dict:
    return {
        "project": {"title": "Publisher incident"},
        "metadata": {
            "publisher_destination_credential_compromise": {
                "destination": "Partner webhook",
                "credential_id": "cred-live-7",
                "detected_at": "2026-06-01T10:00:00Z",
                "exposure_scope": scope,
                "owner": "publishing_owner",
                "affected_publications": [{"name": "Weekly brief"}, {"name": "Daily brief", "id": "pub-daily"}],
            }
        },
    }


def test_critical_scope_adds_immediate_containment_pause_and_publication_ids() -> None:
    plan = generate_publisher_destination_credential_compromise_plan(_spec())

    assert plan["summary"]["exposure_scope"] == "critical"
    assert plan["containment"][0]["name"] == "Immediate containment"
    assert plan["containment"][-1]["name"] == "Pause affected publications"
    assert [item["publication_id"] for item in plan["affected_publications"]] == ["pub-daily", "publication-002"]
    assert plan["revocation"][0]["credential_id"] == "cred-live-7"
    assert plan["replay_review"][0]["required"] is True


def test_standard_scope_omits_pause_and_validates_required_fields() -> None:
    plan = generate_publisher_destination_credential_compromise_plan(_spec("standard"))

    assert [item["name"] for item in plan["containment"]] == ["disable compromised credential", "restrict publisher destination egress"]
    with pytest.raises(ValueError, match="credential_id"):
        generate_publisher_destination_credential_compromise_plan({"metadata": {"publisher_destination_credential_compromise": {"destination": "Partner webhook"}}})
