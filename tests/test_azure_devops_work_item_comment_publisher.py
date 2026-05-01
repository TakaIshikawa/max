"""Tests for Azure DevOps work item comment publishing."""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from max.publisher import (
    AzureDevOpsWorkItemCommentsPublisher as ExportedAzureDevOpsWorkItemCommentsPublisher,
)
from max.publisher.azure_devops_work_item_comments import (
    AzureDevOpsWorkItemCommentPublishError,
    AzureDevOpsWorkItemCommentPublisher,
)


def _artifact() -> dict:
    return {
        "schema_version": "design-brief-scope-matrix/v1",
        "kind": "max.design_brief.scope_matrix",
        "source": {
            "system": "max",
            "type": "design_brief",
            "idea_id": "bu-azdo-comment",
            "design_brief_id": "dbf-azdo-comment",
        },
        "project": {
            "title": "Azure Comment Artifact",
            "summary": "Attach generated planning artifacts to Azure DevOps work items.",
        },
    }


def test_comment_endpoint_uses_organization_url_project_work_item_and_api_version() -> None:
    publisher = AzureDevOpsWorkItemCommentPublisher(
        "https://dev.azure.com/max-org/",
        "Delivery Project",
        42,
    )

    assert publisher.comment_endpoint() == (
        "https://dev.azure.com/max-org/Delivery%20Project/_apis/wit/workItems/"
        "42/comments?api-version=7.1-preview.4"
    )


def test_constructor_accepts_organization_name_fallback() -> None:
    publisher = AzureDevOpsWorkItemCommentPublisher(
        organization="max org",
        project="Max",
        work_item_id="123",
    )

    assert publisher.organization_url == "https://dev.azure.com/max%20org"
    assert publisher.comment_endpoint() == (
        "https://dev.azure.com/max%20org/Max/_apis/wit/workItems/123/comments?"
        "api-version=7.1-preview.4"
    )


def test_build_comment_payload_renders_artifact_markdown_and_metadata() -> None:
    publisher = AzureDevOpsWorkItemCommentPublisher(
        "https://dev.azure.com/max-org",
        "Max",
        "123",
    )

    payload = publisher.build_comment_payload(_artifact()).to_dict()

    assert payload["work_item_id"] == "123"
    assert payload["text"].startswith("## Azure Comment Artifact")
    assert "Attach generated planning artifacts to Azure DevOps work items." in payload["text"]
    assert "- Kind: max.design_brief.scope_matrix" in payload["text"]
    assert "- Schema version: design-brief-scope-matrix/v1" in payload["text"]
    assert payload["metadata"]["publisher"] == "max.azure_devops_work_item_comments"
    assert payload["metadata"]["design_brief_id"] == "dbf-azdo-comment"


def test_string_comment_is_html_safe() -> None:
    publisher = AzureDevOpsWorkItemCommentPublisher("max-org", "Max", "123")

    payload = publisher.build_comment_payload("Ship <script>alert(1)</script>").to_dict()

    assert payload["text"] == "Ship &lt;script&gt;alert(1)&lt;/script&gt;"
    assert payload["metadata"]["source_type"] == "text"


def test_from_env_reads_work_item_id_pat_and_artifact_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_DEVOPS_ORGANIZATION_URL", "https://dev.azure.com/env-org")
    monkeypatch.setenv("AZURE_DEVOPS_PROJECT", "Env Project")
    monkeypatch.setenv("AZURE_DEVOPS_WORK_ITEM_ID", "321")
    monkeypatch.setenv("AZURE_DEVOPS_PAT", "env-pat")
    monkeypatch.setenv("AZURE_DEVOPS_ARTIFACT_TITLE", "Env Artifact Title")

    publisher = AzureDevOpsWorkItemCommentPublisher.from_env()
    payload = publisher.build_comment_payload(_artifact()).to_dict()

    assert publisher.organization_url == "https://dev.azure.com/env-org"
    assert publisher.project == "Env Project"
    assert publisher.work_item_id == "321"
    assert publisher.personal_access_token == "env-pat"
    assert payload["text"].startswith("## Env Artifact Title")


def test_dry_run_returns_comment_request_without_network_or_credentials() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = AzureDevOpsWorkItemCommentPublisher(
        "max-org",
        "Max",
        "123",
        personal_access_token="azdo_pat",
        client=client,
    )

    result = publisher.publish("Review note", dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.work_item_id == "123"
    assert result.comment_id is None
    assert result.payload["request"]["method"] == "POST"
    assert result.payload["request"]["url"] == (
        "https://dev.azure.com/max-org/Max/_apis/wit/workItems/123/comments?"
        "api-version=7.1-preview.4"
    )
    assert result.payload["request"]["json"] == {"text": "Review note"}
    assert result.payload["request"]["headers"]["Authorization"] == "[REDACTED]"
    assert "azdo_pat" not in json.dumps(result.payload["request"])


def test_successful_publish_posts_comment_and_normalizes_response() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": 987,
                "url": "https://dev.azure.com/max-org/Max/_apis/wit/workItems/123/comments/987",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = AzureDevOpsWorkItemCommentPublisher(
        "max-org",
        "Max",
        "123",
        personal_access_token="azdo_pat",
        client=client,
    )

    result = publisher.publish("Review note", dry_run=False)

    assert result.status_code == 200
    assert result.work_item_id == "123"
    assert result.comment_id == "987"
    assert result.comment_url == (
        "https://dev.azure.com/max-org/Max/_apis/wit/workItems/123/comments/987"
    )
    assert str(requests[0].url) == (
        "https://dev.azure.com/max-org/Max/_apis/wit/workItems/123/comments?"
        "api-version=7.1-preview.4"
    )
    assert requests[0].headers["Content-Type"] == "application/json"
    assert requests[0].headers["User-Agent"] == (
        "max-azure-devops-work-item-comments-publisher/1"
    )
    expected_auth = "Basic " + base64.b64encode(b":azdo_pat").decode("ascii")
    assert requests[0].headers["Authorization"] == expected_auth
    assert _json_from_request(requests[0]) == {"text": "Review note"}
    assert result.payload["metadata"]["azure_devops_work_item_comment_id"] == "987"


def test_live_publish_raises_redacted_error_on_http_failure() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                401,
                json={"message": "bad token azdo_pat"},
            )
        )
    )
    publisher = AzureDevOpsWorkItemCommentPublisher(
        "max-org",
        "Max",
        "123",
        personal_access_token="azdo_pat",
        client=client,
    )

    with pytest.raises(AzureDevOpsWorkItemCommentPublishError, match="HTTP 401") as exc:
        publisher.publish("Review note", dry_run=False)

    assert exc.value.status_code == 401
    assert "azdo_pat" not in str(exc.value)


def test_missing_work_item_id_raises_validation_error() -> None:
    with pytest.raises(AzureDevOpsWorkItemCommentPublishError, match="work_item_id"):
        AzureDevOpsWorkItemCommentPublisher("max-org", "Max", None)


def test_exported_from_publisher_package() -> None:
    assert (
        ExportedAzureDevOpsWorkItemCommentsPublisher
        is AzureDevOpsWorkItemCommentPublisher
    )


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
