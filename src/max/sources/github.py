"""GitHub source adapter — trending repos and recent activity."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"

_DEFAULT_TOPICS = ["mcp", "ai-agent", "llm", "developer-tools", "cli"]


class GitHubAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "github"

    @property
    def source_type(self) -> str:
        return SignalSourceType.TRENDING.value

    @property
    def topics(self) -> list[str]:
        return self._configured_terms("topics", _DEFAULT_TOPICS)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        topics = self.topics
        per_topic = max(limit // len(topics), 3)

        headers = {"Accept": "application/vnd.github+json"}
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            try:
                import subprocess
                result = subprocess.run(
                    ["vault", "get", "github/token"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    token = result.stdout.strip()
            except Exception:
                pass
        if token:
            headers["Authorization"] = f"Bearer {token}"

        # Search for repos created/updated in the last 7 days
        since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for topic in topics:
                if len(signals) >= limit:
                    break
                try:
                    resp = await fetch_with_retry(
                        f"{GITHUB_API}/search/repositories",
                        client,
                        adapter_name=self.name,
                        params={
                            "q": f"topic:{topic} pushed:>{since}",
                            "sort": "stars",
                            "order": "desc",
                            "per_page": per_topic,
                        },
                    )
                    data = resp.json()
                except AdapterFetchError:
                    logger.warning(
                        "GitHub search failed for topic: %s", topic, exc_info=True,
                    )
                    continue

                for repo in data.get("items", []):
                    name = repo.get("full_name", "")
                    description = repo.get("description", "") or ""
                    stars = repo.get("stargazers_count", 0)
                    language = repo.get("language")
                    topics = repo.get("topics", [])

                    signals.append(
                        Signal(
                            source_type=SignalSourceType.TRENDING,
                            source_adapter=self.name,
                            title=name,
                            content=description[:500] if description else name,
                            url=repo.get("html_url", ""),
                            author=repo.get("owner", {}).get("login"),
                            published_at=_parse_dt(repo.get("created_at")),
                            tags=_build_tags(topics, language, topic),
                            credibility=min(stars / 5000, 1.0),
                            metadata={
                                "stars": stars,
                                "forks": repo.get("forks_count", 0),
                                "language": language,
                                "topics": topics[:10],
                                "search_topic": topic,
                                "open_issues": repo.get("open_issues_count", 0),
                                "updated_at": repo.get("updated_at"),
                            },
                        )
                    )

        return signals[:limit]


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _build_tags(topics: list[str], language: str | None, search_topic: str) -> list[str]:
    """Build tags from repo topics, language, and search context."""
    tags: set[str] = set()

    # Map GitHub topics to our tag vocabulary
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

    # Add search topic as tag
    search_tag = topic_map.get(search_topic, search_topic)
    tags.add(search_tag)

    return sorted(tags)
