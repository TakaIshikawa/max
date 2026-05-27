from __future__ import annotations

from fastapi.testclient import TestClient

from max.server.app import create_app


def test_certificate_renewal_plan_endpoint_returns_plan_and_alias() -> None:
    client = TestClient(create_app())
    body = {
        "tact_spec": {
            "schema_version": "tact-spec-preview/v1",
            "kind": "tact.project_spec",
            "source": {"idea_id": "cert-api"},
            "project": {"title": "TLS Gateway"},
            "certificate": {
                "service": "api-gateway",
                "common_name": "api.example.com",
                "expires_in_days": 10,
                "owner": "platform",
            },
        }
    }

    response = client.post("/api/v1/spec/certificate-renewal-plan", json=body)
    alias = client.post("/api/v1/ideas/spec-certificate-renewal-plan", json=body)

    assert response.status_code == 200
    assert alias.status_code == 200
    payload = response.json()
    assert payload == alias.json()
    assert payload["summary"]["service"] == "api-gateway"
    assert payload["summary"]["expiry_risk"] == "critical"
    assert payload["certificate_inventory"][0]["description"] == "Renew api.example.com for api-gateway."
    assert payload["renewal_steps"]
    assert payload["validation_checks"]
    assert payload["rollback"][0]["name"] == "restore_previous_cert"


def test_certificate_renewal_plan_endpoint_has_sparse_fallback() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/spec/certificate-renewal-plan",
        json={"tact_spec": {"schema_version": "tact-spec-preview/v1", "kind": "tact.project_spec"}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["service"] == "primary workflow"
    assert payload["certificate_inventory"][0]["owner"] == "platform_owner"
    assert "unknown number of days" in payload["expiry_risk"][0]["description"]
