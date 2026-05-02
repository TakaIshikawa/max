"""Tests for GitLab release publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher import GitLabReleasePublisher as ExportedGitLabReleasePublisher
from max.publisher.gitlab_releases import (
    GitLabReleasePublishError,
    GitLabReleasePublisher,
)
from max.types.buildable_unit import BuildableUnit


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "design_brief",
            "idea_id": "bu-release001",
            "design_brief_id": "dbf-release001",
            "status": "approved",
            "domain": "devtools",
            "category": "release_handoff",
        },
        "project": {
            "title": "GitLab Release Publisher",
            "summary": "Create versioned handoff artifacts for build agents.",
            "target_users": "product engineers",
            "specific_user": "build agent owner",
            "buyer": "platform team",
            "workflow_context": "release handoff",
        },
        "problem": {"statement": "Accepted briefs lack a versioned handoff artifact."},
        "solution": {"approach": "Publish a GitLab Release."},
        "execution": {
            "mvp_scope": ["Release payload builder", "Release API call"],
            "validation_plan": "Create one release in a sandbox project.",
        },
        "evidence": {
            "rationale": "Versioned artifacts keep build handoffs traceable.",
            "insight_ids": ["ins-release001"],
            "signal_ids": ["sig-release001"],
        },
        "quality": {"quality_score": 8.5, "rejection_tags": []},
        "evaluation": {"overall_score": 88.0, "recommendation": "yes"},
    }


def test_dry_run_returns_endpoint_payload_and_no_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitLabReleasePublisher(
        "group/subgroup/project",
        token="secret",
        tag_name="v1.2.3",
        release_name="Release v1.2.3",
        description="Generated release notes",
        ref="main",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.project == "group/subgroup/project"
    assert result.endpoint == (
        "https://gitlab.com/api/v4/projects/group%2Fsubgroup%2Fproject/releases"
    )
    assert result.release_tag is None
    assert result.release_url is None
    assert result.payload == {
        "project": "group/subgroup/project",
        "tag_name": "v1.2.3",
        "name": "Release v1.2.3",
        "description": "Generated release notes",
        "metadata": {
            "publisher": "max.gitlab_releases",
            "source_system": "max",
            "source_type": "design_brief",
            "idea_id": "bu-release001",
            "design_brief_id": "dbf-release001",
            "schema_version": "tact-spec-preview/v1",
            "kind": "tact.project_spec",
            "project": "group/subgroup/project",
            "tag_name": "v1.2.3",
            "release_name": "Release v1.2.3",
            "ref": "main",
        },
        "ref": "main",
    }
    assert "token" not in json.dumps(result.payload).lower()


def test_default_payload_maps_spec_to_release_description() -> None:
    publisher = GitLabReleasePublisher("group/project", tag_name="release/dbf-release001")

    payload = publisher.build_release_payload(_tact_spec()).to_dict()

    assert payload["name"] == "GitLab Release Publisher"
    assert payload["description"].startswith("## GitLab Release Publisher")
    assert "Design brief ID: dbf-release001" in payload["description"]
    assert '"kind": "tact.project_spec"' in payload["description"]
    assert payload["metadata"]["source_type"] == "design_brief"


def test_buildable_unit_payload_is_supported() -> None:
    unit = BuildableUnit(
        id="bu-unit001",
        title="Buildable Release",
        one_liner="Publish buildable units as releases.",
        category="automation",
        problem="No release handoff exists.",
        solution="Create a GitLab release.",
        value_proposition="Traceable release artifact",
        status="approved",
        domain="devtools",
    )
    publisher = GitLabReleasePublisher("group/project", tag_name="v0.1.0")

    payload = publisher.build_release_payload(unit).to_dict()

    assert payload["name"] == "Buildable Release"
    assert payload["metadata"]["source_type"] == "idea"
    assert payload["metadata"]["idea_id"] == "bu-unit001"
    assert "Publish buildable units as releases." in payload["description"]


def test_live_publish_posts_expected_gitlab_release_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            201,
            json={
                "tag_name": "v1.2.3",
                "_links": {
                    "self": "https://gitlab.com/group/project/-/releases/v1.2.3",
                },
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitLabReleasePublisher(
        project_path="group/project",
        token="glpat_secret",
        tag_name="v1.2.3",
        release_name="Release v1.2.3",
        description="Generated release notes",
        ref="main",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 201
    assert result.release_tag == "v1.2.3"
    assert result.release_url == "https://gitlab.com/group/project/-/releases/v1.2.3"
    assert requests[0].method == "POST"
    assert requests[0].url == "https://gitlab.com/api/v4/projects/group%2Fproject/releases"
    assert requests[0].headers["Authorization"] == "Bearer glpat_secret"
    assert requests[0].headers["User-Agent"] == "max-gitlab-releases-publisher/1"
    assert _json_from_request(requests[0]) == {
        "tag_name": "v1.2.3",
        "name": "Release v1.2.3",
        "description": "Generated release notes",
        "ref": "main",
    }
    assert result.payload["metadata"]["gitlab_release_tag"] == "v1.2.3"
    assert (
        result.payload["metadata"]["gitlab_release_url"]
        == "https://gitlab.com/group/project/-/releases/v1.2.3"
    )


def test_from_env_reads_gitlab_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITLAB_PROJECT_PATH", "env-group/env-project")
    monkeypatch.setenv("GITLAB_TOKEN", "env-token")
    monkeypatch.setenv("GITLAB_BASE_URL", "https://gitlab.example")
    monkeypatch.setenv("GITLAB_RELEASE_TAG", "v2.0.0")
    monkeypatch.setenv("GITLAB_RELEASE_NAME", "Env release")
    monkeypatch.setenv("GITLAB_RELEASE_REF", "develop")

    publisher = GitLabReleasePublisher.from_env()
    result = publisher.publish(_tact_spec(), dry_run=True)

    assert publisher.project == "env-group/env-project"
    assert publisher.token == "env-token"
    assert result.endpoint == (
        "https://gitlab.example/api/v4/projects/env-group%2Fenv-project/releases"
    )
    assert result.payload["tag_name"] == "v2.0.0"
    assert result.payload["name"] == "Env release"
    assert result.payload["ref"] == "develop"


def test_invalid_configuration_and_export() -> None:
    with pytest.raises(GitLabReleasePublishError, match="project ID/path"):
        GitLabReleasePublisher(None, tag_name="v1.0.0")

    with pytest.raises(GitLabReleasePublishError, match="tag name"):
        GitLabReleasePublisher("group/project").publish(
            _tact_spec(),
            dry_run=True,
            tag_name="bad tag",
        )

    assert ExportedGitLabReleasePublisher is GitLabReleasePublisher


def test_live_publish_requires_token_before_http_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("missing token should fail before HTTP")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GitLabReleasePublisher("group/project", tag_name="v1.0.0", client=client)

    with pytest.raises(GitLabReleasePublishError, match="GITLAB_TOKEN"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_live_publish_raises_duplicate_release_error() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                409,
                json={"message": "Release already exists"},
            )
        )
    )
    publisher = GitLabReleasePublisher(
        "group/project",
        tag_name="v1.0.0",
        token="secret",
        client=client,
    )

    with pytest.raises(GitLabReleasePublishError, match="already exists") as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc.value.status_code == 409


def test_live_publish_raises_error_with_status_code_on_non_2xx() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(500, json={"message": "server error"})
        )
    )
    publisher = GitLabReleasePublisher(
        "group/project",
        tag_name="v1.0.0",
        token="secret",
        client=client,
    )

    with pytest.raises(GitLabReleasePublishError, match="HTTP 500") as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc.value.status_code == 500


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
