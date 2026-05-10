"""GitHub Discussions source adapter for community Q&A signals.

Collects community Q&A and RFC signals from GitHub repositories via the
GitHub GraphQL API.  Fetches discussion threads, categories, upvotes, and
answered status.  Identifies community pain points and feature requests from
project-level discussions.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

GITHUB_GRAPHQL_API = "https://api.github.com/graphql"

_DEFAULT_REPOS = [
    "vercel/next.js", "facebook/react", "sveltejs/svelte",
    "denoland/deno", "astro-build/astro",
]

_GRAPHQL_QUERY = """
query($owner: String!, $repo: String!, $first: Int!, $after: String) {
  repository(owner: $owner, name: $repo) {
    discussions(first: $first, after: $after, orderBy: {field: CREATED_AT, direction: DESC}) {
      nodes {
        id
        title
        body
        url
        createdAt
        author { login }
        category { name }
        upvoteCount
        comments { totalCount }
        answer { id }
        labels(first: 5) { nodes { name } }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""


def _parse_dt(s: str | None) -> datetime | None:
    """Parse ISO 8601 datetime from GitHub API responses."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _get_token() -> str | None:
    """Get GitHub token from environment."""
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def _build_tags(discussion: dict) -> list[str]:
    """Build tags for a GitHub Discussion signal."""
    tags: set[str] = {"github", "discussions"}

    category = discussion.get("category", {}).get("name", "").lower()
    if category:
        tags.add(category.replace(" ", "-"))

    if discussion.get("answer"):
        tags.add("answered")

    labels = discussion.get("labels", {}).get("nodes", [])
    for label in labels[:3]:
        label_name = label.get("name", "").lower()
        if label_name:
            tags.add(label_name)

    return sorted(tags)


def _compute_credibility(discussion: dict) -> float:
    """Compute credibility based on upvotes and comments."""
    upvotes = discussion.get("upvoteCount", 0)
    comments = discussion.get("comments", {}).get("totalCount", 0)
    score = min((upvotes + comments * 2) / 100, 1.0)
    return max(score, 0.1)


class GHDiscussionsAdapter(SourceAdapter):
    """Fetches discussions from GitHub repositories via GraphQL API.

    Extracts upvote counts, answer status, labels, and comment counts.
    Uses GraphQL API with token authentication and cursor-based pagination.

    Config options:
        repos: list of owner/repo strings to fetch discussions from
        query: single repository string (owner/repo)
        token: GitHub API token (falls back to GITHUB_TOKEN env var)
    """

    @property
    def name(self) -> str:
        return "gh_discussions_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def repos(self) -> list[str]:
        return self._configured_terms("repos", _DEFAULT_REPOS)

    @property
    def query(self) -> str | None:
        q = self._config.get("query")
        return q if isinstance(q, str) else None

    @property
    def token(self) -> str | None:
        return self._config.get("token") or _get_token()

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen: set[str] = set()

        token = self.token
        if not token:
            logger.warning("No GitHub token available for GH Discussions adapter")
            return signals

        async with httpx.AsyncClient(timeout=30) as client:
            repos = [self.query] if self.query else self.repos
            for repo in repos:
                if len(signals) >= limit:
                    break
                if "/" not in repo:
                    continue
                owner, repo_name = repo.split("/", 1)
                new_signals = await self._fetch_discussions(
                    client, owner, repo_name, token, seen, limit - len(signals),
                )
                signals.extend(new_signals)

        return signals[:limit]

    async def _fetch_discussions(
        self,
        client: httpx.AsyncClient,
        owner: str,
        repo_name: str,
        token: str,
        seen: set[str],
        limit: int,
    ) -> list[Signal]:
        """Fetch discussions for a single repository."""
        signals: list[Signal] = []

        try:
            resp = await fetch_with_retry(
                GITHUB_GRAPHQL_API,
                client,
                adapter_name=self.name,
                method="POST",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "query": _GRAPHQL_QUERY,
                    "variables": {
                        "owner": owner,
                        "repo": repo_name,
                        "first": min(limit, 25),
                        "after": None,
                    },
                },
            )
            data = resp.json()
        except Exception:
            logger.warning(
                "GitHub Discussions fetch failed for: %s/%s", owner, repo_name,
                exc_info=True,
            )
            return signals

        discussions = (
            data.get("data", {})
            .get("repository", {})
            .get("discussions", {})
            .get("nodes", [])
        )

        for discussion in discussions:
            disc_id = discussion.get("id", "")
            if not disc_id or disc_id in seen:
                continue
            seen.add(disc_id)

            title = discussion.get("title", "")
            body = discussion.get("body", "")
            author = discussion.get("author", {}).get("login", "") if discussion.get("author") else ""

            signals.append(
                Signal(
                    source_type=SignalSourceType.FORUM,
                    source_adapter=self.name,
                    title=title or disc_id,
                    content=(body or title)[:500],
                    url=discussion.get("url", ""),
                    author=author or None,
                    published_at=_parse_dt(discussion.get("createdAt")),
                    tags=_build_tags(discussion),
                    credibility=_compute_credibility(discussion),
                    metadata={
                        "discussion_id": disc_id,
                        "repo": f"{owner}/{repo_name}",
                        "category": discussion.get("category", {}).get("name", ""),
                        "upvotes": discussion.get("upvoteCount", 0),
                        "comment_count": discussion.get("comments", {}).get("totalCount", 0),
                        "is_answered": discussion.get("answer") is not None,
                        "labels": [
                            l.get("name", "") for l in
                            discussion.get("labels", {}).get("nodes", [])
                        ],
                    },
                )
            )

            if len(signals) >= limit:
                break

        return signals
