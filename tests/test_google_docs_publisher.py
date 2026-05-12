"""Tests for Google Docs publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.google_docs import GoogleDocsPublishError, GoogleDocsPublisher


def _idea_payload() -> dict:
    return {
        "source": {"idea_id": "bu-doc001", "type": "idea"},
        "project": {"title": "Docs Publisher", "summary": "Create Google Docs from Max ideas."},
        "problem": {"statement": "Ideas need review documents."},
        "solution": {"approach": "Create a document through the Docs API."},
        "execution": {"mvp_scope": ["Create doc", "Insert body"]},
        "evidence": {"rationale": "Reviewers ask for docs."},
        "evaluation": {"overall_score": 79.0, "recommendation": "ship"},
    }


def _design_brief_payload() -> dict:
    return {
        "design_brief": {
            "id": "dbf-doc001",
            "title": "Docs Design Brief",
            "summary": "Turn briefs into Google Docs.",
            "readiness_score": 91.0,
            "recommendation": "ready",
            "source_idea_ids": ["bu-doc001"],
            "validation_plan": "Publish to a test folder.",
            "markdown": "# Docs Design Brief\n\nRendered preview.",
        }
    }


def test_dry_run_returns_create_and_insert_payloads_without_credentials_or_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    publisher = GoogleDocsPublisher(title_prefix="[Max]", folder_id="folder-1", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(_idea_payload(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.create_endpoint == "https://docs.googleapis.com/v1/documents"
    assert result.create_payload == {"title": "[Max] Max Idea - Docs Publisher", "metadata": {"folder_id": "folder-1"}}
    assert "Recommendation: ship" in result.rendered_text
    assert result.insert_payload["requests"][0]["insertText"]["location"] == {"index": 1}
    assert "Create Google Docs from Max ideas." in result.insert_payload["requests"][0]["insertText"]["text"]


def test_design_brief_renders_plain_text_body() -> None:
    publisher = GoogleDocsPublisher(document_title="Explicit Title")

    result = publisher.publish(_design_brief_payload(), dry_run=True)

    assert result.create_payload["title"] == "Explicit Title"
    assert "Brief ID: dbf-doc001" in result.rendered_text
    assert "Readiness score: 91.0" in result.rendered_text
    assert "Source ideas: bu-doc001" in result.rendered_text
    assert "# Docs Design Brief" in result.rendered_text


def test_live_publish_creates_document_and_appends_text() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if str(request.url).endswith("/v1/documents"):
            return httpx.Response(200, json={"documentId": "doc-123"})
        return httpx.Response(200, json={"replies": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GoogleDocsPublisher(access_token="docs-token", api_url="https://docs.example.test", client=client)

    result = publisher.publish(_idea_payload(), dry_run=False)

    assert result.status_code == 200
    assert result.document_id == "doc-123"
    assert result.document_url == "https://docs.google.com/document/d/doc-123/edit"
    assert [request.headers["Authorization"] for request in requests] == ["Bearer docs-token", "Bearer docs-token"]
    assert json.loads(requests[0].read())["title"] == "Max Idea - Docs Publisher"
    assert json.loads(requests[1].read())["requests"][0]["insertText"]["text"].startswith("Docs Publisher")


def test_live_publish_requires_access_token() -> None:
    publisher = GoogleDocsPublisher()

    with pytest.raises(GoogleDocsPublishError, match="GOOGLE_DOCS_ACCESS_TOKEN"):
        publisher.publish(_idea_payload(), dry_run=False)


def test_provider_error_redacts_access_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="bad access_token=docs-token Authorization=Bearer docs-token")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GoogleDocsPublisher(access_token="docs-token", client=client)

    with pytest.raises(GoogleDocsPublishError) as exc:
        publisher.publish(_idea_payload(), dry_run=False)

    assert exc.value.status_code == 401
    assert "docs-token" not in str(exc.value)
