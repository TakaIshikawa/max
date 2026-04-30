"""Tests for publishing design briefs to Bitbucket issues through the REST API."""

from __future__ import annotations

import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode


@pytest.fixture
def db_path(tmp_path) -> str:
    path = str(tmp_path / "test_design_brief_bitbucket_api.db")
    Store(db_path=path, wal_mode=True).close()
    return path


@pytest.fixture
def client(db_path: str) -> TestClient:
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


def _seed_design_brief(db_path: str) -> str:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        unit = BuildableUnit(
            id="bu-bitbucket-brief",
            title="Bitbucket Brief Source",
            one_liner="Publish design briefs to Bitbucket issues",
            category=BuildableCategory.APPLICATION,
            ideation_mode=IdeationMode.DIRECT,
            problem="Design briefs stall before repository issue tracking.",
            solution="Create a Bitbucket issue from the persisted brief.",
            value_proposition="Planning handoffs stay visible for Bitbucket teams.",
            buyer="Product lead",
            specific_user="Engineering manager",
            workflow_context="Execution planning",
            evidence_rationale="Teams requested Bitbucket issue handoff.",
            domain="devtools",
        )
        store.insert_buildable_unit(unit)
        return store.insert_design_brief(
            ProjectBrief(
                title="Bitbucket Design Brief",
                domain="devtools",
                theme="execution-handoff",
                lead=Candidate(unit=unit),
                readiness_score=86.0,
                why_this_now="Planning artifacts need direct follow-through.",
                merged_product_concept="A Bitbucket issue publisher for design briefs.",
                synthesis_rationale="The source idea is ready for implementation planning.",
                mvp_scope=["Render Bitbucket issue payload", "Create Bitbucket issue"],
                first_milestones=["Ship REST endpoint"],
                validation_plan="Dry run, then create a fake transport issue.",
                risks=["Incorrect Bitbucket credentials"],
                source_idea_ids=["bu-bitbucket-brief", "bu-supporting-bitbucket"],
            )
        )
    finally:
        store.close()


