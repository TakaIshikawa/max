"""Docker Hub image trend source adapter."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.sources.dockerhub import (
    _dockerhub_url,
    _int_or_none,
    _parse_datetime,
    _parse_repository_ref,
    _string_or_none,
)
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

DOCKERHUB_API = "https://hub.docker.com/v2"
_DEFAULT_REPOSITORIES = ["library/nginx", "library/postgres", "library/redis"]


class DockerHubImageTrendsAdapter(SourceAdapter):
    """Fetch Docker Hub repository popularity and maintenance trend metadata."""

    @property
    def name(self) -> str:
        return "dockerhub_image_trends"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def repositories(self) -> list[str]:
        configured = (
            self._config.get("repositories")
            or self._config.get("repository_names")
            or self._config.get("images")
        )
        return _repository_list(configured, _DEFAULT_REPOSITORIES)

    @property
    def api_url(self) -> str:
        value = self._config.get("api_url")
        if isinstance(value, str) and value.strip():
            return value.strip().rstrip("/")
        return DOCKERHUB_API

    @property
    def timeout(self) -> float:
        value = self._config.get("timeout", 30)
        try:
            timeout = float(value)
        except (TypeError, ValueError):
            return 30.0
        return timeout if timeout > 0 else 30.0

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        item_limit = max(limit, 0)
        if item_limit == 0:
            return []

        signals: list[Signal] = []
        seen_ids: set[str] = set()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for repository_ref in self.repositories:
                if len(signals) >= item_limit:
                    break

                repo_id = _parse_repository_ref(repository_ref)
                if repo_id is None:
                    logger.warning("%s: invalid repository reference: %s", self.name, repository_ref)
                    continue

                payload = await self._fetch_repository(client, repo_id)
                if payload is None:
                    continue

                signal = parse_repository_signal(payload, repo_id=repo_id, adapter_name=self.name)
                if signal.id in seen_ids:
                    continue
                seen_ids.add(signal.id)
                signals.append(signal)

        return signals[:item_limit]

    async def _fetch_repository(
        self,
        client: httpx.AsyncClient,
        repo_id: tuple[str, str],
    ) -> dict | None:
        namespace, repository = repo_id
        url = (
            f"{self.api_url}/namespaces/{quote(namespace, safe='')}"
            f"/repositories/{quote(repository, safe='')}"
        )
        try:
            response = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                max_retries=2,
                backoff_base=0,
                headers={"User-Agent": "max-dockerhub-image-trends-adapter/0.1"},
            )
            payload = response.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch Docker Hub repository %s/%s: %s", self.name, namespace, repository, e)
            return None
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning("%s: request failed for Docker Hub repository %s/%s: %s", self.name, namespace, repository, e)
            return None
        except ValueError as e:
            logger.warning("%s: failed to parse Docker Hub repository %s/%s JSON: %s", self.name, namespace, repository, e)
            return None

        if not isinstance(payload, dict):
            logger.warning("%s: malformed Docker Hub repository response for %s/%s", self.name, namespace, repository)
            return None
        return payload


def parse_repository_signal(
    repository_data: dict,
    *,
    repo_id: tuple[str, str],
    adapter_name: str = "dockerhub_image_trends",
) -> Signal:
    """Normalize a Docker Hub repository detail response into a Signal."""

    namespace, repository = repo_id
    repository_name = _repository_name(repository_data, repo_id)
    description = (
        _string_or_none(repository_data.get("description"))
        or _string_or_none(repository_data.get("short_description"))
        or ""
    )
    pull_count = _int_or_none(repository_data.get("pull_count")) or 0
    star_count = _int_or_none(repository_data.get("star_count")) or 0
    last_updated = _parse_datetime(
        repository_data.get("last_updated")
        or repository_data.get("updated_at")
        or repository_data.get("last_pushed")
    )
    url = _dockerhub_url(namespace, repository)

    metadata = {
        "signal_role": "market",
        "repository_name": repository_name,
        "namespace": namespace,
        "name": repository,
        "pull_count": pull_count,
        "star_count": star_count,
        "last_updated": last_updated.isoformat() if last_updated else None,
        "description": description,
        "is_official": bool(repository_data.get("is_official") or namespace == "library"),
        "is_automated": repository_data.get("is_automated"),
        "repository_type": repository_data.get("repository_type"),
        "source_url": url,
    }

    return Signal(
        id=f"{adapter_name}:{repository_name}",
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=f"{repository_name} Docker Hub image trend",
        content=_content(repository_name, pull_count, star_count, last_updated, description),
        url=url,
        published_at=last_updated,
        tags=_tags(repository_name, repository_data),
        credibility=_credibility(pull_count=pull_count, star_count=star_count, last_updated=last_updated),
        metadata=metadata,
    )


def _repository_list(value: object, default: list[str]) -> list[str]:
    raw_values = default if value is None else value
    if isinstance(raw_values, str):
        candidates: list[object] = [raw_values]
    elif isinstance(raw_values, list | tuple | set):
        candidates = list(raw_values)
    else:
        candidates = []

    repositories: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        repository = _repository_string(candidate)
        if repository is None:
            continue
        repo_id = _parse_repository_ref(repository)
        if repo_id is None:
            continue
        normalized = f"{repo_id[0]}/{repo_id[1]}"
        if normalized in seen:
            continue
        seen.add(normalized)
        repositories.append(normalized)
    return repositories


def _repository_string(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        for key in ("repository", "repository_name", "image", "name"):
            text = _string_or_none(value.get(key))
            if text:
                return text
    return None


def _repository_name(repository_data: dict, repo_id: tuple[str, str]) -> str:
    repo_name = _string_or_none(repository_data.get("repo_name"))
    if repo_name and "/" in repo_name:
        return repo_name
    namespace = _string_or_none(repository_data.get("namespace")) or repo_id[0]
    name = _string_or_none(repository_data.get("name")) or repo_id[1]
    return f"{namespace}/{name}"


def _content(
    repository_name: str,
    pull_count: int,
    star_count: int,
    last_updated: datetime | None,
    description: str,
) -> str:
    updated = f" Last updated {last_updated.date().isoformat()}." if last_updated else ""
    summary = (
        f"{repository_name} has {pull_count:,} pulls and {star_count:,} stars on Docker Hub."
        f"{updated}"
    )
    if description:
        return f"{summary} {description}"[:500]
    return summary


def _tags(repository_name: str, repository_data: dict) -> list[str]:
    tags = ["dockerhub", "container-image", repository_name.split("/", 1)[0]]
    if repository_data.get("is_official") or repository_name.startswith("library/"):
        tags.append("official-image")
    repository_type = _string_or_none(repository_data.get("repository_type"))
    if repository_type:
        tags.append(repository_type)
    return _dedupe(tags)


def _credibility(
    *,
    pull_count: int,
    star_count: int,
    last_updated: datetime | None,
) -> float:
    pull_score = min(math.log10(pull_count + 1) / 10, 0.55)
    star_score = min(math.log10(star_count + 1) / 5, 0.3)
    freshness_score = 0.0
    if last_updated is not None:
        age_days = (datetime.now(timezone.utc) - last_updated).days
        if age_days <= 30:
            freshness_score = 0.15
        elif age_days <= 180:
            freshness_score = 0.1
        elif age_days <= 365:
            freshness_score = 0.05
    return min(round(0.1 + pull_score + star_score + freshness_score, 3), 1.0)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped
