"""Tests for the LinkedIn source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.imports.linkedin_adapter import LinkedInAdapter
from max.types.signal import SignalSourceType


def _response(payload: object) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    return resp


def _post(
    post_id: str = "post123",
    *,
    commentary: str = "We're hiring AI engineers to build the next generation of developer tools",
    likes: int = 100,
    comments: int = 25,
    created_at: int = 1713780000000,
) -> dict:
    return {
        "id": post_id,
        "commentary": commentary,
        "likeCount": likes,
        "commentCount": comments,
        "createdAt": created_at,
    }


def _job(
    job_id: str = "job456",
    *,
    title: str = "Senior AI Engineer",
    company: str = "TechCorp",
    location: str = "Remote",
    description: str = "Build LLM-powered developer tools",
    skills: list[str] | None = None,
    listed_at: int = 1713780000000,
) -> dict:
    return {
        "id": job_id,
        "title": title,
        "companyName": company,
        "location": location,
        "description": description,
        "skills": skills or ["Python", "AI", "LLM"],
        "listedAt": listed_at,
    }


def test_linkedin_adapter_properties() -> None:
    adapter = LinkedInAdapter(
        config={
            "keywords": ["rust developer"],
            "access_token_env": "MY_LINKEDIN_TOKEN",
            "organization_ids": ["org1", "org2"],
        }
    )

    assert adapter.name == "linkedin"
    assert adapter.source_type == SignalSourceType.FORUM.value
    assert adapter.keywords == ["rust developer"]
    assert adapter.access_token_env == "MY_LINKEDIN_TOKEN"
    assert adapter.organization_ids == ["org1", "org2"]


def test_linkedin_adapter_defaults() -> None:
    adapter = LinkedInAdapter()

    assert adapter.name == "linkedin"
    assert adapter.access_token_env == "LINKEDIN_ACCESS_TOKEN"
    assert len(adapter.keywords) > 0
    assert adapter.organization_ids == []


@pytest.mark.asyncio
async def test_linkedin_returns_empty_without_token() -> None:
    adapter = LinkedInAdapter(config={"keywords": ["ai"]})
    with patch.dict("os.environ", {}, clear=True):
        signals = await adapter.fetch(limit=10)
    assert signals == []


@pytest.mark.asyncio
async def test_linkedin_fetches_org_posts() -> None:
    adapter = LinkedInAdapter(config={"organization_ids": ["org1"], "keywords": []})

    posts_response = {
        "elements": [
            _post("p1", commentary="Launching new AI developer tools"),
            _post("p2", commentary="Open source contribution guide"),
        ],
    }

    with (
        patch.dict("os.environ", {"LINKEDIN_ACCESS_TOKEN": "test-token"}),
        patch("max.imports.linkedin_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
    ):
        mock_fetch.return_value = _response(posts_response)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert signals[0].source_adapter == "linkedin"
    assert signals[0].source_type == SignalSourceType.FORUM
    assert "AI developer tools" in signals[0].title
    assert signals[0].metadata["type"] == "post"


@pytest.mark.asyncio
async def test_linkedin_fetches_jobs() -> None:
    adapter = LinkedInAdapter(config={"keywords": ["AI engineer"], "organization_ids": []})

    jobs_response = {
        "elements": [
            _job("j1", title="AI Engineer", company="StartupAI"),
            _job("j2", title="ML Platform Lead", company="BigTech"),
        ],
    }

    with (
        patch.dict("os.environ", {"LINKEDIN_ACCESS_TOKEN": "test-token"}),
        patch("max.imports.linkedin_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
    ):
        mock_fetch.return_value = _response(jobs_response)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert signals[0].metadata["type"] == "job"
    assert signals[0].metadata["company"] == "StartupAI"
    assert "AI Engineer at StartupAI" in signals[0].title
    assert "hiring" in signals[0].tags


@pytest.mark.asyncio
async def test_linkedin_extracts_post_metrics() -> None:
    adapter = LinkedInAdapter(config={"organization_ids": ["org1"], "keywords": []})

    posts_response = {
        "elements": [_post("p1", likes=500, comments=80)],
    }

    with (
        patch.dict("os.environ", {"LINKEDIN_ACCESS_TOKEN": "test-token"}),
        patch("max.imports.linkedin_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
    ):
        mock_fetch.return_value = _response(posts_response)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["likes"] == 500
    assert signals[0].metadata["comments"] == 80


@pytest.mark.asyncio
async def test_linkedin_extracts_job_skills() -> None:
    adapter = LinkedInAdapter(config={"keywords": ["dev"], "organization_ids": []})

    jobs_response = {
        "elements": [
            _job("j1", skills=["Python", "Rust", "TypeScript"]),
        ],
    }

    with (
        patch.dict("os.environ", {"LINKEDIN_ACCESS_TOKEN": "test-token"}),
        patch("max.imports.linkedin_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
    ):
        mock_fetch.return_value = _response(jobs_response)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["skills"] == ["Python", "Rust", "TypeScript"]


@pytest.mark.asyncio
async def test_linkedin_handles_fetch_error() -> None:
    from max.sources.base import AdapterFetchError

    adapter = LinkedInAdapter(config={"organization_ids": ["org1"], "keywords": []})

    with (
        patch.dict("os.environ", {"LINKEDIN_ACCESS_TOKEN": "test-token"}),
        patch("max.imports.linkedin_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
    ):
        mock_fetch.side_effect = AdapterFetchError("linkedin", 401, "https://api.linkedin.com/...")
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_linkedin_deduplicates_by_id() -> None:
    adapter = LinkedInAdapter(config={"organization_ids": ["org1", "org2"], "keywords": []})

    posts_response = {"elements": [_post("p1")]}

    with (
        patch.dict("os.environ", {"LINKEDIN_ACCESS_TOKEN": "test-token"}),
        patch("max.imports.linkedin_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
    ):
        mock_fetch.return_value = _response(posts_response)
        signals = await adapter.fetch(limit=10)

    # Same post ID from two orgs should deduplicate
    assert len(signals) == 1


@pytest.mark.asyncio
async def test_linkedin_respects_limit() -> None:
    adapter = LinkedInAdapter(config={"keywords": ["ai"], "organization_ids": []})

    jobs_response = {
        "elements": [_job(f"j{i}", title=f"Job {i}") for i in range(20)],
    }

    with (
        patch.dict("os.environ", {"LINKEDIN_ACCESS_TOKEN": "test-token"}),
        patch("max.imports.linkedin_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
    ):
        mock_fetch.return_value = _response(jobs_response)
        signals = await adapter.fetch(limit=5)

    assert len(signals) == 5


@pytest.mark.asyncio
async def test_linkedin_returns_empty_for_zero_limit() -> None:
    adapter = LinkedInAdapter(config={"keywords": ["ai"]})
    with patch.dict("os.environ", {"LINKEDIN_ACCESS_TOKEN": "test-token"}):
        signals = await adapter.fetch(limit=0)
    assert signals == []


def test_linkedin_tag_extraction() -> None:
    from max.imports.linkedin_adapter import _extract_tags

    tags = _extract_tags("Hiring AI engineers for LLM platform development")
    assert "linkedin" in tags
    assert "ai" in tags
    assert "hiring" in tags


def test_linkedin_credibility_calculation() -> None:
    from max.imports.linkedin_adapter import _credibility

    # Baseline
    assert _credibility(likes=0, comments=0) == 0.3

    # With engagement
    cred = _credibility(likes=100, comments=50)
    assert cred > 0.3

    # Capped at 1.0
    assert _credibility(likes=10000, comments=5000) == 1.0
