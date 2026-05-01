"""API tests for design brief data-room index Markdown exports."""

from __future__ import annotations

from fastapi.testclient import TestClient

from max.analysis.design_brief_data_room_index import SCHEMA_VERSION
from tests.test_api_design_brief_data_room_index import data_room_client


def test_get_design_brief_data_room_index_markdown_download(
    data_room_client: tuple[TestClient, str],
) -> None:
    client, brief_id = data_room_client

    response = client.get(f"/api/v1/design-briefs/{brief_id}/data-room-index.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-data-room-index.md"'
    )
    assert response.text.startswith("# Data Room Index: Bundle Export Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in response.text
    assert f"Design brief: `{brief_id}`" in response.text
    assert "## Artifact Index" in response.text
    assert "| Artifact | JSON | Markdown | Description |" in response.text
    assert f"`/api/v1/design-briefs/{brief_id}/bundle`" in response.text
    assert f"`/api/v1/design-briefs/{brief_id}/bundle.md`" in response.text
    assert "## Sections" in response.text


def test_get_design_brief_data_room_index_supports_markdown_format(
    data_room_client: tuple[TestClient, str],
) -> None:
    client, brief_id = data_room_client

    response = client.get(f"/api/v1/design-briefs/{brief_id}/data-room-index?format=markdown")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.text.startswith("# Data Room Index: Bundle Export Brief")


def test_get_design_brief_data_room_index_markdown_missing_brief_returns_404(
    data_room_client: tuple[TestClient, str],
) -> None:
    client, _brief_id = data_room_client

    response = client.get("/api/v1/design-briefs/dbf-missing/data-room-index.md")

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"