def test_publish_design_brief_bitbucket_dry_run_returns_deterministic_payload(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("BITBUCKET_USERNAME", raising=False)
    monkeypatch.delenv("BITBUCKET_APP_PASSWORD", raising=False)

    body = {
        "workspace": "max-team",
        "repository": "handoffs",
        "title": "Custom Bitbucket Brief",
        "issue_kind": "enhancement",
        "priority": "major",
        "dry_run": True,
    }
    first = client.post(f"/api/v1/design-briefs/{brief_id}/publish/bitbucket", json=body)
    second = client.post(f"/api/v1/design-briefs/{brief_id}/publish/bitbucket", json=body)

    assert first.status_code == 200
    assert second.status_code == 200
    data = first.json()
    assert data["design_brief_id"] == brief_id
    assert data["workspace"] == "max-team"
    assert data["repository"] == "handoffs"
    assert data["dry_run"] is True
    assert data["status_code"] is None
    assert data["issue_id"] is None
    assert data["issue_url"] is None
    assert data["attempts"] == 0
    assert data["title"] == "[Max] Custom Bitbucket Brief"
    assert data["content_preview"] == second.json()["content_preview"]
    assert data["kind"] == "enhancement"
    assert data["priority"] == "major"
    assert "A Bitbucket issue publisher for design briefs." in data["payload"]["content"]
    assert "- Buyer: Product lead" in data["payload"]["content"]
    assert "- Workflow context: Execution planning" in data["payload"]["content"]
    assert "Dry run, then create a fake transport issue." in data["payload"]["content"]
    assert "- Render Bitbucket issue payload" in data["payload"]["content"]
    assert "- Incorrect Bitbucket credentials" in data["payload"]["content"]
    assert "bu-supporting-bitbucket" in data["payload"]["content"]
    assert data["payload"]["metadata"]["design_brief_id"] == brief_id
    assert data["payload"]["metadata"]["source_type"] == "design_brief"
    assert data["provider_metadata"]["issue_endpoint"].endswith(
        "/repositories/max-team/handoffs/issues"
    )
    assert data["request_summary"]["app_password"] is None
    assert data["publication_attempt"]["target_type"] == "bitbucket_issue"
    assert data["publication_attempt"]["idea_id"] == brief_id
    assert data["publication_attempt"]["status"] == "success"


def test_publish_design_brief_bitbucket_live_success_with_fake_transport(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            201,
            json={
                "id": 42,
                "links": {
                    "html": {
                        "href": "https://bitbucket.org/max-team/handoffs/issues/42/bitbucket-design-brief"
                    }
                },
            },
        )

    def publisher_from_env(**kwargs):
        from max.publisher.bitbucket_issues import BitbucketIssuePublisher

        return BitbucketIssuePublisher(
            kwargs["workspace"],
            kwargs["repository"],
            username=kwargs["username"],
            app_password=kwargs["app_password"],
            api_url=kwargs["api_url"] or "https://api.bitbucket.test/2.0",
            issue_kind=kwargs["issue_kind"],
            priority=kwargs["priority"],
            timeout=kwargs["timeout"],
            max_retries=kwargs["max_retries"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.BitbucketIssuePublisher.from_env", publisher_from_env)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/bitbucket",
        json={
            "workspace": "max-team",
            "repository": "handoffs",
            "username": "agent@example.com",
            "app_password": "bb_app_password",
            "issue_kind": "task",
            "priority": "critical",
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["status_code"] == 201
    assert data["issue_id"] == 42
    assert data["issue_url"] == (
        "https://bitbucket.org/max-team/handoffs/issues/42/bitbucket-design-brief"
    )
    assert data["provider_metadata"]["bitbucket_issue_id"] == 42
    assert data["request_summary"]["app_password"] == "[redacted]"
    assert "bb_app_password" not in response.text
    assert data["publication_attempt"]["target_url"] == data["issue_url"]
    assert len(requests) == 1

    posted = json.loads(requests[0].content)
    assert posted["title"] == "[Max] Bitbucket Design Brief"
    assert posted["kind"] == "task"
    assert posted["priority"] == "critical"
    assert "A Bitbucket issue publisher for design briefs." in posted["content"]["raw"]
    expected_auth = base64.b64encode(b"agent@example.com:bb_app_password").decode("ascii")
    assert requests[0].headers["Authorization"] == f"Basic {expected_auth}"

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["status"] == "success"
        assert attempts[0]["response_status"] == 201
    finally:
        store.close()


def test_publish_design_brief_bitbucket_live_requires_credentials_and_records_failure(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("BITBUCKET_USERNAME", raising=False)
    monkeypatch.delenv("BITBUCKET_APP_PASSWORD", raising=False)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/bitbucket",
        json={"workspace": "max-team", "repository": "handoffs", "dry_run": False},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "BITBUCKET_USERNAME and BITBUCKET_APP_PASSWORD are required" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "bitbucket_issue"
    assert detail["publication_attempt"]["status"] == "failure"

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
    finally:
        store.close()


def test_publish_design_brief_bitbucket_missing_brief_returns_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing briefs should not initialize the Bitbucket publisher")

    monkeypatch.setattr("max.server.api.BitbucketIssuePublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/design-briefs/dbf-missing/publish/bitbucket",
        json={"workspace": "max-team", "repository": "handoffs"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"


def test_publish_design_brief_bitbucket_provider_failure_records_attempt_and_redacts_secret(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="bad app_password=bb_secret password=bb_password")

    def publisher_from_env(**kwargs):
        from max.publisher.bitbucket_issues import BitbucketIssuePublisher

        return BitbucketIssuePublisher(
            kwargs["workspace"],
            kwargs["repository"],
            username=kwargs["username"],
            app_password=kwargs["app_password"],
            api_url=kwargs["api_url"] or "https://api.bitbucket.test/2.0",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.BitbucketIssuePublisher.from_env", publisher_from_env)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/bitbucket",
        json={
            "workspace": "max-team",
            "repository": "handoffs",
            "username": "agent@example.com",
            "app_password": "bb_app_password",
            "dry_run": False,
        },
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "Bitbucket issue publish failed with HTTP 401" in detail["message"]
    assert "bb_secret" not in response.text
    assert "bb_password" not in response.text
    assert "bb_app_password" not in response.text
    assert detail["publication_attempt"]["target_type"] == "bitbucket_issue"
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["response_status"] == 401

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
        assert "bb_secret" not in attempts[0]["error"]
        assert "bb_password" not in attempts[0]["error"]
    finally:
        store.close()
