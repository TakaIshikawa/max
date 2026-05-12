from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.productboard_feature_notes import (
    ProductboardFeatureNotePublishError,
    ProductboardFeatureNotePublisher,
)


def _unit() -> dict:
    return {
        "source": {
            "idea_id": "idea-productboard-001",
            "status": "approved",
            "category": "discovery",
        },
        "project": {
            "title": "Productboard Feature Note Publisher",
            "summary": "Close the product discovery loop.",
        },
        "problem": {"statement": "Product teams need curated Max context next to feature work."},
        "solution": {"approach": "Attach a deterministic note to the matching feature."},
        "evaluation": {"overall_score": 91.25},
        "execution": {"validation_plan": "Review with PMs during roadmap triage."},
    }


def test_builds_deterministic_productboard_feature_note_payload() -> None:
    publisher = ProductboardFeatureNotePublisher(feature_id="fea_123")

    payload = publisher.build_feature_note_payload(_unit()).to_dict()

    assert payload == {
        "feature_id": "fea_123",
        "body": "\n".join(
            [
                "Productboard Feature Note Publisher",
                "Idea ID: idea-productboard-001",
                "Status: approved",
                "Score: 91.2",
                "Problem: Product teams need curated Max context next to feature work.",
                "Solution: Attach a deterministic note to the matching feature.",
                "Validation plan: Review with PMs during roadmap triage.",
            ]
        ),
        "metadata": {
            "publisher": "max.productboard_feature_notes",
            "idea_id": "idea-productboard-001",
            "status": "approved",
            "category": "discovery",
            "score": "91.2",
        },
    }


def test_from_env_reads_productboard_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRODUCTBOARD_FEATURE_ID", "fea_env")
    monkeypatch.setenv("PRODUCTBOARD_ACCESS_TOKEN", "pb_env")
    monkeypatch.setenv("PRODUCTBOARD_API_URL", "https://productboard.example.test")

    publisher = ProductboardFeatureNotePublisher.from_env(max_retries=4)

    assert publisher.feature_id == "fea_env"
    assert publisher.token == "pb_env"
    assert publisher.api_url == "https://productboard.example.test"
    assert publisher.max_retries == 4


def test_dry_run_returns_endpoint_payload_feature_and_no_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    publisher = ProductboardFeatureNotePublisher(
        feature_id="fea_123",
        api_url="https://productboard.example.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_unit(), dry_run=True)

    assert result.dry_run is True
    assert result.feature_id == "fea_123"
    assert result.endpoint == "https://productboard.example.test/features/fea_123/notes"
    assert result.payload["feature_id"] == "fea_123"
    assert result.payload["metadata"]["idea_id"] == "idea-productboard-001"


def test_live_publish_posts_note_body_and_parses_response() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"data": {"id": "note_123"}})

    publisher = ProductboardFeatureNotePublisher(
        feature_id="fea_123",
        token="pb_test",
        api_url="https://productboard.example.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_unit(), dry_run=False)

    posted = json.loads(requests[0].read())
    note_body = posted["data"]["content"]
    assert result.status_code == 201
    assert result.note_id == "note_123"
    assert requests[0].headers["Authorization"] == "Bearer pb_test"
    assert requests[0].url == "https://productboard.example.test/features/fea_123/notes"
    assert "Idea ID: idea-productboard-001" in note_body
    assert "Status: approved" in note_body
    assert "Score: 91.2" in note_body
    assert "Problem: Product teams need curated Max context next to feature work." in note_body
    assert "Solution: Attach a deterministic note to the matching feature." in note_body
    assert "Validation plan: Review with PMs during roadmap triage." in note_body


def test_retryable_failure_retries_and_redacts_token() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, text="temporarily unavailable pb_test")

    publisher = ProductboardFeatureNotePublisher(
        feature_id="fea_123",
        token="pb_test",
        max_retries=2,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ProductboardFeatureNotePublishError, match="HTTP 503") as exc:
        publisher.publish(_unit(), dry_run=False)

    assert calls == 3
    assert exc.value.status_code == 503
    assert "pb_test" not in str(exc.value)


def test_live_publish_requires_token() -> None:
    publisher = ProductboardFeatureNotePublisher(feature_id="fea_123")

    with pytest.raises(ProductboardFeatureNotePublishError, match="PRODUCTBOARD_ACCESS_TOKEN"):
        publisher.publish(_unit(), dry_run=False)
