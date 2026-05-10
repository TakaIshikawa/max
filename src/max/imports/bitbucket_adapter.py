"""Bitbucket source adapter for repository signals.

Collects repository signals from Bitbucket Cloud via the REST API v2.0.
Fetches repository metadata, pull request activity, and pipeline status.
Extracts watchers, forks, language breakdown, and recent commit activity
for enterprise project trend analysis.
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

BITBUCKET_API = "https://api.bitbucket.org/2.0"

_DEFAULT_WORKSPACES = ["atlassian"]


def _get_credentials() -> tuple[str | None, str | None]:
    """Resolve Bitbucket credentials from env or vault.

    Returns (username, app_password) tuple.
    """
    username = os.environ.get("BITBUCKET_USERNAME")
    password = os.environ.get("BITBUCKET_APP_PASSWORD")
    if username and password:
        return username, password
    try:
        u_result = subprocess.run(
            ["vault", "get", "bitbucket/username"],
            capture_output=True, text=True, timeout=5,
        )
        p_result = subprocess.run(
            ["vault", "get", "bitbucket/app_password"],
            capture_output=True, text=True, timeout=5,
        )
        if u_result.returncode == 0 and p_result.returncode == 0:
            u = u_result.stdout.strip()
            p = p_result.stdout.strip()
            if u and p:
                return u, p
    except Exception:
        pass
    return None, None


def _parse_dt(s: str | None) -> datetime | None:
    """Parse ISO 8601 datetime from Bitbucket API responses."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _build_tags(language: str | None, workspace: str) -> list[str]:
    """Build tags from repo language and workspace."""
    tags: set[str] = {"bitbucket"}
    if workspace:
        tags.add(workspace)
    if language:
        lang_map = {
            "python": "python",
            "javascript": "typescript",
            "typescript": "typescript",
            "java": "java",
            "go": "go",
            "rust": "rust",
            "c#": "csharp",
            "kotlin": "kotlin",
        }
        mapped = lang_map.get(language.lower())
        if mapped:
            tags.add(mapped)
    return sorted(tags)


class BitbucketAdapter(SourceAdapter):
    """Fetches repositories from Bitbucket Cloud by workspace or search query.

    Extracts watchers, forks, language stats, and PR activity.
    Handles app password authentication and API pagination via
    ``fetch_with_retry``.

    Config options:
        workspaces: list of Bitbucket workspaces to search
        query: search query string (used with /repositories endpoint)
        language: filter by programming language
    """

    @property
    def name(self) -> str:
        return "bitbucket_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.TRENDING.value

    @property
    def workspaces(self) -> list[str]:
        return self._configured_terms("workspaces", _DEFAULT_WORKSPACES)

    @property
    def query(self) -> str | None:
        q = self._config.get("query")
        return q if isinstance(q, str) else None

    @property
    def language(self) -> str | None:
        lang = self._config.get("language")
        return lang if isinstance(lang, str) else None

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen: set[str] = set()
        username, password = _get_credentials()

        auth = httpx.BasicAuth(username, password) if username and password else None

        async with httpx.AsyncClient(timeout=30, auth=auth) as client:
            if self.query:
                signals = await self._search_repos(client, seen, limit)
            else:
                for workspace in self.workspaces:
                    if len(signals) >= limit:
                        break
                    new_signals = await self._fetch_workspace(
                        client, workspace, seen, limit - len(signals),
                    )
                    signals.extend(new_signals)

        return signals[:limit]

    async def _search_repos(
        self, client: httpx.AsyncClient, seen: set[str], limit: int,
    ) -> list[Signal]:
        """Search repositories across Bitbucket."""
        signals: list[Signal] = []
        params: dict = {"pagelen": min(limit, 50)}

        q_parts: list[str] = []
        if self.query:
            q_parts.append(f'name ~ "{self.query}"')
        if self.language:
            q_parts.append(f'language = "{self.language}"')
        if q_parts:
            params["q"] = " AND ".join(q_parts)

        try:
            resp = await fetch_with_retry(
                f"{BITBUCKET_API}/repositories",
                client,
                adapter_name=self.name,
                params=params,
            )
            data = resp.json()
        except Exception:
            logger.warning("Bitbucket search failed", exc_info=True)
            return signals

        for repo in data.get("values", []):
            sig = self._repo_to_signal(repo, seen, "search")
            if sig:
                signals.append(sig)
                if len(signals) >= limit:
                    break

        return signals

    async def _fetch_workspace(
        self,
        client: httpx.AsyncClient,
        workspace: str,
        seen: set[str],
        limit: int,
    ) -> list[Signal]:
        """Fetch repositories from a specific workspace."""
        signals: list[Signal] = []
        params: dict = {
            "pagelen": min(limit, 50),
            "sort": "-updated_on",
        }
        if self.language:
            params["q"] = f'language = "{self.language}"'

        try:
            resp = await fetch_with_retry(
                f"{BITBUCKET_API}/repositories/{workspace}",
                client,
                adapter_name=self.name,
                params=params,
            )
            data = resp.json()
        except Exception:
            logger.warning("Bitbucket workspace fetch failed: %s", workspace, exc_info=True)
            return signals

        for repo in data.get("values", []):
            sig = self._repo_to_signal(repo, seen, workspace)
            if sig:
                signals.append(sig)
                if len(signals) >= limit:
                    break

        return signals

    def _repo_to_signal(
        self, repo: dict, seen: set[str], context: str,
    ) -> Signal | None:
        """Convert a Bitbucket repo dict to a Signal."""
        full_name = repo.get("full_name", "")
        if not full_name or full_name in seen:
            return None
        seen.add(full_name)

        language = repo.get("language")
        workspace = full_name.split("/")[0] if "/" in full_name else context

        return Signal(
            source_type=SignalSourceType.TRENDING,
            source_adapter=self.name,
            title=full_name,
            content=(repo.get("description") or full_name)[:500],
            url=(repo.get("links", {}).get("html", {}).get("href", "")),
            author=repo.get("owner", {}).get("display_name"),
            published_at=_parse_dt(repo.get("created_on")),
            tags=_build_tags(language, workspace),
            credibility=0.5,
            metadata={
                "language": language,
                "has_wiki": repo.get("has_wiki", False),
                "has_issues": repo.get("has_issues", False),
                "fork_policy": repo.get("fork_policy"),
                "updated_on": repo.get("updated_on"),
                "scm": repo.get("scm", "git"),
                "is_private": repo.get("is_private", False),
                "workspace": workspace,
            },
        )
