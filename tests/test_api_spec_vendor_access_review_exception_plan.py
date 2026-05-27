from __future__ import annotations

from fastapi.testclient import TestClient

from max.server.app import create_app


def test_vendor_access_review_exception_endpoint_returns_plan_and_alias() -> None:
    client = TestClient(create_app())
    body = {
        "tact_spec": {
            "schema_version": "tact-spec-preview/v1",
            "kind": "tact.project_spec",
            "source": {"idea_id": "vendor-access-api"},
            "metadata": {
                "vendor_access_review_exception": {
                    "vendors": [{"vendor": "Acme SOC", "role": "auditor"}],
                    "systems_accessed": ["billing admin"],
                    "exception_rationale": ["audit evidence collection window"],
                    "compensating_controls": ["daily access log review"],
                    "approvers": ["security lead"],
                }
            },
        }
    }

    response = client.post("/api/v1/spec/vendor-access-review-exception-plan", json=body)
    alias = client.post("/api/v1/ideas/spec-vendor-access-review-exception-plan", json=body)

    assert response.status_code == 200
    assert alias.status_code == 200
    payload = response.json()
    assert payload == alias.json()
    assert payload["vendor_access_records"][0]["name"] == "Acme SOC"
    assert payload["vendor_access_records"][0]["role"] == "auditor"
    assert payload["systems_accessed"][0]["name"] == "billing admin"
    assert payload["compensating_controls"][0]["name"] == "daily access log review"
    assert payload["approver_review"][0]["name"] == "security lead"


def test_vendor_access_review_exception_endpoint_has_sparse_fallback() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/spec/vendor-access-review-exception-plan",
        json={"tact_spec": {"schema_version": "tact-spec-preview/v1", "kind": "tact.project_spec"}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["vendor_access_records"][0]["name"] == "vendor access review exception"
    assert payload["compensating_controls"][0]["owner"] == "security_owner"
    assert payload["revocation_workflow"]
