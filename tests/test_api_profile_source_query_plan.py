"""API tests for profile source query plans."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from max.analysis.profile_signal_query_plan import SCHEMA_VERSION
from max.profiles.schema import DomainContext, PipelineProfile, SourceConfig
from max.server.app import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def _profile(name: str = "query-plan") -> PipelineProfile:
    return PipelineProfile(
        name=name,
        domain=DomainContext(
            name="developer-tools",
            description="Tools for software teams building and operating developer workflows.",
            categories=["mcp_server", "cli_tool"],
            target_user_types=["developers", "platform engineers"],
            workflows=["local development"],
        ),
        sources=[
            SourceConfig(
                adapter="hackernews",
                weight=2.0,
                params={"filter_keywords": ["developer", "agents"]},
            ),
            SourceConfig(
                adapter="github_issues",
                weight=1.5,
                params={"queries": ["mcp_server"]},
            ),
            SourceConfig(adapter="reddit", enabled=False),
        ],
    )


def _profile_payload(profile: PipelineProfile) -> dict:
    return profile.model_dump(mode="json")


def test_get_profile_source_query_plan_for_known_profile() -> None:
    with patch("max.profiles.loader.load_profile", return_value=_profile("devtools")):
        response = _client().get("/api/v1/profiles/devtools/source-query-plan")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["kind"] == "max.profile.signal_query_plan"
    assert payload["profile"]["name"] == "devtools"
    assert payload["profile"]["domain"] == "developer-tools"
    assert payload["summary"]["enabled_source_count"] == 2
    assert payload["summary"]["disabled_source_count"] == 1
    assert payload["category_terms"] == ["mcp_server", "cli_tool"]

    sources = {source["adapter"]: source for source in payload["sources"]}
    assert sources["hackernews"]["weight"] == 2.0
    assert sources["hackernews"]["query_terms"] == ["developer", "agents"]
    assert sources["github_issues"]["suggested_queries"]
    assert sources["github_issues"]["expected_signal_roles"] == [
        "problem evidence",
        "adoption friction",
    ]


def test_post_profile_source_query_plan_for_inline_profile_payload() -> None:
    profile = _profile("inline-plan")

    response = _client().post(
        "/api/v1/profiles/source-query-plan",
        json={"profile": _profile_payload(profile)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"]["name"] == "inline-plan"
    assert payload["domain_terms"] == ["developer-tools", "local development"]
    assert payload["target_user_terms"] == ["developers", "platform engineers"]
    assert [source["adapter"] for source in payload["sources"]] == [
        "hackernews",
        "github_issues",
    ]


def test_get_profile_source_query_plan_unknown_profile_returns_404() -> None:
    with patch("max.profiles.loader.load_profile", side_effect=FileNotFoundError("missing")):
        response = _client().get("/api/v1/profiles/missing/source-query-plan")

    assert response.status_code == 404
    assert response.json()["detail"] == "Profile not found: missing"


def test_profile_source_query_plan_includes_missing_configuration_warnings() -> None:
    sparse = PipelineProfile(
        name="sparse",
        domain=DomainContext(
            name="tiny",
            description="Short",
            categories=[],
            target_user_types=[],
        ),
        sources=[SourceConfig(adapter="hackernews")],
    )

    response = _client().post(
        "/api/v1/profiles/source-query-plan",
        json={"profile": _profile_payload(sparse)},
    )

    assert response.status_code == 200
    payload = response.json()
    warnings = {(warning["field"], warning["severity"]) for warning in payload["warnings"]}
    assert ("domain.categories", "missing") in warnings
    assert ("domain.target_user_types", "missing") in warnings
    assert ("domain.description", "weak") in warnings
    assert ("sources.hackernews.params", "weak") in warnings
    assert payload["warnings"] == payload["gaps"]
