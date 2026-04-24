"""Tests for publishing ideas to generic webhooks through the REST API."""

from __future__ import annotations

from fastapi.testclient import TestClient

from max.publisher.webhook import WebhookPublishError, WebhookPublishResult
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.signal import Signal, SignalSourceType


def _client(db_path: str) -> TestClient:
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


def _seed_idea(db_path: str) -> None:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_signal(
            Signal(
                id="sig-webhook001",
                source_type=SignalSourceType.FORUM,
                source_adapter="hackernews",
                title="Webhook handoff thread",
                content="Users want generic webhook publication.",
                url="https://news.ycombinator.com/item?id=123",
            )
        )
        store.insert_buildable_unit(
            BuildableUnit(
                id="bu-webhook001",
                title="Webhook Publish Idea",
                one_liner="Publish an idea to any webhook",
                category=BuildableCategory.INTEGRATION,
                problem="API clients cannot publish generic webhook payloads",
                solution="Expose the generic webhook publisher over REST",
                value_proposition="Users can integrate with custom automation tools",
                validation_plan="Call the REST endpoint with a mock webhook",
                domain="devtools",
                status="evaluated",
                evidence_rationale="Customer signals mention webhook handoff.",
                evidence_signals=["sig-webhook001"],
            )
        )
        store.insert_evaluation(_evaluation("bu-webhook001"))
    finally:
        store.close()


def _evaluation(unit_id: str) -> UtilityEvaluation:
    score = DimensionScore(value=8.0, confidence=0.7, reasoning="test")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=score,
        addressable_scale=score,
        build_effort=score,
        composability=score,
        competitive_density=score,
        timing_fit=score,
        compounding_value=score,
        overall_score=80.0,
        recommendation="yes",
    )


def test_publish_webhook_dry_run_returns_payload_without_network(tmp_path, monkeypatch) -> None:
    db_path = str(tmp_path / "test_webhook_api.db")
    _seed_idea(db_path)

    def fail_constructor(*args, **kwargs):
        raise AssertionError("dry_run must not construct a network publisher")

    monkeypatch.setattr("max.server.api.WebhookPublisher", fail_constructor)

    response = _client(db_path).post(
        "/api/v1/ideas/bu-webhook001/publish/webhook",
        json={
            "webhook_url": "https://user:secret@example.com/hooks/max?token=abc",
            "dry_run": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is True
    assert data["status_code"] is None
    assert data["attempts"] == 0
    assert data["target_url"] == "https://***@example.com/hooks/max?[redacted]"
    assert data["payload_type"] == "idea"
    assert data["payload"]["idea"]["id"] == "bu-webhook001"
    assert data["payload"]["evaluation"]["overall_score"] == 80.0
    assert data["payload"]["evidence_links"][0]["url"] == "https://news.ycombinator.com/item?id=123"
    assert data["payload"]["spec_preview"]["source"]["idea_id"] == "bu-webhook001"
    assert data["publication_attempt"] is None

    store = Store(db_path=db_path, wal_mode=True)
    try:
        assert store.list_publication_attempts("bu-webhook001") == []
    finally:
        store.close()


def test_publish_webhook_success_records_publication_attempt(tmp_path, monkeypatch) -> None:
    db_path = str(tmp_path / "test_webhook_api.db")
    _seed_idea(db_path)
    published: list[dict] = []

    class FakePublisher:
        redacted_url = "https://example.com/hooks/max"

        def __init__(self, url: str, *, timeout: float, retries: int) -> None:
            assert url == "https://example.com/hooks/max"
            assert timeout == 3.0
            assert retries == 1

        def publish(self, payload: dict, *, payload_type: str) -> WebhookPublishResult:
            published.append({"payload": payload, "payload_type": payload_type})
            return WebhookPublishResult(
                status_code=202,
                attempts=2,
                url=self.redacted_url,
                response_body='{"ok":true}',
            )

    monkeypatch.setattr("max.server.api.WebhookPublisher", FakePublisher)

    response = _client(db_path).post(
        "/api/v1/ideas/bu-webhook001/publish/webhook",
        json={
            "webhook_url": "https://example.com/hooks/max",
            "payload_fields": ["idea", "evaluation"],
            "payload_template": {"source": "api-test"},
            "dry_run": False,
            "timeout": 3.0,
            "max_retries": 1,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["status_code"] == 202
    assert data["attempts"] == 2
    assert data["target_url"] == "https://example.com/hooks/max"
    assert data["payload_type"] == "idea"
    assert data["payload"]["source"] == "api-test"
    assert "spec_preview" not in data["payload"]
    assert published[0]["payload_type"] == "idea"
    assert data["publication_attempt"]["target_type"] == "webhook"
    assert data["publication_attempt"]["target_url"] == "https://example.com/hooks/max"
    assert data["publication_attempt"]["status"] == "success"
    assert data["publication_attempt"]["response_status"] == 202

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-webhook001")
        assert len(attempts) == 1
        assert attempts[0]["target_type"] == "webhook"
        assert attempts[0]["status"] == "success"
    finally:
        store.close()


def test_publish_webhook_missing_idea_returns_404(tmp_path) -> None:
    response = _client(str(tmp_path / "test_webhook_api.db")).post(
        "/api/v1/ideas/missing/publish/webhook",
        json={"webhook_url": "https://example.com/hooks/max", "dry_run": True},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Idea not found: missing"


def test_publish_webhook_failure_records_failed_attempt(tmp_path, monkeypatch) -> None:
    db_path = str(tmp_path / "test_webhook_api.db")
    _seed_idea(db_path)

    class FakePublisher:
        redacted_url = "https://example.com/hooks/max"

        def __init__(self, *args, **kwargs) -> None:
            pass

        def publish(self, payload: dict, *, payload_type: str) -> WebhookPublishResult:
            raise WebhookPublishError("webhook returned HTTP 500: unavailable", status_code=500)

    monkeypatch.setattr("max.server.api.WebhookPublisher", FakePublisher)

    response = _client(db_path).post(
        "/api/v1/ideas/bu-webhook001/publish/webhook",
        json={"webhook_url": "https://example.com/hooks/max", "dry_run": False},
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "HTTP 500" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "webhook"
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["response_status"] == 500

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-webhook001")
        assert len(attempts) == 1
        assert attempts[0]["target_type"] == "webhook"
        assert attempts[0]["status"] == "failure"
        assert "HTTP 500" in attempts[0]["error"]
    finally:
        store.close()


def test_publish_webhook_attempts_appear_in_publication_history(tmp_path, monkeypatch) -> None:
    db_path = str(tmp_path / "test_webhook_api.db")
    _seed_idea(db_path)

    class FakePublisher:
        redacted_url = "https://example.com/hooks/max"

        def __init__(self, *args, **kwargs) -> None:
            pass

        def publish(self, payload: dict, *, payload_type: str) -> WebhookPublishResult:
            return WebhookPublishResult(
                status_code=200,
                attempts=1,
                url=self.redacted_url,
                response_body="",
            )

    monkeypatch.setattr("max.server.api.WebhookPublisher", FakePublisher)

    response = _client(db_path).post(
        "/api/v1/ideas/bu-webhook001/publish/webhook",
        json={"webhook_url": "https://example.com/hooks/max", "dry_run": False},
    )
    assert response.status_code == 200

    history = _client(db_path).get("/api/v1/ideas/bu-webhook001/publications")

    assert history.status_code == 200
    attempts = history.json()
    assert len(attempts) == 1
    assert attempts[0]["target_type"] == "webhook"
    assert attempts[0]["target_url"] == "https://example.com/hooks/max"
