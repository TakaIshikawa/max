"""Docker Hub source adapter — container image popularity and update signals."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

DOCKERHUB_SEARCH = "https://hub.docker.com/v2/search/repositories/"
DOCKERHUB_REPOSITORY = "https://hub.docker.com/v2/namespaces/{namespace}/repositories/{repository}"
DOCKERHUB_TAGS = "https://hub.docker.com/v2/namespaces/{namespace}/repositories/{repository}/tags"

_DEFAULT_QUERIES = ["ai", "llm", "agent", "database", "devtools"]
_DEFAULT_REPOSITORIES = ["library/nginx", "library/postgres", "library/redis"]


class DockerHubAdapter(SourceAdapter):
    """Fetch container image popularity and freshness signals from Docker Hub."""

    @property
    def name(self) -> str:
        return "dockerhub"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def queries(self) -> list[str]:
        return self._configured_terms("queries", _DEFAULT_QUERIES)

    @property
    def repositories(self) -> list[str]:
        return self._configured_terms("repositories", _DEFAULT_REPOSITORIES)

    @property
    def include_tags(self) -> bool:
        return bool(self._config.get("include_tags", True))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_repositories: set[str] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            for repository_ref in self.repositories:
                if len(signals) >= limit:
                    break

                repo_id = _parse_repository_ref(repository_ref)
                if repo_id is None:
                    logger.warning("%s: invalid repository reference: %s", self.name, repository_ref)
                    continue

                await self._append_repository_signal(
                    client,
                    signals,
                    repo_id,
                    limit=limit,
                    seen_repositories=seen_repositories,
                )

            for query in self.queries:
                if len(signals) >= limit:
                    break

                data = await self._fetch_json(
                    client,
                    DOCKERHUB_SEARCH,
                    context=f"query '{query}'",
                    params={"query": query, "page_size": min(10, limit - len(signals))},
                )
                if data is None:
                    continue

                for result in data.get("results", []):
                    if len(signals) >= limit:
                        break

                    repo_id = _repository_id_from_search_result(result)
                    if repo_id is None:
                        continue

                    # Search responses carry popularity; detail responses carry freshness
                    # and category fields. Merge when available, but keep the search hit if
                    # detail fetch is unavailable for a public repository.
                    detail = await self._fetch_repository(client, repo_id)
                    repo_data = {**result, **(detail or {})}
                    await self._append_repository_signal(
                        client,
                        signals,
                        repo_id,
                        limit=limit,
                        seen_repositories=seen_repositories,
                        search_query=query,
                        repository_data=repo_data,
                    )

        return signals[:limit]

    async def _append_repository_signal(
        self,
        client: httpx.AsyncClient,
        signals: list[Signal],
        repo_id: tuple[str, str],
        *,
        limit: int,
        seen_repositories: set[str],
        search_query: str | None = None,
        repository_data: dict | None = None,
    ) -> None:
        namespace, repository = repo_id
        full_name = f"{namespace}/{repository}"
        if full_name in seen_repositories or len(signals) >= limit:
            return

        repo_data = repository_data
        if repo_data is None:
            repo_data = await self._fetch_repository(client, repo_id)
        if repo_data is None:
            return

        tag_names: list[str] = []
        tag_last_updated: datetime | None = None
        if self.include_tags:
            tag_names, tag_last_updated = await self._fetch_tags(client, repo_id)

        seen_repositories.add(full_name)
        try:
            signals.append(
                _repository_to_signal(
                    repo_data,
                    adapter_name=self.name,
                    repo_id=repo_id,
                    search_query=search_query,
                    tag_names=tag_names,
                    tag_last_updated=tag_last_updated,
                )
            )
        except (TypeError, ValueError) as e:
            logger.warning("%s: failed to parse repository object for %s: %s", self.name, full_name, e)

    async def _fetch_repository(
        self,
        client: httpx.AsyncClient,
        repo_id: tuple[str, str],
    ) -> dict | None:
        namespace, repository = repo_id
        return await self._fetch_json(
            client,
            DOCKERHUB_REPOSITORY.format(
                namespace=quote(namespace, safe=""),
                repository=quote(repository, safe=""),
            ),
            context=f"repository '{namespace}/{repository}'",
            params={},
        )

    async def _fetch_tags(
        self,
        client: httpx.AsyncClient,
        repo_id: tuple[str, str],
    ) -> tuple[list[str], datetime | None]:
        namespace, repository = repo_id
        data = await self._fetch_json(
            client,
            DOCKERHUB_TAGS.format(
                namespace=quote(namespace, safe=""),
                repository=quote(repository, safe=""),
            ),
            context=f"tags for '{namespace}/{repository}'",
            params={"page_size": 10},
        )
        if data is None:
            return [], None

        tag_names: list[str] = []
        newest: datetime | None = None
        for tag in data.get("results", []):
            name = _string_or_none(tag.get("name"))
            if name:
                tag_names.append(name)

            updated = _parse_datetime(tag.get("last_updated") or tag.get("tag_last_pushed"))
            if updated is not None and (newest is None or updated > newest):
                newest = updated

        return _dedupe(tag_names)[:10], newest

    async def _fetch_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        context: str,
        params: dict[str, object],
    ) -> dict | None:
        try:
            resp = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                params=params,
                headers={"User-Agent": "max-dockerhub-adapter/0.1"},
            )
            return resp.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch Docker Hub data for %s: %s", self.name, context, e)
        except ValueError as e:
            logger.warning("%s: failed to parse JSON response for %s: %s", self.name, context, e)
        return None


def _repository_to_signal(
    repository_data: dict,
    *,
    adapter_name: str,
    repo_id: tuple[str, str],
    search_query: str | None = None,
    tag_names: list[str] | None = None,
    tag_last_updated: datetime | None = None,
) -> Signal:
    namespace, repository = repo_id
    full_name = _repository_full_name(repository_data, repo_id)
    description = (
        _string_or_none(repository_data.get("description"))
        or _string_or_none(repository_data.get("short_description"))
        or full_name
    )
    star_count = _int_or_none(repository_data.get("star_count")) or 0
    pull_count = _int_or_none(repository_data.get("pull_count")) or 0
    last_updated = _parse_datetime(
        repository_data.get("last_updated")
        or repository_data.get("updated_at")
        or repository_data.get("last_pushed")
    )
    if last_updated is None:
        last_updated = tag_last_updated

    categories = _extract_categories(repository_data)
    tags = _build_tags(
        categories=categories,
        tag_names=tag_names or [],
        search_query=search_query,
    )

    metadata = {
        "repository_name": full_name,
        "namespace": namespace,
        "name": repository,
        "description": description,
        "star_count": star_count,
        "pull_count": pull_count,
        "last_updated": last_updated.isoformat() if last_updated else None,
        "categories": categories,
        "tags": tag_names or [],
        "search_query": search_query,
        "is_official": bool(repository_data.get("is_official") or namespace == "library"),
        "is_automated": repository_data.get("is_automated"),
        "repository_type": repository_data.get("repository_type"),
    }

    return Signal(
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=full_name,
        content=description[:500],
        url=_dockerhub_url(namespace, repository),
        published_at=last_updated,
        tags=tags,
        credibility=_credibility(
            pull_count=pull_count,
            star_count=star_count,
            last_updated=last_updated,
        ),
        metadata=metadata,
    )


def _parse_repository_ref(value: str) -> tuple[str, str] | None:
    ref = value.strip()
    if not ref:
        return None
    if ref.startswith("_/"):
        return ("library", ref[2:].strip())
    if "/" not in ref:
        return ("library", ref)

    namespace, repository = ref.split("/", 1)
    namespace = namespace.strip()
    repository = repository.strip()
    if not namespace or not repository or "/" in repository:
        return None
    return namespace, repository


def _repository_id_from_search_result(result: dict) -> tuple[str, str] | None:
    repo_name = _string_or_none(result.get("repo_name") or result.get("name"))
    namespace = _string_or_none(result.get("namespace") or result.get("repo_owner"))

    if repo_name and "/" in repo_name:
        return _parse_repository_ref(repo_name)

    if repo_name:
        if result.get("is_official") and not namespace:
            namespace = "library"
        return (namespace or "library", repo_name)

    return None


def _repository_full_name(repository_data: dict, repo_id: tuple[str, str]) -> str:
    namespace, repository = repo_id
    repo_name = _string_or_none(repository_data.get("repo_name"))
    if repo_name and "/" in repo_name:
        return repo_name
    return f"{namespace}/{repository}"


def _dockerhub_url(namespace: str, repository: str) -> str:
    if namespace == "library":
        return f"https://hub.docker.com/_/{repository}"
    return f"https://hub.docker.com/r/{namespace}/{repository}"


def _extract_categories(repository_data: dict) -> list[str]:
    raw_categories = repository_data.get("categories") or repository_data.get("category") or []
    if isinstance(raw_categories, str):
        raw_values: list[object] = [raw_categories]
    elif isinstance(raw_categories, list):
        raw_values = raw_categories
    else:
        raw_values = []

    categories: list[str] = []
    for value in raw_values:
        if isinstance(value, str):
            categories.append(value)
        elif isinstance(value, dict):
            category = (
                _string_or_none(value.get("name"))
                or _string_or_none(value.get("slug"))
                or _string_or_none(value.get("label"))
            )
            if category:
                categories.append(category)

    return _dedupe([category.strip() for category in categories if category.strip()])[:10]


def _build_tags(
    *,
    categories: list[str],
    tag_names: list[str],
    search_query: str | None = None,
) -> list[str]:
    tags = [*categories, *tag_names]
    if search_query:
        tags.append(search_query)
    return _dedupe(tags)[:10]


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


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _int_or_none(value: object) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


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
