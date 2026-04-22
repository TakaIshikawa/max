"""Tests for inbound external feedback webhooks."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test_feedback_webhook.db")
    store = Store(db_path=path, wal_mode=True)
    store.close()
    return path


@pytest.fixture
def client(db_path):
    from max.server.dependencies import get_store

    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def _seed_idea(db_path: str, idea_id: str = "bu-webhook") -> None:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_buildable_unit(
            BuildableUnit(
                id=idea_id,
                title="Webhook Idea",
                one_liner="External execution feedback",
                category=BuildableCategory.APPLICATION,
                ideation_mode=IdeationMode.DIRECT,
                problem="External systems need to report outcomes",
                solution="Accept signed feedback callbacks",
                value_proposition="Closes the execution feedback loop",
                status="evaluated",
            )
        )
    finally:
        store.close()


def _raw_payload(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _signature(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _post_raw(client: TestClient, body: bytes, signature: str | None = None):
    headers = {"content-type": "application/json"}
    if signature is not None:
        headers["X-Max-Signature"] = signature
    return client.post("/api/v1/webhooks/feedback", content=body, headers=headers)


def test_feedback_webhook_accepts_signed_payload(client, db_path, monkeypatch):
    monkeypatch.setattr("max.config.MAX_FEEDBACK_WEBHOOK_SECRET", "test-secret")
    _seed_idea(db_path)
    payload = {
        "idea_id": "bu-webhook",
        "outcome": "approved",
        "reason": "integration checks passed",
        "approval_score": 9,
        "external_run_id": "run-123",
        "external_url": "https://executor.example/runs/run-123",
        "metadata": {"executor": "ci", "commit": "abc123"},
    }
    body = _raw_payload(payload)

    response = _post_raw(client, body, _signature("test-secret", body))

    assert response.status_code == 201
    assert response.json() == {
        "status": "ok",
        "idea_id": "bu-webhook",
        "outcome": "approved",
        "external_run_id": "run-123",
    }

    store = Store(db_path=db_path, wal_mode=True)
    try:
        unit = store.get_buildable_unit("bu-webhook")
        feedback = store.get_latest_feedback("bu-webhook")
        assert unit is not None
        assert unit.status == "approved"
        assert feedback is not None
        assert feedback["outcome"] == "approved"
        assert feedback["approval_score"] == 9
        assert feedback["reason"].startswith("integration checks passed")
        assert "external_feedback=" in feedback["reason"]
        assert '"external_run_id":"run-123"' in feedback["reason"]
        assert '"executor":"ci"' in feedback["reason"]
    finally:
        store.close()


def test_feedback_webhook_rejects_bad_signature(client, db_path, monkeypatch):
    monkeypatch.setattr("max.config.MAX_FEEDBACK_WEBHOOK_SECRET", "test-secret")
    _seed_idea(db_path)
    body = _raw_payload(
        {
            "idea_id": "bu-webhook",
            "outcome": "rejected",
            "reason": "failed",
            "external_run_id": "run-123",
            "external_url": "https://executor.example/runs/run-123",
        }
    )

    response = _post_raw(client, body, "sha256=bad")

    assert response.status_code == 401
    store = Store(db_path=db_path, wal_mode=True)
    try:
        assert store.has_feedback("bu-webhook") is False
    finally:
        store.close()


def test_feedback_webhook_missing_idea_returns_404(client, monkeypatch):
    monkeypatch.setattr("max.config.MAX_FEEDBACK_WEBHOOK_SECRET", "test-secret")
    body = _raw_payload(
        {
            "idea_id": "missing-webhook-idea",
            "outcome": "approved",
            "reason": "passed",
            "external_run_id": "run-123",
            "external_url": "https://executor.example/runs/run-123",
        }
    )

    response = _post_raw(client, body, _signature("test-secret", body))

    assert response.status_code == 404
    assert "Idea not found" in response.json()["detail"]


def test_feedback_webhook_rejects_invalid_outcome(client, db_path, monkeypatch):
    monkeypatch.setattr("max.config.MAX_FEEDBACK_WEBHOOK_SECRET", "")
    _seed_idea(db_path)

    response = client.post(
        "/api/v1/webhooks/feedback",
        json={
            "idea_id": "bu-webhook",
            "outcome": "unknown",
            "reason": "bad outcome",
            "external_run_id": "run-123",
            "external_url": "https://executor.example/runs/run-123",
        },
    )

    assert response.status_code == 422


def test_feedback_webhook_accepts_unsigned_when_no_secret(client, db_path, monkeypatch):
    monkeypatch.setattr("max.config.MAX_FEEDBACK_WEBHOOK_SECRET", "")
    _seed_idea(db_path)

    response = client.post(
        "/api/v1/webhooks/feedback",
        json={
            "idea_id": "bu-webhook",
            "outcome": "published",
            "reason": "deployed",
            "approval_score": 8,
            "external_run_id": "run-local",
            "external_url": "http://localhost/runs/run-local",
            "metadata": {"local": True},
        },
    )

    assert response.status_code == 201
    assert response.json()["outcome"] == "published"

    store = Store(db_path=db_path, wal_mode=True)
    try:
        unit = store.get_buildable_unit("bu-webhook")
        feedback = store.get_latest_feedback("bu-webhook")
        assert unit is not None
        assert unit.status == "published"
        assert feedback is not None
        assert feedback["outcome"] == "published"
        assert "external_feedback=" in feedback["reason"]
    finally:
        store.close()
