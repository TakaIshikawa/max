"""SourceForge projects source adapter - open-source project metadata signals."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from max.sources.base import (
    AdapterCircuitOpenError,
    AdapterFetchError,
    SourceAdapter,
    fetch_with_retry,
)
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

SOURCEFORGE_BASE_URL = "https://sourceforge.net"
SOURCEFORGE_PROJECTS_API = f"{SOURCEFORGE_BASE_URL}/rest/p/"

_DEFAULT_QUERIES = ["ai", "developer-tools", "security", "database", "python"]


class SourceForgeProjectsAdapter(SourceAdapter):
    """Fetch SourceForge project metadata as open-source ecosystem signals."""

    @property
    def name(self) -> str:
        return "sourceforge_projects"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def queries(self) -> list[str]:
        return self._configured_terms("queries", _DEFAULT_QUERIES)

    @property
    def categories(self) -> list[str]:
        configured = self._config.get("categories", [])
        return _dedupe_strings(configured if isinstance(configured, (list, tuple, set)) else [])

    @property
    def projects(self) -> list[str]:
        configured = self._config.get("projects", self._config.get("project_names", []))
        return _dedupe_strings(configured if isinstance(configured, (list, tuple, set)) else [])

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0:
            return []

        signals: list[Signal] = []
        seen_projects: set[str] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            for query in self.queries:
                if len(signals) >= limit:
                    break

                data = await self._fetch_json(
                    client,
                    SOURCEFORGE_PROJECTS_API,
                    context=f"query '{query}'",
                    params={
                        "q": query,
                        "limit": min(100, max(1, limit - len(signals))),
                        "offset": 0,
                    },
                )
                if data is None:
                    continue

                self._append_project_signals(
                    signals,
                    _extract_projects(data),
                    limit=limit,
                    seen_projects=seen_projects,
                    search_query=query,
                )

            for category in self.categories:
                if len(signals) >= limit:
                    break

                data = await self._fetch_json(
                    client,
                    SOURCEFORGE_PROJECTS_API,
                    context=f"category '{category}'",
                    params={
                        "category": category,
                        "limit": min(100, max(1, limit - len(signals))),
                        "offset": 0,
                    },
                )
                if data is None:
                    continue

                self._append_project_signals(
                    signals,
                    _extract_projects(data),
                    limit=limit,
                    seen_projects=seen_projects,
                    category=category,
                )

            for project in self.projects:
                if len(signals) >= limit:
                    break

                data = await self._fetch_json(
                    client,
                    f"{SOURCEFORGE_PROJECTS_API}{quote(project.strip('/'), safe='')}/",
                    context=f"project '{project}'",
                    params={},
                )
                if data is None:
                    continue

                self._append_project_signals(
                    signals,
                    [_project_payload(data)] if isinstance(data, dict) else [],
                    limit=limit,
                    seen_projects=seen_projects,
                    project_name=project,
                )

        return signals[:limit]

    async def _fetch_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        context: str,
        params: dict[str, object],
    ) -> dict | list | None:
        try:
            response = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                params=params,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "max-sourceforge-projects-adapter/0.1",
                },
            )
            return response.json()
        except (AdapterCircuitOpenError, AdapterFetchError, httpx.RequestError) as e:
            logger.warning(
                "%s: failed to fetch SourceForge projects for %s: %s",
                self.name,
                context,
                e,
            )
        except ValueError as e:
            logger.warning(
                "%s: failed to parse JSON response for %s: %s",
                self.name,
                context,
                e,
            )
        return None

    def _append_project_signals(
        self,
        signals: list[Signal],
        projects: list[dict],
        *,
        limit: int,
        seen_projects: set[str],
        search_query: str | None = None,
        category: str | None = None,
        project_name: str | None = None,
    ) -> None:
        for project in projects:
            if len(signals) >= limit:
                break

            try:
                identity = _project_identity(project)
                if identity is None or identity in seen_projects:
                    continue

                signal = _project_to_signal(
                    project,
                    adapter_name=self.name,
                    search_query=search_query,
                    category=category,
                    project_name=project_name,
                )
                seen_projects.add(identity)
                signals.append(signal)
            except (TypeError, ValueError) as e:
                logger.warning("%s: failed to parse SourceForge project object: %s", self.name, e)


def _extract_projects(data: dict | list) -> list[dict]:
    if isinstance(data, list):
        projects: list[dict] = []
        for item in data:
            payload = _project_payload(item)
            if isinstance(payload, dict):
                projects.append(payload)
        return projects
    if not isinstance(data, dict):
        return []

    for key in ("projects", "results", "items", "hits"):
        value = data.get(key)
        if isinstance(value, list):
            projects: list[dict] = []
            for item in value:
                payload = _project_payload(item)
                if isinstance(payload, dict):
                    projects.append(payload)
            return projects
    return []


def _project_payload(value: object) -> object:
    if not isinstance(value, dict):
        return value
    for key in ("project", "project_summary", "node"):
        nested = value.get(key)
        if isinstance(nested, dict):
            return nested
    return value


def _project_identity(project: dict) -> str | None:
    external_id = _external_id(project)
    return external_id.lower() if external_id else None


def _project_to_signal(
    project: dict,
    *,
    adapter_name: str,
    search_query: str | None,
    category: str | None,
    project_name: str | None,
) -> Signal:
    external_id = _external_id(project)
    if external_id is None:
        raise ValueError("project missing id, shortname, or name")

    name = _string_or_none(project.get("name") or project.get("title") or project.get("full_name"))
    shortname = _string_or_none(
        project.get("shortname")
        or project.get("short_name")
        or project.get("unixname")
        or project.get("unix_name")
        or project.get("slug")
    )
    title = name or shortname or external_id
    summary = (
        _string_or_none(project.get("summary"))
        or _string_or_none(project.get("description"))
        or _string_or_none(project.get("short_description"))
        or title
    )
    source_url = _source_url(project, external_id=shortname or external_id)
    categories = _string_list(project.get("categories") or project.get("category"))
    tags = _string_list(project.get("tags") or project.get("labels"))
    license_value = _license(project.get("license") or project.get("licenses"))
    created_at = _parse_datetime(
        project.get("created_at")
        or project.get("created")
        or project.get("creation_date")
        or project.get("registered")
    )
    updated_at = _parse_datetime(
        project.get("updated_at")
        or project.get("updated")
        or project.get("last_updated")
        or project.get("modified")
    )
    downloads = _int_or_none(
        project.get("downloads")
        or project.get("download_count")
        or project.get("downloads_total")
        or project.get("total_downloads")
    )
    weekly_downloads = _int_or_none(
        project.get("weekly_downloads") or project.get("downloads_week")
    )
    monthly_downloads = _int_or_none(
        project.get("monthly_downloads") or project.get("downloads_month")
    )
    rating = _float_or_none(
        project.get("rating") or project.get("rating_average") or project.get("score")
    )
    developers = _int_or_none(project.get("developers") or project.get("developer_count"))
    repository = _repository_url(
        project.get("repository") or project.get("repository_url") or project.get("repo")
    )
    homepage = _string_or_none(
        project.get("homepage") or project.get("homepage_url") or project.get("website")
    )

    metadata = {
        "sourceforge_id": external_id,
        "shortname": shortname,
        "name": name,
        "summary": summary,
        "categories": categories,
        "tags": tags,
        "license": license_value,
        "downloads": downloads,
        "weekly_downloads": weekly_downloads,
        "monthly_downloads": monthly_downloads,
        "rating": rating,
        "developers": developers,
        "repository": repository,
        "homepage": homepage,
        "created_at": created_at.isoformat() if created_at is not None else None,
        "updated_at": updated_at.isoformat() if updated_at is not None else None,
        "source_url": source_url,
        "search_query": search_query,
        "category": category,
        "project_name": project_name,
        "signal_role": "market",
    }

    return Signal(
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=title,
        content=summary[:500],
        url=source_url,
        author=_author(project),
        published_at=created_at or updated_at,
        tags=_build_tags(
            categories=categories,
            tags=tags,
            search_query=search_query,
            category=category,
        ),
        credibility=_credibility(
            downloads=downloads,
            weekly_downloads=weekly_downloads,
            rating=rating,
        ),
        metadata=metadata,
    )


def _external_id(project: dict) -> str | None:
    for key in ("id", "shortname", "short_name", "unixname", "unix_name", "slug", "name"):
        value = _string_or_none(project.get(key))
        if value:
            return value
    return None


def _source_url(project: dict, *, external_id: str) -> str:
    for key in ("url", "web_url", "external_url", "html_url"):
        value = _string_or_none(project.get(key))
        if value:
            return value
    return f"{SOURCEFORGE_BASE_URL}/projects/{quote(external_id.strip('/'), safe='')}/"


def _repository_url(value: object) -> str | None:
    if isinstance(value, str):
        return _string_or_none(value)
    if isinstance(value, dict):
        return _string_or_none(value.get("url") or value.get("git_url") or value.get("hg_url"))
    return None


def _license(value: object) -> str | None:
    if isinstance(value, str):
        return _string_or_none(value)
    if isinstance(value, list):
        values = _string_list(value)
        return values[0] if values else None
    if isinstance(value, dict):
        return _string_or_none(value.get("name") or value.get("shortname") or value.get("id"))
    return None


def _author(project: dict) -> str | None:
    value = project.get("maintainers") or project.get("developers") or project.get("authors")
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, str):
            return _string_or_none(first)
        if isinstance(first, dict):
            return _string_or_none(first.get("username") or first.get("name"))
    return _string_or_none(project.get("owner") or project.get("maintainer"))


def _build_tags(
    *,
    categories: list[str],
    tags: list[str],
    search_query: str | None,
    category: str | None,
) -> list[str]:
    values = [*categories, *tags]
    if search_query:
        values.append(search_query)
    if category:
        values.append(category)

    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _tag(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped[:10]


def _credibility(
    *,
    downloads: int | None,
    weekly_downloads: int | None,
    rating: float | None,
) -> float:
    total = max(downloads or 0, weekly_downloads or 0)
    download_score = min(math.log10(total + 1) / 7, 0.75)
    rating_score = 0.0
    if rating is not None:
        scale = 5.0 if rating <= 5 else 100.0
        rating_score = min(max(rating, 0.0) / scale, 1.0) * 0.15
    return min(round(0.1 + download_score + rating_score, 3), 1.0)


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        return []

    deduped: list[str] = []
    seen: set[str] = set()
    for item in values:
        if isinstance(item, dict):
            item = item.get("shortname") or item.get("name") or item.get("label")
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _dedupe_strings(values: object) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        normalized = value.strip().strip("/")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _tag(value: str) -> str:
    return "-".join(value.strip().lower().replace("_", "-").split())


def _int_or_none(value: object) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
