"""GitLab source adapter for repository signals.

Collects project signals from GitLab instances via the GitLab REST API.
Fetches project metrics, merge request activity, and CI/CD pipeline stats.
Supports both gitlab.com and self-hosted instances.
"""

from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

GITLAB_API = "https://gitlab.com/api/v4"

_DEFAULT_TOPICS = ["mcp", "ai-agent", "llm", "machine-learning"]


def _get_token(env_var: str = "GITLAB_TOKEN") -> str | None:
    """Resolve GitLab API token from env or vault."""
    token = os.environ.get(env_var)
    if token:
        return token
    try:
        result = subprocess.run(
            ["vault", "get", "gitlab/token"],
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
    """Parse ISO 8601 datetime from GitLab API responses."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _build_tags(topics: list[str], search_term: str) -> list[str]:
    """Build normalized tags from project topics and search context."""
    tags: set[str] = set()
    topic_map = {
        "mcp": "mcp",
        "ai-agent": "agent",
        "ai-agents": "agent",
        "llm": "ai",
        "machine-learning": "ml",
        "devops": "devops",
        "ci-cd": "devops",
        "security": "security",
        "python": "python",
        "typescript": "typescript",
        "rust": "rust",
        "golang": "go",
    }
    for t in topics:
        mapped = topic_map.get(t)
        if mapped:
            tags.add(mapped)
    search_tag = topic_map.get(search_term, search_term)
    if search_tag:
        tags.add(search_tag)
    tags.add("gitlab")
    return sorted(tags)


class GitLabAdapter(SourceAdapter):
    """Fetches projects by group, topic, or search.

    Extracts stars, forks, merge request activity, and pipeline status.
    Supports configurable base URL for self-hosted instances.
    """

    @property
    def name(self) -> str:
        return "gitlab_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.TRENDING.value

    @property
    def topics(self) -> list[str]:
        return self._configured_terms("topics", _DEFAULT_TOPICS)

    @property
    def base_url(self) -> str:
        configured = self._config.get("base_url")
        if isinstance(configured, str) and configured.strip():
            return configured.strip().rstrip("/")
        return GITLAB_API

    @property
    def group_id(self) -> str | None:
        gid = self._config.get("group_id")
        return str(gid) if gid is not None else None

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen: set[int] = set()
        token = _get_token()

        headers: dict[str, str] = {}
        if token:
            headers["PRIVATE-TOKEN"] = token

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            search_terms = self.topics
            per_search = max(limit // max(len(search_terms), 1), 3)

            for term in search_terms:
                if len(signals) >= limit:
                    break

                url, params = self._build_request(term, per_search)

                try:
                    resp = await fetch_with_retry(
                        url,
                        client,
                        adapter_name=self.name,
                        params=params,
                    )
                    projects = resp.json()
                except Exception:
                    logger.warning(
                        "GitLab search failed for: %s", term, exc_info=True,
                    )
                    continue

                if not isinstance(projects, list):
                    continue

                for project in projects:
                    pid = project.get("id")
                    if pid in seen:
                        continue
                    seen.add(pid)

                    stars = project.get("star_count", 0)
                    forks = project.get("forks_count", 0)
                    topics = project.get("topics", []) or project.get("tag_list", [])

                    signals.append(
                        Signal(
                            source_type=SignalSourceType.TRENDING,
                            source_adapter=self.name,
                            title=project.get("path_with_namespace", ""),
                            content=(project.get("description") or project.get("path_with_namespace", ""))[:500],
                            url=project.get("web_url", ""),
                            author=(project.get("namespace") or {}).get("name"),
                            published_at=_parse_dt(project.get("created_at")),
                            tags=_build_tags(topics, term),
                            credibility=min(stars / 2000, 1.0),
                            metadata={
                                "stars": stars,
                                "forks": forks,
                                "open_issues_count": project.get("open_issues_count", 0),
                                "topics": topics[:10],
                                "last_activity_at": project.get("last_activity_at"),
                                "visibility": project.get("visibility"),
                                "default_branch": project.get("default_branch"),
                            },
                        )
                    )
                    if len(signals) >= limit:
                        break

        return signals[:limit]

    def _build_request(self, term: str, per_page: int) -> tuple[str, dict]:
        """Build GitLab API URL and params for a search term."""
        base = self.base_url

        if self.group_id:
            url = f"{base}/groups/{self.group_id}/projects"
            params = {
                "search": term,
                "order_by": "last_activity_at",
                "sort": "desc",
                "per_page": per_page,
            }
        else:
            url = f"{base}/projects"
            params = {
                "search": term,
                "order_by": "last_activity_at",
                "sort": "desc",
                "per_page": per_page,
                "topic": term,
            }

        return url, params
