"""GitHub source adapter for repository signals.

Collects repository signals including stars, forks, issues, and pull request
activity via the GitHub REST API.  Fetches trending repositories, release
activity, and contributor metrics to identify popular projects and emerging
frameworks.
"""

from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime, timedelta, timezone

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"

_DEFAULT_TOPICS = ["mcp", "ai-agent", "llm", "developer-tools", "cli"]


def _get_token() -> str | None:
    """Resolve GitHub API token from env or vault."""
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    try:
        result = subprocess.run(
            ["vault", "get", "github/token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _parse_dt(s: str | None) -> datetime | None:
    """Parse ISO 8601 datetime from GitHub API responses."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _build_tags(
    topics: list[str], language: str | None, search_topic: str,
) -> list[str]:
    """Build normalized tags from repo topics, language, and search context."""
    tags: set[str] = set()
    topic_map = {
        "mcp": "mcp",
        "model-context-protocol": "mcp",
        "ai-agent": "agent",
        "ai-agents": "agent",
        "llm": "ai",
        "large-language-model": "ai",
        "developer-tools": "devtools",
        "cli": "devtools",
        "machine-learning": "ml",
        "security": "security",
        "typescript": "typescript",
        "python": "python",
        "rust": "rust",
        "golang": "go",
    }
    for t in topics:
        mapped = topic_map.get(t)
        if mapped:
            tags.add(mapped)

    if language:
        lang_map = {
            "TypeScript": "typescript",
            "Python": "python",
            "Rust": "rust",
            "Go": "go",
            "JavaScript": "typescript",
        }
        mapped = lang_map.get(language)
        if mapped:
            tags.add(mapped)

    search_tag = topic_map.get(search_topic, search_topic)
    tags.add(search_tag)
    return sorted(tags)


class GitHubAdapter(SourceAdapter):
    """Fetches repositories by topic, language, or search query.

    Extracts stars, forks, issues count, and recent release data.
    Handles API token authentication and rate limiting via ``fetch_with_retry``.
    """

    @property
    def name(self) -> str:
        return "github_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.TRENDING.value

    @property
    def topics(self) -> list[str]:
        return self._configured_terms("topics", _DEFAULT_TOPICS)

    @property
    def language(self) -> str | None:
        lang = self._config.get("language")
        return lang if isinstance(lang, str) else None

    @property
    def query(self) -> str | None:
        q = self._config.get("query")
        return q if isinstance(q, str) else None

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen: set[str] = set()
        token = _get_token()

        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            search_queries = self._build_search_queries(since)
            per_query = max(limit // max(len(search_queries), 1), 3)

            for q in search_queries:
                if len(signals) >= limit:
                    break

                try:
                    resp = await fetch_with_retry(
                        f"{GITHUB_API}/search/repositories",
                        client,
                        adapter_name=self.name,
                        params={
                            "q": q,
                            "sort": "stars",
                            "order": "desc",
                            "per_page": per_query,
                        },
                    )
                    data = resp.json()
                except Exception:
                    logger.warning("GitHub search failed for query: %s", q, exc_info=True)
                    continue

                for repo in data.get("items", []):
                    full_name = repo.get("full_name", "")
                    if full_name in seen:
                        continue
                    seen.add(full_name)

                    repo_topics = repo.get("topics", [])
                    language = repo.get("language")
                    stars = repo.get("stargazers_count", 0)

                    signals.append(
                        Signal(
                            source_type=SignalSourceType.TRENDING,
                            source_adapter=self.name,
                            title=full_name,
                            content=(repo.get("description") or full_name)[:500],
                            url=repo.get("html_url", ""),
                            author=repo.get("owner", {}).get("login"),
                            published_at=_parse_dt(repo.get("created_at")),
                            tags=_build_tags(repo_topics, language, q.split("topic:")[-1].split()[0] if "topic:" in q else ""),
                            credibility=min(stars / 5000, 1.0),
                            metadata={
                                "stars": stars,
                                "forks": repo.get("forks_count", 0),
                                "open_issues": repo.get("open_issues_count", 0),
                                "language": language,
                                "topics": repo_topics[:10],
                                "updated_at": repo.get("updated_at"),
                                "license": (repo.get("license") or {}).get("spdx_id"),
                                "watchers": repo.get("watchers_count", 0),
                            },
                        )
                    )
                    if len(signals) >= limit:
                        break

        return signals[:limit]

    def _build_search_queries(self, since: str) -> list[str]:
        """Build GitHub search queries from config."""
        queries: list[str] = []

        if self.query:
            q = self.query
            if self.language:
                q += f" language:{self.language}"
            q += f" pushed:>{since}"
            queries.append(q)
            return queries

        for topic in self.topics:
            q = f"topic:{topic} pushed:>{since}"
            if self.language:
                q += f" language:{self.language}"
            queries.append(q)

        return queries
