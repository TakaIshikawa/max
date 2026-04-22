"""MCP Registry source adapter — server discovery and trust signals."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://registry.modelcontextprotocol.io"
DEFAULT_ENDPOINT = "/v0.1/servers"
_DEFAULT_QUERIES: list[str] = []
_DEFAULT_CATEGORIES: list[str] = []


class McpRegistryAdapter(SourceAdapter):
    """Fetch MCP server discovery, package, capability, and trust signals."""

    @property
    def name(self) -> str:
        return "mcp_registry"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def base_url(self) -> str:
        configured = self._config.get("base_url")
        if isinstance(configured, str) and configured.strip():
            return configured.strip().rstrip("/")
        return DEFAULT_BASE_URL

    @property
    def endpoint(self) -> str:
        configured = self._config.get("endpoint")
        if isinstance(configured, str) and configured.strip():
            return configured.strip()
        return DEFAULT_ENDPOINT

    @property
    def queries(self) -> list[str]:
        return self._configured_terms("queries", _DEFAULT_QUERIES)

    @property
    def categories(self) -> list[str]:
        return self._configured_terms("categories", _DEFAULT_CATEGORIES)

    @property
    def min_stars(self) -> int:
        return _int_or_none(self._config.get("min_stars")) or 0

    @property
    def min_score(self) -> float:
        return _normalize_score(self._config.get("min_score")) or 0.0

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_servers: set[str] = set()
        requests = self._request_filters()

        async with httpx.AsyncClient(timeout=30) as client:
            for search_query, category in requests:
                if len(signals) >= limit:
                    break

                cursor: str | None = None
                while len(signals) < limit:
                    data = await self._fetch_json(
                        client,
                        context=_request_context(search_query=search_query, category=category),
                        params=self._request_params(
                            limit=min(100, max(1, limit - len(signals))),
                            search_query=search_query,
                            category=category,
                            cursor=cursor,
                        ),
                    )
                    if data is None:
                        break

                    entries = _extract_entries(data)
                    if not entries:
                        break

                    self._append_server_signals(
                        signals,
                        entries,
                        limit=limit,
                        seen_servers=seen_servers,
                        search_query=search_query,
                        category=category,
                    )

                    cursor = _next_cursor(data)
                    if not cursor:
                        break

        return signals[:limit]

    def _request_filters(self) -> list[tuple[str | None, str | None]]:
        filters: list[tuple[str | None, str | None]] = []
        filters.extend((query, None) for query in self.queries)
        filters.extend((None, category) for category in self.categories)
        return filters or [(None, None)]

    def _request_params(
        self,
        *,
        limit: int,
        search_query: str | None,
        category: str | None,
        cursor: str | None,
    ) -> dict[str, object]:
        params: dict[str, object] = {"limit": limit}
        if search_query:
            params["search"] = search_query
        if category:
            params["category"] = category
        if cursor:
            params["cursor"] = cursor
        return params

    async def _fetch_json(
        self,
        client: httpx.AsyncClient,
        *,
        context: str,
        params: dict[str, object],
    ) -> dict | list | None:
        try:
            resp = await fetch_with_retry(
                self._list_url(),
                client,
                adapter_name=self.name,
                params=params,
                headers={"User-Agent": "max-mcp-registry-adapter/0.1"},
            )
            return resp.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch MCP registry data for %s: %s", self.name, context, e)
        except ValueError as e:
            logger.warning("%s: failed to parse JSON response for %s: %s", self.name, context, e)
        return None

    def _list_url(self) -> str:
        endpoint = self.endpoint
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            return endpoint
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"
        return f"{self.base_url}{endpoint}"

    def _append_server_signals(
        self,
        signals: list[Signal],
        entries: list[dict],
        *,
        limit: int,
        seen_servers: set[str],
        search_query: str | None,
        category: str | None,
    ) -> None:
        for entry in entries:
            if len(signals) >= limit:
                break

            try:
                server = _server_payload(entry)
                server_name = _server_name(server)
                if server_name is None:
                    continue

                version = _string_or_none(server.get("version"))
                dedupe_key = f"{server_name}@{version or 'latest'}"
                if dedupe_key in seen_servers:
                    continue

                if not self._passes_filters(entry, server):
                    continue

                signal = _server_to_signal(
                    entry,
                    server,
                    adapter_name=self.name,
                    base_url=self.base_url,
                    search_query=search_query,
                    category=category,
                )
                seen_servers.add(dedupe_key)
                signals.append(signal)
            except (TypeError, ValueError) as e:
                logger.warning("%s: failed to parse MCP registry entry: %s", self.name, e)

    def _passes_filters(self, entry: dict, server: dict) -> bool:
        if self.min_stars > 0:
            stars = _metric(entry, server, _STAR_KEYS)
            if stars is not None and stars < self.min_stars:
                return False

        if self.min_score > 0:
            score = _score_metric(entry, server)
            if score is not None and score < self.min_score:
                return False

        return True


def _server_to_signal(
    entry: dict,
    server: dict,
    *,
    adapter_name: str,
    base_url: str,
    search_query: str | None,
    category: str | None,
) -> Signal:
    server_name = _server_name(server) or ""
    version = _string_or_none(server.get("version"))
    title = _string_or_none(server.get("title")) or server_name
    description = _string_or_none(server.get("description")) or title
    published_at = _parse_datetime(
        entry.get("updated_at")
        or entry.get("updatedAt")
        or entry.get("published_at")
        or entry.get("publishedAt")
        or server.get("updated_at")
        or server.get("updatedAt")
    )
    packages = _extract_packages(server)
    package_urls = _package_urls(packages)
    capabilities = _extract_capabilities(server)
    categories = _extract_categories(entry, server)
    tags = _build_tags(
        categories=categories,
        capabilities=capabilities,
        packages=packages,
        search_query=search_query,
        category=category,
    )
    registry_url = _registry_url(base_url, server_name, version)
    stars = _metric(entry, server, _STAR_KEYS)
    downloads = _metric(entry, server, _DOWNLOAD_KEYS)
    installs = _metric(entry, server, _INSTALL_KEYS)
    score = _score_metric(entry, server)
    verified = bool(_metric(entry, server, _VERIFIED_KEYS) or _namespace_verified(server_name))

    metadata = {
        "server_name": server_name,
        "version": version,
        "status": _string_or_none(entry.get("status") or server.get("status")),
        "registry_url": registry_url,
        "package_urls": package_urls,
        "packages": packages,
        "capabilities": capabilities,
        "categories": categories,
        "repository_url": _repository_url(server),
        "website_url": _website_url(server),
        "search_query": search_query,
        "category": category,
        "stars": stars,
        "downloads": downloads,
        "install_count": installs,
        "score": score,
        "verified": verified,
        "registry_metadata": entry.get("metadata") or entry.get("_meta") or server.get("_meta") or {},
    }

    return Signal(
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=f"{title}@{version}" if version else title,
        content=description[:500],
        url=registry_url,
        author=_author(server),
        published_at=published_at,
        tags=tags,
        credibility=_credibility(
            score=score,
            stars=stars,
            downloads=downloads,
            installs=installs,
            verified=verified,
            status=metadata["status"],
        ),
        metadata=metadata,
    )


def _extract_entries(data: dict | list) -> list[dict]:
    if isinstance(data, list):
        values = data
    elif isinstance(data, dict):
        values = (
            data.get("servers")
            or data.get("items")
            or data.get("results")
            or data.get("data")
            or []
        )
    else:
        values = []

    return [value for value in values if isinstance(value, dict)]


def _next_cursor(data: dict | list) -> str | None:
    if not isinstance(data, dict):
        return None

    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        cursor = _string_or_none(metadata.get("nextCursor") or metadata.get("next_cursor"))
        if cursor:
            return cursor

    return _string_or_none(data.get("nextCursor") or data.get("next_cursor"))


def _server_payload(entry: dict) -> dict:
    for key in ("server", "server_detail", "serverDetail", "package"):
        value = entry.get(key)
        if isinstance(value, dict):
            return value
    return entry


def _server_name(server: dict) -> str | None:
    return _string_or_none(server.get("name") or server.get("id") or server.get("serverName"))


def _extract_packages(server: dict) -> list[dict[str, Any]]:
    packages = server.get("packages") or server.get("package") or []
    if isinstance(packages, dict):
        raw_packages: list[object] = [packages]
    elif isinstance(packages, list):
        raw_packages = packages
    else:
        raw_packages = []

    parsed: list[dict[str, Any]] = []
    for package in raw_packages:
        if not isinstance(package, dict):
            continue
        package_type = _string_or_none(package.get("registryType") or package.get("registry_type"))
        identifier = _string_or_none(package.get("identifier") or package.get("name"))
        version = _string_or_none(package.get("version"))
        url = _string_or_none(package.get("url") or package.get("packageUrl") or package.get("package_url"))
        if not (package_type or identifier or url):
            continue
        parsed.append(
            {
                "registry_type": package_type,
                "identifier": identifier,
                "version": version,
                "url": url,
                "registry_base_url": _string_or_none(
                    package.get("registryBaseUrl") or package.get("registry_base_url")
                ),
                "transport": package.get("transport") if isinstance(package.get("transport"), dict) else None,
            }
        )
    return parsed


def _package_urls(packages: list[dict[str, Any]]) -> list[str]:
    urls: list[str] = []
    for package in packages:
        explicit = _string_or_none(package.get("url"))
        if explicit:
            urls.append(explicit)
            continue

        package_type = _string_or_none(package.get("registry_type"))
        identifier = _string_or_none(package.get("identifier"))
        if package_type is None or identifier is None:
            continue

        normalized_type = package_type.lower()
        if normalized_type == "npm":
            urls.append(f"https://www.npmjs.com/package/{quote(identifier, safe='@/')}")
        elif normalized_type == "pypi":
            urls.append(f"https://pypi.org/project/{quote(identifier, safe='')}/")
        elif normalized_type == "nuget":
            urls.append(f"https://www.nuget.org/packages/{quote(identifier, safe='')}/")
        elif normalized_type in {"oci", "docker"}:
            base_url = _string_or_none(package.get("registry_base_url")) or ""
            if "ghcr.io" in base_url:
                urls.append(f"https://github.com/{identifier}/pkgs/container/{identifier.rsplit('/', 1)[-1]}")
            else:
                urls.append(f"https://hub.docker.com/r/{identifier}")
    return _dedupe(urls)


def _extract_capabilities(server: dict) -> list[str]:
    capabilities = server.get("capabilities") or []
    if isinstance(capabilities, list):
        values = [value for value in capabilities if isinstance(value, str)]
    elif isinstance(capabilities, dict):
        values = [key for key, value in capabilities.items() if value is not False and value is not None]
    else:
        values = []
    return _dedupe(values)[:10]


def _extract_categories(entry: dict, server: dict) -> list[str]:
    raw_values: list[object] = []
    for payload in (server, entry):
        for key in ("categories", "category", "tags", "keywords"):
            value = payload.get(key)
            if isinstance(value, list):
                raw_values.extend(value)
            elif isinstance(value, str):
                raw_values.extend(part.strip() for part in value.replace(",", " ").split())

    categories: list[str] = []
    for value in raw_values:
        if isinstance(value, str):
            categories.append(value)
        elif isinstance(value, dict):
            label = _string_or_none(value.get("name") or value.get("slug") or value.get("label"))
            if label:
                categories.append(label)
    return _dedupe(categories)[:10]


def _build_tags(
    *,
    categories: list[str],
    capabilities: list[str],
    packages: list[dict[str, Any]],
    search_query: str | None,
    category: str | None,
) -> list[str]:
    tags = [*categories, *capabilities]
    for package in packages:
        package_type = _string_or_none(package.get("registry_type"))
        if package_type:
            tags.append(package_type)
    if search_query:
        tags.append(search_query)
    if category:
        tags.append(category)
    return _dedupe(tags)[:12]


def _registry_url(base_url: str, server_name: str, version: str | None) -> str:
    encoded_name = quote(server_name, safe="")
    encoded_version = quote(version or "latest", safe="")
    return f"{base_url.rstrip()}/v0.1/servers/{encoded_name}/versions/{encoded_version}"


def _repository_url(server: dict) -> str | None:
    repository = server.get("repository")
    if isinstance(repository, dict):
        return _string_or_none(repository.get("url"))
    return _string_or_none(
        repository
        or server.get("repositoryUrl")
        or server.get("repository_url")
        or server.get("sourceUrl")
        or server.get("source_url")
    )


def _website_url(server: dict) -> str | None:
    return _string_or_none(
        server.get("websiteUrl")
        or server.get("website_url")
        or server.get("homepage")
        or server.get("homepageUrl")
    )


def _author(server: dict) -> str | None:
    author = server.get("author") or server.get("publisher") or server.get("maintainer")
    if isinstance(author, dict):
        return _string_or_none(author.get("name") or author.get("username") or author.get("login"))
    return _string_or_none(author)


_STAR_KEYS = {"stars", "star_count", "starCount", "github_stars", "githubStars"}
_DOWNLOAD_KEYS = {"downloads", "download_count", "downloadCount", "package_downloads"}
_INSTALL_KEYS = {"installs", "install_count", "installCount", "installation_count", "usage_count"}
_SCORE_KEYS = {"score", "trust_score", "trustScore", "popularity_score", "rating", "user_rating"}
_VERIFIED_KEYS = {"verified", "is_verified", "trusted", "is_trusted"}


def _metric(entry: dict, server: dict, keys: set[str]) -> float | None:
    for payload in (server, entry, server.get("_meta"), entry.get("_meta"), entry.get("metadata")):
        value = _find_metric(payload, keys)
        if value is not None:
            return value
    return None


def _find_metric(value: object, keys: set[str]) -> float | None:
    if not isinstance(value, dict):
        return None

    for key, item in value.items():
        if key in keys:
            metric = _float_or_none(item)
            if metric is not None:
                return metric

    for item in value.values():
        if isinstance(item, dict):
            metric = _find_metric(item, keys)
            if metric is not None:
                return metric
    return None


def _score_metric(entry: dict, server: dict) -> float | None:
    score = _metric(entry, server, _SCORE_KEYS)
    return _normalize_score(score)


def _normalize_score(value: object) -> float | None:
    score = _float_or_none(value)
    if score is None:
        return None
    if score <= 1:
        return max(score, 0.0)
    if score <= 5:
        return score / 5
    return min(score / 100, 1.0)


def _credibility(
    *,
    score: float | None,
    stars: float | None,
    downloads: float | None,
    installs: float | None,
    verified: bool,
    status: str | None,
) -> float:
    explicit_score = score if score is not None else 0.0
    star_score = min(math.log10((stars or 0) + 1) / 5, 0.25)
    usage_score = min(math.log10(max(downloads or 0, installs or 0) + 1) / 7, 0.25)
    verified_score = 0.1 if verified else 0.0
    status_score = 0.1 if status in {None, "", "active"} else -0.15

    if score is None and not any((stars, downloads, installs, verified)):
        return 0.5 if status != "deprecated" else 0.35

    return min(max(round(0.15 + explicit_score * 0.35 + star_score + usage_score + verified_score + status_score, 3), 0), 1)


def _namespace_verified(server_name: str) -> bool:
    return server_name.startswith(("io.github.", "com.", "org.", "net.", "io."))


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


def _float_or_none(value: object) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        return float(value)
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


def _request_context(*, search_query: str | None, category: str | None) -> str:
    if search_query:
        return f"query '{search_query}'"
    if category:
        return f"category '{category}'"
    return "server listing"


MCPRegistryAdapter = McpRegistryAdapter
