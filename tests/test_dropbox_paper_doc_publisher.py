from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.dropbox_paper_docs import DropboxPaperDocPublisher
from tests.test_zoom_chat_webhook_publisher import _design_brief_payload, _idea_payload


def test_dry_run_builds_title_and_body_for_idea_and_design_brief() -> None:
    publisher = DropboxPaperDocPublisher(api_url="https://dropbox.example.test/2")

    idea = publisher.publish(_idea_payload(), dry_run=True)
    brief = publisher.publish(_design_brief_payload(), dry_run=True)

    assert idea.endpoint == "https://dropbox.example.test/2/paper/docs/create"
    assert idea.payload["title"] == "Zoom Chat Publisher"
    assert "Idea ID: bu-zoom001" in idea.payload["body"]
    assert brief.payload["title"] == "Zoom Chat Design Brief"
    assert "Brief ID: dbf-zoom001" in brief.payload["body"]


def test_from_env_reads_dropbox_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DROPBOX_ACCESS_TOKEN", "drop-token")
    monkeypatch.setenv("DROPBOX_API_URL", "https://dropbox.example.test/2")

    publisher = DropboxPaperDocPublisher.from_env()

    assert publisher.access_token == "drop-token"
    assert publisher.api_url == "https://dropbox.example.test/2"


def test_live_publish_posts_bearer_json_and_returns_document_fields() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"doc_id": "doc-1", "url": "https://paper.example/doc-1"})

    publisher = DropboxPaperDocPublisher(access_token="drop-token", api_url="https://dropbox.example.test/2", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(_idea_payload(), dry_run=False)

    assert result.document_id == "doc-1"
    assert result.document_url == "https://paper.example/doc-1"
    assert requests[0].headers["Authorization"] == "Bearer drop-token"
    assert json.loads(requests[0].read())["format"] == "markdown"
