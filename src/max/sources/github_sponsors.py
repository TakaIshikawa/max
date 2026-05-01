"""GitHub Sponsors source adapter -- funding metadata from GitHub repositories."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote

import httpx

from max.sources.base import SourceAdapter
from max.sources.errors import (
    SourceAuthError,
    SourceParseError,
    SourceRateLimitError,
    SourceTransientError,
)
from max.sources.retry import with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


@dataclass(frozen=True)
class SponsorFunding:
    """Normalized funding metadata for a GitHub repository."""

    platform: str
    url: str
    maintainer: str | None
    sponsor_enabled: bool


class GitHubSponsorsAdapter(SourceAdapter):
    """Discover GitHub repositories with funding metadata and emit funding signals."""

    @property
    def name(self) -> str:
        return "github_sponsors"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FUNDING.value

    @property
    def organizations(self) -> list[str]:
        return _string_list(self._config.get("organizations") or self._config.get("orgs"))

    @property
    def users(self) -> list[str]:
        return _string_list(self._config.get("users"))

    @property
    def topics(self) -> list[str]:
        return self._configured_terms("topics", [])

    @property
    def repositories(self) -> list[str]:
        return _string_list(self._config.get("repositories"))

    @property
    def max_repositories_per_query(self) -> int:
        return _positive_int(self._config.get("max_repositories_per_query"), default=25)

    @property
    def token_env(self) -> str:
        configured = self._config.get("token_env")
        if isinstance(configured, str) and configured.strip():
            return configured.strip()
        return "GITHUB_TOKEN"

    @property
    def token(self) -> str | None:
        configured = self._config.get("github_token") or self._config.get("token")
        if isinstance(configured, str) and configured.strip():
            return configured.strip()
        return os.environ.get(self.token_env)

    @property
    def timeout(self) -> float:
        value = self._config.get("timeout", 30)
        if isinstance(value, bool):
            return 30.0
        try:
            timeout = float(value)
        except (TypeError, ValueError):
            return 30.0
        return timeout if timeout > 0 else 30.0

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0:
            return []

        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        signals: list[Signal] = []
        seen_repositories: set[str] = set()
        seen_signal_keys: set[tuple[str, str]] = set()

        async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
            async for repo in self._iter_repositories(client):
                full_name = _repo_full_name(repo)
                if not full_name or full_name in seen_repositories:
                    continue
                seen_repositories.add(full_name)

                try:
                    profile = await self._fetch_profile(client, full_name)
                except (SourceRateLimitError, SourceAuthError):
                    raise
                except (
                    SourceTransientError,
                    SourceParseError,
                    httpx.RequestError,
                    httpx.TimeoutException,
                ):
                    logger.warning(
                        "GitHub Sponsors funding metadata fetch failed for repo: %s",
                        full_name,
                        exc_info=True,
                    )
                    continue

                funding = _sponsor_funding(profile, default_owner=_repo_owner(repo))
                if not funding:
                    continue

                evidence_url = _evidence_url(full_name, profile)
                for link in funding:
                    if len(signals) >= limit:
                        return signals[:limit]
                    signal_key = (full_name, link.url)
                    if signal_key in seen_signal_keys:
                        continue
                    seen_signal_keys.add(signal_key)
                    signals.append(
                        _to_signal(
                            repo,
                            link,
                            adapter_name=self.name,
                            evidence_url=evidence_url,
                        )
                    )

                if len(signals) >= limit:
                    break

        return signals[:limit]

    async def _iter_repositories(self, client: httpx.AsyncClient):
        for repo_name in self.repositories:
            try:
                repo = await self._fetch_repository(client, repo_name)
            except (SourceRateLimitError, SourceAuthError):
                raise
            except (
                SourceTransientError,
                SourceParseError,
                httpx.RequestError,
                httpx.TimeoutException,
            ):
                logger.warning(
                    "GitHub Sponsors repository fetch failed for repo: %s",
                    repo_name,
                    exc_info=True,
                )
                continue
            if repo:
                yield repo

        for org in self.organizations:
            try:
                repos = await self._fetch_owner_repositories(client, org, owner_type="org")
            except (SourceRateLimitError, SourceAuthError):
                raise
            except (
                SourceTransientError,
                SourceParseError,
                httpx.RequestError,
                httpx.TimeoutException,
            ):
                logger.warning(
                    "GitHub Sponsors organization repository fetch failed for org: %s",
                    org,
                    exc_info=True,
                )
                continue
            for repo in repos:
                yield repo

        for user in self.users:
            try:
                repos = await self._fetch_owner_repositories(client, user, owner_type="user")
            except (SourceRateLimitError, SourceAuthError):
                raise
            except (
                SourceTransientError,
                SourceParseError,
                httpx.RequestError,
                httpx.TimeoutException,
            ):
                logger.warning(
                    "GitHub Sponsors user repository fetch failed for user: %s",
                    user,
                    exc_info=True,
                )
                continue
            for repo in repos:
                yield repo

        for topic in self.topics:
            try:
                repos = await self._search_topic_repositories(client, topic)
            except (SourceRateLimitError, SourceAuthError):
                raise
            except (
                SourceTransientError,
                SourceParseError,
                httpx.RequestError,
                httpx.TimeoutException,
            ):
                logger.warning(
                    "GitHub Sponsors topic search failed for topic: %s",
                    topic,
                    exc_info=True,
                )
                continue
            for repo in repos:
                yield repo

    @with_retry(max_retries=3, base_delay=1.0, adapter_name="github_sponsors")
    async def _fetch_repository(
        self,
        client: httpx.AsyncClient,
        repository: str,
    ) -> dict | None:
        repo = repository.strip()
        if "/" not in repo:
            return None
        try:
            resp = await client.get(f"{GITHUB_API}/repos/{repo}")
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            _raise_http_error(e, f"repository: {repo}", self.name)
        except (ValueError, KeyError, TypeError) as e:
            raise SourceParseError(
                f"Failed to parse repository response for: {repo}",
                adapter_name=self.name,
            ) from e

        if not isinstance(data, dict):
            raise SourceParseError(
                f"Unexpected repository response for: {repo}",
                adapter_name=self.name,
            )
        return data

    @with_retry(max_retries=3, base_delay=1.0, adapter_name="github_sponsors")
    async def _fetch_owner_repositories(
        self,
        client: httpx.AsyncClient,
        owner: str,
        *,
        owner_type: str,
    ) -> list[dict]:
        owner = owner.strip()
        if not owner:
            return []
        path = "orgs" if owner_type == "org" else "users"
        try:
            resp = await client.get(
                f"{GITHUB_API}/{path}/{quote(owner)}/repos",
                params={
                    "per_page": self.max_repositories_per_query,
                    "sort": "updated",
                    "direction": "desc",
                    "type": "public",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return []
            _raise_http_error(e, f"{owner_type} repositories: {owner}", self.name)
        except (ValueError, KeyError, TypeError) as e:
            raise SourceParseError(
                f"Failed to parse repositories response for: {owner}",
                adapter_name=self.name,
            ) from e

        if not isinstance(data, list):
            raise SourceParseError(
                f"Unexpected repositories response for: {owner}",
                adapter_name=self.name,
            )
        return [repo for repo in data if isinstance(repo, dict)]

    @with_retry(max_retries=3, base_delay=1.0, adapter_name="github_sponsors")
    async def _search_topic_repositories(
        self,
        client: httpx.AsyncClient,
        topic: str,
    ) -> list[dict]:
        topic = topic.strip()
        if not topic:
            return []
        try:
            resp = await client.get(
                f"{GITHUB_API}/search/repositories",
                params={
                    "q": f"topic:{topic}",
                    "sort": "stars",
                    "order": "desc",
                    "per_page": self.max_repositories_per_query,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            _raise_http_error(e, f"topic search: {topic}", self.name)
        except (ValueError, KeyError, TypeError) as e:
            raise SourceParseError(
                f"Failed to parse topic search response for: {topic}",
                adapter_name=self.name,
            ) from e

        if not isinstance(data, dict):
            raise SourceParseError(
                f"Unexpected topic search response for: {topic}",
                adapter_name=self.name,
            )
        items = data.get("items") or []
        return [repo for repo in items if isinstance(repo, dict)] if isinstance(items, list) else []

    @with_retry(max_retries=3, base_delay=1.0, adapter_name="github_sponsors")
    async def _fetch_profile(self, client: httpx.AsyncClient, repo: str) -> dict:
        try:
            resp = await client.get(f"{GITHUB_API}/repos/{repo}/community/profile")
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {}
            _raise_http_error(e, f"funding profile: {repo}", self.name)
        except (ValueError, KeyError, TypeError) as e:
            raise SourceParseError(
                f"Failed to parse funding profile response for: {repo}",
                adapter_name=self.name,
            ) from e

        if not isinstance(data, dict):
            raise SourceParseError(
                f"Unexpected funding profile response for: {repo}",
                adapter_name=self.name,
            )
        return data


def _sponsor_funding(profile: dict, *, default_owner: str | None = None) -> list[SponsorFunding]:
    links = profile.get("funding_links") or []
    if not isinstance(links, list):
        return []

    funding: list[SponsorFunding] = []
    for item in links:
        if not isinstance(item, dict):
            continue
        platform = str(item.get("platform") or "").strip()
        url = str(item.get("url") or "").strip()
        if not platform or not url:
            continue

        maintainer = _sponsor_maintainer(url) or default_owner
        sponsor_enabled = _is_github_sponsors(platform, url)
        funding.append(
            SponsorFunding(
                platform=platform,
                url=url,
                maintainer=maintainer,
                sponsor_enabled=sponsor_enabled,
            )
        )

    return funding


def _to_signal(
    repo: dict,
    funding: SponsorFunding,
    *,
    adapter_name: str,
    evidence_url: str,
) -> Signal:
    full_name = _repo_full_name(repo)
    owner = _repo_owner(repo)
    stars = _int_value(repo.get("stargazers_count"))
    language = _string_or_none(repo.get("language"))
    description = str(repo.get("description") or "").strip()

    return Signal(
        source_type=SignalSourceType.FUNDING,
        source_adapter=adapter_name,
        title=f"{full_name} exposes funding via {funding.platform}",
        content=_content(full_name, funding, description),
        url=funding.url,
        author=funding.maintainer or owner,
        published_at=_parse_dt(repo.get("created_at")),
        tags=_build_tags(repo, funding),
        credibility=_credibility(stars, funding.sponsor_enabled),
        metadata={
            "repo": full_name,
            "repository": full_name,
            "repository_url": repo.get("html_url") or f"https://github.com/{full_name}",
            "owner": owner,
            "maintainer": funding.maintainer,
            "sponsor_enabled": funding.sponsor_enabled,
            "funding_platform": funding.platform,
            "funding_url": funding.url,
            "evidence_url": evidence_url,
            "stars": stars,
            "forks": _int_value(repo.get("forks_count")),
            "language": language,
            "topics": _topics(repo),
            "open_issues": _int_value(repo.get("open_issues_count")),
            "updated_at": repo.get("updated_at"),
            "signal_role": "market",
            "role_hint": "market",
        },
    )


def _content(full_name: str, funding: SponsorFunding, description: str) -> str:
    parts = [f"{full_name} publishes funding metadata for {funding.platform}."]
    if funding.sponsor_enabled and funding.maintainer:
        parts.append(f"{funding.maintainer} is reachable through GitHub Sponsors.")
    if description:
        parts.append(description[:500])
    parts.append(
        "Maintainer sponsorship signals active ecosystem demand, sustainability pressure, "
        "and potential commercial intent around repository maintenance."
    )
    return " ".join(parts)


def _build_tags(repo: dict, funding: SponsorFunding) -> list[str]:
    tags: set[str] = {"github", "funding", "sponsorship", "repository"}
    if funding.sponsor_enabled:
        tags.add("github-sponsors")
    platform = _slug(funding.platform)
    if platform:
        tags.add(platform)
    language = _string_or_none(repo.get("language"))
    if language:
        tags.add(_slug(language))
    for topic in _topics(repo):
        slug = _slug(topic)
        if slug:
            tags.add(slug)
    return sorted(tags)[:10]


def _evidence_url(repo: str, profile: dict) -> str:
    files = profile.get("files")
    if isinstance(files, dict):
        funding = files.get("funding")
        if isinstance(funding, dict):
            html_url = funding.get("html_url")
            if isinstance(html_url, str) and html_url.strip():
                return html_url.strip()
    return f"https://github.com/{repo}/community"


def _repo_full_name(repo: dict) -> str:
    full_name = repo.get("full_name")
    if isinstance(full_name, str) and "/" in full_name:
        return full_name.strip()
    owner = _repo_owner(repo)
    name = repo.get("name")
    if owner and isinstance(name, str) and name.strip():
        return f"{owner}/{name.strip()}"
    return ""


def _repo_owner(repo: dict) -> str | None:
    owner = repo.get("owner")
    if isinstance(owner, dict):
        login = owner.get("login")
        if isinstance(login, str) and login.strip():
            return login.strip()
    full_name = repo.get("full_name")
    if isinstance(full_name, str) and "/" in full_name:
        return full_name.split("/", 1)[0].strip()
    return None


def _sponsor_maintainer(url: str) -> str | None:
    marker = "github.com/sponsors/"
    lower = url.lower()
    index = lower.find(marker)
    if index < 0:
        return None
    maintainer = url[index + len(marker):].strip("/").split("/", 1)[0]
    return maintainer or None


def _is_github_sponsors(platform: str, url: str) -> bool:
    return platform.strip().lower() == "github sponsors" or "github.com/sponsors/" in url.lower()


def _credibility(stars: int, sponsor_enabled: bool) -> float:
    base = 0.45 if sponsor_enabled else 0.35
    return min(base + (stars / 10000), 1.0)


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _topics(repo: dict) -> list[str]:
    topics = repo.get("topics") or []
    if not isinstance(topics, list):
        return []
    return [topic.strip() for topic in topics if isinstance(topic, str) and topic.strip()][:10]


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        items.append(normalized)
    return items


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _positive_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    return result if result > 0 else default


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _slug(value: str) -> str:
    return value.strip().lower().replace(" ", "-")


def _raise_http_error(error: httpx.HTTPStatusError, context: str, adapter_name: str) -> None:
    status = error.response.status_code
    if status == 429 or _is_github_rate_limit(error.response):
        retry_after = error.response.headers.get("Retry-After")
        retry_seconds = float(retry_after) if retry_after else None
        raise SourceRateLimitError(
            f"Rate limit exceeded for {context}",
            adapter_name=adapter_name,
            retry_after=retry_seconds,
        ) from error
    if status in (401, 403):
        raise SourceAuthError(
            f"Authentication failed (HTTP {status}) for {context}",
            adapter_name=adapter_name,
        ) from error
    if 500 <= status < 600:
        raise SourceTransientError(
            f"Server error (HTTP {status}) for {context}",
            adapter_name=adapter_name,
        ) from error
    raise SourceTransientError(
        f"HTTP {status} for {context}",
        adapter_name=adapter_name,
    ) from error


def _is_github_rate_limit(response: httpx.Response) -> bool:
    remaining = response.headers.get("X-RateLimit-Remaining")
    message = ""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            message = str(payload.get("message", "")).lower()
    except ValueError:
        pass
    return response.status_code == 403 and (remaining == "0" or "rate limit" in message)
