from __future__ import annotations

from fastapi.testclient import TestClient

from max.server.app import create_app


def test_api_version_deprecation_endpoint_returns_plan_and_alias() -> None:
    client = TestClient(create_app())
    body = {
        "tact_spec": {
            "schema_version": "tact-spec-preview/v1",
            "kind": "tact.project_spec",
            "source": {"idea_id": "api-deprecation"},
            "project": {"title": "Public API", "target_users": "partners"},
            "metadata": {
                "api_deprecation": {
                    "deprecated_version": "v1",
                    "replacement_version": "v2",
                    "consumers": ["mobile app", "partner sync"],
                    "surfaces": ["/v1/accounts"],
                    "notice_days": 120,
                    "public_api": True,
                    "breaking": True,
                }
            },
        }
    }

    response = client.post("/api/v1/spec/api-version-deprecation-plan", json=body)
    alias = client.post("/api/v1/ideas/spec-api-version-deprecation-plan", json=body)

    assert response.status_code == 200
    assert alias.status_code == 200
    payload = response.json()
    assert payload == alias.json()
    assert payload["summary"]["deprecated_version"] == "v1"
    assert payload["summary"]["replacement_version"] == "v2"
    assert payload["deprecation_policy"]["migration_window_days"] == 120
    assert [row["consumer"] for row in payload["affected_consumers"]] == [
        "mobile app",
        "partner sync",
        "partners",
    ]
    assert payload["compatibility_checks"]
    assert payload["communication_schedule"]


def test_api_version_deprecation_endpoint_has_sparse_fallback() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/spec/api-version-deprecation-plan",
        json={"tact_spec": {"schema_version": "tact-spec-preview/v1", "kind": "tact.project_spec"}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["deprecated_version"] == "v1"
    assert payload["summary"]["replacement_version"] == "v2"
    assert payload["affected_consumers"][0]["consumer"] == "default API consumer"
    assert payload["migration_timeline"]
