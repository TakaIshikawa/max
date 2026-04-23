"""GitLab releases source adapter -- release activity from configured projects."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, unquote

import httpx

from max.sources.base import (
    AdapterCircuitOpenError,
    AdapterFetchError,
    AdapterRateLimitError,
    SourceAdapter,
    fetch_with_retry,
)
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

DEFAULT_GITLAB_BASE_URL = "https://gitlab.com"


class GitLabReleasesAdapter(SourceAdapter):
    """Fetch GitLab project releases and normalize them into registry signals."""

    @property
    def name(self) -> str:
        return "gitlab_releases"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def projects(self) -> list[str]:
        values = self._config.get("projects", [])
        projects: list[str] = []
        seen: set[str] = set()
        for value in values:
            if not isinstance(value, (str, int)) or isinstance(value, bool):
                continue
            project = str(value).strip()
            if not project or project in seen:
                continue
            seen.add(project)
            projects.append(project)
        return projects

    @property
    def gitlab_base_url(self) -> str:
        value = self._config.get("gitlab_base_url", DEFAULT_GITLAB_BASE_URL)
        if not isinstance(value, str) or not value.strip():
            return DEFAULT_GITLAB_BASE_URL
        return value.strip().rstrip("/")

    @property
    def token_env(self) -> str:
        value = self._config.get("token_env", "GITLAB_TOKEN")
        return value if isinstance(value, str) and value.strip() else "GITLAB_TOKEN"

    @property
    def include_prerelease(self) -> bool:
        return bool(self._config.get("include_prerelease", False))

    @property
    def max_age_days(self) -> int | None:
        value = self._config.get("max_age_days")
        if value is None or isinstance(value, bool):
            return None
        try:
            days = int(value)
        except (TypeError, ValueError):
            return None
        return days if days > 0 else None

    @property
    def tags(self) -> list[str]:
        return self._configured_terms("tags", [])

    @property
    def query_terms(self) -> list[str]:
        return self._configured_terms("query_terms", [])

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.projects:
            return []

        signals: list[Signal] = []
        seen_urls: set[str] = set()
        per_page = min(max(limit, 1), 100)
        headers = {"Accept": "application/json"}
        token = os.environ.get(self.token_env)
        if token:
            headers["PRIVATE-TOKEN"] = token

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for project in self.projects:
                if len(signals) >= limit:
                    break

                page = 1
                while len(signals) < limit:
                    try:
                        releases = await self._fetch_page(
                            client,
                            project=project,
                            page=page,
                            per_page=per_page,
                        )
                    except (AdapterRateLimitError, AdapterCircuitOpenError):
                        raise
                    except (AdapterFetchError, httpx.RequestError, httpx.TimeoutException):
                        logger.warning(
                            "GitLab releases fetch failed for project=%s page=%s",
                            project,
                            page,
                            exc_info=True,
                        )
                        break
                    except (ValueError, TypeError):
                        logger.warning(
                            "GitLab releases response parse failed for project=%s page=%s",
                            project,
                            page,
                            exc_info=True,
                        )
                        break

                    if not releases:
                        break

                    for release in releases:
                        if len(signals) >= limit:
                            break
                        signal = self._release_to_signal(project, release)
                        if signal is None or signal.url in seen_urls:
                            continue
                        seen_urls.add(signal.url)
                        signals.append(signal)

                    if len(releases) < per_page:
                        break
                    page += 1

        return signals[:limit]

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        *,
        project: str,
        page: int,
        per_page: int,
    ) -> list[dict]:
        response = await fetch_with_retry(
            _releases_url(self.gitlab_base_url, project),
            client,
            adapter_name=self.name,
            params={"per_page": per_page, "page": page},
        )
        data = response.json()
        if not isinstance(data, list):
            raise ValueError("GitLab releases response was not a list")
        return data

    def _release_to_signal(self, project: str, release: object) -> Signal | None:
        if not isinstance(release, dict):
            return None
        if _is_prerelease(release) and not self.include_prerelease:
            return None

        url = _release_url(release)
        tag_name = _str_value(release.get("tag_name"))
        name = _str_value(release.get("name"))
        if not url or not (tag_name or name):
            return None

        published_at = _parse_dt(release.get("released_at")) or _parse_dt(release.get("created_at"))
        if self._is_too_old(published_at):
            return None

        description = _str_value(release.get("description"))
        evidence_tags = _build_evidence_tags(project, release)
        if not _matches_terms(self.query_terms, project, release, evidence_tags):
            return None
        if not _matches_terms(self.tags, project, release, evidence_tags):
            return None

        title = _release_title(project, release)
        return Signal(
            source_type=SignalSourceType.REGISTRY,
            source_adapter=self.name,
            title=title,
            content=description[:4000] if description else title,
            url=url,
            published_at=published_at,
            tags=evidence_tags,
            credibility=0.6,
            metadata={
                "project_id": release.get("project_id"),
                "project_path": project,
                "tag_name": tag_name or None,
                "commit_path": _commit_path(release.get("commit")),
                "milestones": _milestone_titles(release.get("milestones")),
                "assets_count": _assets_count(release.get("assets")),
                "evidence_tags": evidence_tags,
            },
        )

    def _is_too_old(self, published_at: datetime | None) -> bool:
        if self.max_age_days is None or published_at is None:
            return False
        compare_at = published_at
        if compare_at.tzinfo is None:
            compare_at = compare_at.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.max_age_days)
        return compare_at < cutoff


def _releases_url(base_url: str, project: str) -> str:
    api_base = base_url.rstrip("/")
    if not api_base.endswith("/api/v4"):
        api_base = f"{api_base}/api/v4"
    return f"{api_base}/projects/{_encode_project(project)}/releases"


def _encode_project(project: str) -> str:
    return quote(unquote(str(project).strip()), safe="")


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _release_title(project: str, release: dict) -> str:
    name = _str_value(release.get("name"))
    tag = _str_value(release.get("tag_name"))
    if name and tag and name != tag:
        return f"{project} {name} ({tag})"
    if name or tag:
        return f"{project} {name or tag}"
    return project


def _release_url(release: dict) -> str:
    links = release.get("_links")
    if isinstance(links, dict):
        self_url = _str_value(links.get("self"))
        if self_url:
            return self_url
    return _str_value(release.get("url")) or _str_value(release.get("web_url"))


def _commit_path(commit: object) -> str | None:
    if not isinstance(commit, dict):
        return None
    return _str_value(commit.get("web_url")) or _str_value(commit.get("id")) or None


def _milestone_titles(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    titles: list[str] = []
    for item in value:
        if isinstance(item, dict):
            title = _str_value(item.get("title"))
            if title:
                titles.append(title)
        elif isinstance(item, str) and item.strip():
            titles.append(item.strip())
    return titles[:10]


def _assets_count(value: object) -> int:
    if not isinstance(value, dict):
        return 0
    count = 0
    for key in ("links", "sources"):
        items = value.get(key)
        if isinstance(items, list):
            count += len(items)
    return count


def _is_prerelease(release: dict) -> bool:
    for key in ("prerelease", "pre_release", "upcoming_release"):
        value = release.get(key)
        if isinstance(value, bool):
            return value
    return False


def _build_evidence_tags(project: str, release: dict) -> list[str]:
    tags: set[str] = {"gitlab", "release"}
    tag_name = _str_value(release.get("tag_name"))
    if tag_name:
        tags.add(tag_name.lower())

    text = " ".join(
        [
            project,
            _str_value(release.get("name")),
            tag_name,
            _str_value(release.get("description")),
            " ".join(_milestone_titles(release.get("milestones"))),
        ]
    ).lower()
    keyword_map = {
        "ai": ["ai", "artificial intelligence"],
        "agent": ["agent", "agentic"],
        "llm": ["llm", "language model"],
        "mcp": ["mcp", "model context protocol"],
        "security": ["security", "vulnerability", "cve"],
        "python": ["python"],
        "javascript": ["javascript", "typescript", "node"],
        "devtools": ["cli", "sdk", "developer tool"],
    }
    for tag, keywords in keyword_map.items():
        if any(keyword in text for keyword in keywords):
            tags.add(tag)
    return sorted(tags)[:10]


def _matches_terms(terms: list[str], project: str, release: dict, evidence_tags: list[str]) -> bool:
    if not terms:
        return True
    haystack = " ".join(
        [
            project,
            _str_value(release.get("name")),
            _str_value(release.get("tag_name")),
            _str_value(release.get("description")),
            " ".join(_milestone_titles(release.get("milestones"))),
            " ".join(evidence_tags),
        ]
    ).lower()
    return any(term.lower() in haystack for term in terms if term)


def _str_value(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""
