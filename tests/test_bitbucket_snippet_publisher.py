"""Tests for Bitbucket Cloud snippet publishing."""

from __future__ import annotations

import base64

import httpx
import pytest

from max.publisher import (
    BitbucketSnippetPayload,
    BitbucketSnippetPublishError,
    BitbucketSnippetPublishResult,
    BitbucketSnippetPublisher,
    BitbucketSnippetsPublisher,
)


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-snippet001",
            "status": "approved",
            "domain": "devtools",
            "category": "handoff",
            "created_at": "2026-04-22T00:00:00+00:00",
            "updated_at": "2026-04-22T00:00:00+00:00",
        },
        "project": {
            "title": "Bitbucket Snippet Handoff",
            "summary": "Publish generated TactSpecs as Bitbucket snippets",
            "target_users": "platform teams",
        },
        "problem": {"statement": "TactSpec handoff artifacts are scattered"},
        "solution": {"approach": "Create deterministic Bitbucket snippet artifacts"},
        "execution": {
            "mvp_scope": ["Snippet payload builder", "Bitbucket REST publisher"],
            "validation_plan": "Dry run and publish into a test workspace.",
        },
        "evidence": {
            "rationale": "Teams already review snippets in Bitbucket.",
            "insight_ids": ["ins-snippet001"],
            "signal_ids": ["sig-snippet001"],
        },
        "evaluation": {
            "overall_score": 84.0,
            "recommendation": "yes",
        },
    }


def test_build_snippet_payload_maps_tact_spec_files_visibility_and_metadata() -> None:
    publisher = BitbucketSnippetPublisher("max-team", visibility="public")

    payload = publisher.build_snippet_payload(_tact_spec()).to_dict()

    assert payload["title"] == "Max TactSpec: Bitbucket Snippet Handoff"
    assert payload["workspace"] == "max-team"
    assert payload["visibility"] == "public"
    assert set(payload["files"]) == {"bu-snippet001.md", "bu-snippet001.json"}
    assert payload["files"]["bu-snippet001.md"]["content"].startswith(
        "# Bitbucket Snippet Handoff"
    )
    assert "Idea ID: bu-snippet001" in payload["files"]["bu-snippet001.md"]["content"]
    assert '"kind": "tact.project_spec"' in payload["files"]["bu-snippet001.json"]["content"]
    assert payload["metadata"] == {
        "publisher": "max.bitbucket_snippets",
        "source_system": "max",
        "source_type": "idea",
        "idea_id": "bu-snippet001",
        "design_brief_id": None,
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "workspace": "max-team",
        "visibility": "public",
        "filenames": ["bu-snippet001.json", "bu-snippet001.md"],
    }


def test_dry_run_returns_exact_payload_without_credentials_or_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = BitbucketSnippetPublisher("max-team", client=client)

    result = publisher.publish(_tact_spec(), dry_run=True)
    expected = publisher.build_snippet_payload(_tact_spec()).to_dict()

    assert result.dry_run is True
    assert result.status_code is None
    assert result.snippet_id is None
    assert result.snippet_url is None
    assert result.payload == expected


def test_from_env_reads_workspace_credentials_and_visibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BITBUCKET_WORKSPACE", "env-team")
    monkeypatch.setenv("BITBUCKET_USERNAME", "env@example.com")
    monkeypatch.setenv("BITBUCKET_APP_PASSWORD", "env-password")
    monkeypatch.setenv("BITBUCKET_TOKEN", "env-token")
    monkeypatch.setenv("BITBUCKET_SNIPPET_VISIBILITY", "public")
    monkeypatch.setenv("BITBUCKET_API_URL", "https://api.bitbucket.test/2.0")

    publisher = BitbucketSnippetPublisher.from_env()

    assert publisher.workspace == "env-team"
    assert publisher.username == "env@example.com"
    assert publisher.app_password == "env-password"
    assert publisher.token == "env-token"
    assert publisher.visibility == "public"
    assert publisher.api_url == "https://api.bitbucket.test/2.0"


def test_live_publish_posts_bitbucket_snippet_with_token() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = request.read().decode("utf-8")
        assert 'name="title"' in body
        assert "Custom Snippet" in body
        assert 'name="is_private"' in body
        assert "false" in body
        assert 'name="files/bu-snippet001.md"; filename="bu-snippet001.md"' in body
        assert 'name="files/bu-snippet001.json"; filename="bu-snippet001.json"' in body
        assert "max.bitbucket_snippets" not in body
        return httpx.Response(
            201,
            json={
                "id": "abc123",
                "links": {
                    "html": {
                        "href": "https://bitbucket.org/snippets/max-team/abc123/custom-snippet"
                    }
                },
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = BitbucketSnippetPublisher(
        "max-team",
        token="secret-token",
        api_url="https://api.bitbucket.test/2.0",
        client=client,
    )

    result = publisher.publish(
        _tact_spec(),
        title="Custom Snippet",
        visibility="public",
        dry_run=False,
    )

    assert result.status_code == 201
    assert result.snippet_id == "abc123"
    assert result.snippet_url == "https://bitbucket.org/snippets/max-team/abc123/custom-snippet"
    assert requests[0].url == "https://api.bitbucket.test/2.0/snippets/max-team"
    assert requests[0].headers["Authorization"] == "Bearer secret-token"
    assert result.payload["metadata"]["bitbucket_snippet_id"] == "abc123"
    assert result.payload["metadata"]["bitbucket_snippet_url"] == result.snippet_url


def test_live_publish_supports_app_password_credentials() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "basic123",
                "links": {"html": {"href": "https://bitbucket.org/snippets/max-team/basic123"}},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = BitbucketSnippetPublisher(
        "max-team",
        username="agent@example.com",
        app_password="bb_app_password",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    expected_auth = base64.b64encode(b"agent@example.com:bb_app_password").decode("ascii")
    assert requests[0].headers["Authorization"] == f"Basic {expected_auth}"
    assert result.snippet_id == "basic123"


def test_live_publish_requires_credentials() -> None:
    publisher = BitbucketSnippetPublisher("max-team")

    with pytest.raises(BitbucketSnippetPublishError, match="BITBUCKET_TOKEN"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_live_publish_surfaces_http_error_with_status_code() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"message": "workspace forbidden"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = BitbucketSnippetPublisher("max-team", token="secret-token", client=client)

    with pytest.raises(BitbucketSnippetPublishError) as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc.value.status_code == 403
    assert "HTTP 403" in str(exc.value)
    assert "workspace forbidden" in str(exc.value)


def test_public_imports_expose_bitbucket_snippet_types() -> None:
    assert BitbucketSnippetsPublisher is BitbucketSnippetPublisher
    assert BitbucketSnippetPayload.__name__ == "BitbucketSnippetPayload"
    assert BitbucketSnippetPublishResult.__name__ == "BitbucketSnippetPublishResult"
    assert issubclass(BitbucketSnippetPublishError, RuntimeError)
