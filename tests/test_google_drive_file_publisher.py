from __future__ import annotations

import json

import httpx

from max.publisher.google_drive_files import GoogleDriveFilePublisher
from tests.test_zoom_chat_webhook_publisher import _design_brief_payload, _idea_payload


def test_dry_run_returns_metadata_content_endpoint_and_redacted_headers() -> None:
    publisher = GoogleDriveFilePublisher(folder_id="folder-1", api_url="https://drive.example.test/drive/v3")

    result = publisher.publish(_idea_payload(), dry_run=True)

    assert result.endpoint == "https://drive.example.test/drive/v3/files?uploadType=multipart&fields=id,webViewLink"
    assert result.headers["Authorization"] == "Bearer [REDACTED]"
    assert result.metadata["name"] == "zoom-chat-publisher.md"
    assert result.metadata["parents"] == ["folder-1"]
    assert "Idea ID: bu-zoom001" in result.content


def test_design_brief_dry_run_uses_deterministic_filename() -> None:
    result = GoogleDriveFilePublisher().publish(_design_brief_payload(), dry_run=True)

    assert result.metadata["name"] == "zoom-chat-design-brief.md"
    assert "Brief ID: dbf-zoom001" in result.content


def test_from_env_reads_google_drive_configuration(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_DRIVE_ACCESS_TOKEN", "drive-token")
    monkeypatch.setenv("GOOGLE_DRIVE_FOLDER_ID", "folder-env")
    monkeypatch.setenv("GOOGLE_DRIVE_API_URL", "https://drive.example.test/drive/v3")

    publisher = GoogleDriveFilePublisher.from_env()

    assert publisher.access_token == "drive-token"
    assert publisher.folder_id == "folder-env"
    assert publisher.api_url == "https://drive.example.test/drive/v3"


def test_live_publish_posts_drive_creation_request_and_returns_file_fields() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "file-1", "webViewLink": "https://drive.example/file-1"})

    publisher = GoogleDriveFilePublisher(access_token="drive-token", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(_idea_payload(), dry_run=False)

    assert result.file_id == "file-1"
    assert result.web_view_link == "https://drive.example/file-1"
    assert requests[0].headers["Authorization"] == "Bearer drive-token"
    assert json.loads(requests[0].read())["metadata"]["name"] == "zoom-chat-publisher.md"
