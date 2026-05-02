"""Go package discovery source adapter."""

from __future__ import annotations

import hashlib
import html
import logging
import math
import re
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlparse

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

PKG_GO_DEV_SEARCH = "https://pkg.go.dev/search"
PKG_GO_DEV_BASE = "https://pkg.go.dev"

_DEFAULT_QUERIES = ["ai", "llm", "agent", "mcp", "devtools"]


class GoPackagesAdapter(SourceAdapter):
    """Fetch Go package/module discovery signals from pkg.go.dev search."""

    @property
    def name(self) -> str:
        return "go_packages"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def queries(self) -> list[str]:
        return self._configured_terms("queries", _DEFAULT_QUERIES)

    @property
    def package_names(self) -> list[str]:
        return self._configured_terms("package_names", [])

    @property
    def max_results(self) -> int:
        return max(_int_or_none(self._config.get("max_results")) or 10, 1)

    @property
    def min_imported_by(self) -> int:
        return max(_int_or_none(self._config.get("min_imported_by")) or 0, 0)

    @property
    def include_stdlib(self) -> bool:
        return bool(self._config.get("include_stdlib", False))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_modules: set[str] = set()
        item_limit = max(limit, 0)
        if item_limit == 0:
            return signals

        async with httpx.AsyncClient(timeout=30) as client:
            for package_name in self.package_names:
                if len(signals) >= item_limit:
                    break

                normalized = _normalize_module_path(package_name)
                dedupe_key = _dedupe_key(normalized)
                if not normalized or dedupe_key in seen_modules:
                    continue

                data = await self._fetch_package(client, package_name=normalized)
                if data is None:
                    continue

                item = _extract_package_item(data, fallback_module_path=normalized)
                signal = _item_to_signal(
                    item,
                    adapter_name=self.name,
                    search_query=None,
                    lookup_type="package",
                )
                if signal is None:
                    continue
                if not self._should_include(signal):
                    continue

                seen_modules.add(dedupe_key)
                signals.append(signal)

            for query in self.queries:
                if len(signals) >= item_limit:
                    break

                per_query_limit = min(self.max_results, item_limit - len(signals))
                data = await self._fetch_search(client, query=query, limit=per_query_limit)
                if data is None:
                    continue

                for item in _extract_result_items(data)[:per_query_limit]:
                    if len(signals) >= item_limit:
                        break

                    signal = _item_to_signal(
                        item,
                        adapter_name=self.name,
                        search_query=query,
                        lookup_type="search",
                    )
                    if signal is None:
                        continue
                    module_path = signal.metadata["module_path"]
                    dedupe_key = _dedupe_key(module_path)
                    if dedupe_key in seen_modules:
                        continue
                    if not self._should_include(signal):
                        continue

                    seen_modules.add(dedupe_key)
                    signals.append(signal)

        return signals[:item_limit]

    def _should_include(self, signal: Signal) -> bool:
        module_path = signal.metadata["module_path"]
        if not self.include_stdlib and _is_stdlib_path(module_path):
            return False
        imported_by = signal.metadata["imported_by_count"]
        return not (imported_by is not None and imported_by < self.min_imported_by)

    async def _fetch_search(
        self,
        client: httpx.AsyncClient,
        *,
        query: str,
        limit: int,
    ) -> dict | str | None:
        try:
            resp = await fetch_with_retry(
                PKG_GO_DEV_SEARCH,
                client,
                adapter_name=self.name,
                params={"q": query, "limit": limit},
                headers={"User-Agent": "max-go-packages-adapter/0.1"},
            )
            content_type = resp.headers.get("content-type", "")
            if "json" in content_type:
                return resp.json()
            text = resp.text
            try:
                return resp.json()
            except ValueError:
                return text
        except AdapterFetchError as e:
            logger.warning(
                "%s: failed to fetch Go package search results for query '%s': %s",
                self.name,
                query,
                e,
            )
        except ValueError as e:
            logger.warning(
                "%s: failed to parse Go package search results for query '%s': %s",
                self.name,
                query,
                e,
            )
        return None

    async def _fetch_package(
        self,
        client: httpx.AsyncClient,
        *,
        package_name: str,
    ) -> dict | str | None:
        url = _package_page_url(package_name)
        try:
            resp = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                headers={"User-Agent": "max-go-packages-adapter/0.1"},
            )
            try:
                return resp.json()
            except ValueError:
                return resp.text
        except AdapterFetchError as e:
            logger.warning(
                "%s: failed to fetch Go package metadata for '%s': %s",
                self.name,
                package_name,
                e,
            )
        except ValueError as e:
            logger.warning(
                "%s: failed to parse Go package metadata for '%s': %s",
                self.name,
                package_name,
                e,
            )
        return None


def _extract_result_items(data: dict | str) -> list[dict]:
    if isinstance(data, dict):
        for key in ("results", "packages", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    parser = _PkgGoDevSearchParser()
    parser.feed(data)
    return parser.results()


def _extract_package_item(data: dict | str, *, fallback_module_path: str) -> dict:
    if isinstance(data, dict):
        for key in ("package", "module", "result", "metadata"):
            value = data.get(key)
            if isinstance(value, dict):
                item = dict(value)
                item.setdefault("module_path", fallback_module_path)
                return item
        item = dict(data)
        item.setdefault("module_path", fallback_module_path)
        return item

    parser = _PkgGoDevPackageParser(fallback_module_path=fallback_module_path)
    parser.feed(data)
    return parser.result()


def _item_to_signal(
    item: dict,
    *,
    adapter_name: str,
    search_query: str | None,
    lookup_type: str,
) -> Signal | None:
    module_path = _module_path(item)
    if module_path is None:
        return None

    synopsis = _string_or_none(item.get("synopsis")) or _string_or_none(item.get("description"))
    synopsis = synopsis or module_path
    version = _string_or_none(item.get("version"))
    imported_by_count = _int_or_none(
        item.get("imported_by_count")
        or item.get("imported_by")
        or item.get("importedByCount")
        or item.get("importedBy")
    )
    package_url = _package_url(item, module_path)
    tags = _build_tags(item, search_query=search_query, module_path=module_path)

    metadata = {
        "package_ecosystem": "go",
        "module_path": module_path,
        "package_name": module_path,
        "synopsis": synopsis,
        "imported_by_count": imported_by_count,
        "version": version,
        "package_url": package_url,
        "search_query": search_query,
        "query": search_query,
        "lookup_type": lookup_type,
        "signal_kind": "package_metadata",
        "signal_role": "solution",
    }

    return Signal(
        id=_signal_id(module_path),
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=f"{module_path}@{version}" if version else module_path,
        content=synopsis[:500],
        url=package_url,
        tags=tags,
        credibility=_credibility(imported_by_count),
        metadata=metadata,
    )


def _module_path(item: dict) -> str | None:
    for key in ("module_path", "package_path", "path", "name", "modulePath", "packagePath"):
        value = _string_or_none(item.get(key))
        if value:
            return _normalize_module_path(value)

    url = _string_or_none(item.get("url")) or _string_or_none(item.get("package_url"))
    if url:
        parsed = urlparse(url)
        path = parsed.path.lstrip("/")
        if path:
            return _normalize_module_path(path)
    return None


def _package_url(item: dict, module_path: str) -> str:
    configured = _string_or_none(item.get("package_url")) or _string_or_none(item.get("url"))
    if configured:
        return urljoin(PKG_GO_DEV_BASE, configured)
    return _package_page_url(module_path)


def _package_page_url(module_path: str) -> str:
    return f"{PKG_GO_DEV_BASE}/{quote(module_path, safe='/')}"


def _build_tags(item: dict, *, search_query: str | None, module_path: str) -> list[str]:
    tags = ["go", "golang"]
    if search_query:
        tags.append(search_query)
    tags.extend(_string_list(item.get("tags")))
    tags.extend(_string_list(item.get("licenses")))
    if _is_stdlib_path(module_path):
        tags.append("stdlib")
    if _int_or_none(item.get("imported_by_count") or item.get("imported_by")):
        tags.append("package-popularity")

    seen: set[str] = set()
    deduped: list[str] = []
    for tag in tags:
        tag = tag.strip()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        deduped.append(tag)
    return deduped[:10]


def _credibility(imported_by_count: int | None) -> float:
    if imported_by_count is None:
        return 0.4
    return min(round(0.2 + min(math.log10(imported_by_count + 1) / 6, 0.75), 3), 1.0)


def _signal_id(module_path: str) -> str:
    normalized_path = module_path.strip().lower()
    digest = hashlib.sha1(normalized_path.encode()).hexdigest()[:12]
    return f"go_packages:{digest}"


def _normalize_module_path(value: str) -> str:
    value = html.unescape(value).strip()
    value = re.sub(r"\s+", " ", value)
    value = value.removeprefix(PKG_GO_DEV_BASE).strip("/")
    return value


def _dedupe_key(module_path: str) -> str:
    return _normalize_module_path(module_path).lower()


def _is_stdlib_path(module_path: str) -> bool:
    first = module_path.split("/", 1)[0]
    return "." not in first


def _int_or_none(value: object) -> int | None:
    if isinstance(value, str):
        value = value.replace(",", "").strip()
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"[, ]+", value) if part.strip()]
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


class _PkgGoDevSearchParser(HTMLParser):
    """Small pkg.go.dev search parser used when only HTML is available."""

    def __init__(self) -> None:
        super().__init__()
        self._links: list[dict[str, str | int | None]] = []
        self._current_href: str | None = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if not href:
            return
        path = urlparse(href).path
        if not path or path in {"/", "/search"}:
            return
        self._current_href = href
        self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._current_href is None:
            return
        text = " ".join(part.strip() for part in self._current_text if part.strip())
        module_path = _normalize_module_path(text) if text else _normalize_module_path(
            urlparse(self._current_href).path
        )
        if module_path and not module_path.startswith(("search", "about", "license")):
            self._links.append(
                {
                    "module_path": module_path,
                    "package_url": urljoin(PKG_GO_DEV_BASE, self._current_href),
                    "synopsis": module_path,
                    "imported_by_count": None,
                }
            )
        self._current_href = None
        self._current_text = []

    def results(self) -> list[dict]:
        seen: set[str] = set()
        results: list[dict] = []
        for link in self._links:
            module_path = str(link["module_path"])
            if module_path in seen:
                continue
            seen.add(module_path)
            results.append(link)
        return results


class _PkgGoDevPackageParser(HTMLParser):
    """Extract basic metadata from a pkg.go.dev package page."""

    def __init__(self, *, fallback_module_path: str) -> None:
        super().__init__()
        self._fallback_module_path = fallback_module_path
        self._go_import: str | None = None
        self._title: str | None = None
        self._description: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "meta":
            return
        values = dict(attrs)
        name = values.get("name") or values.get("property")
        content = values.get("content")
        if not content:
            return
        if name == "go-import" and self._go_import is None:
            self._go_import = content
        if name == "og:title" and self._title is None:
            self._title = content
        if name in {"description", "og:description"} and self._description is None:
            self._description = content

    def result(self) -> dict:
        module_path = self._fallback_module_path
        if self._go_import:
            module_path = _normalize_module_path(self._go_import.split()[0])
        elif self._title and " - " in self._title:
            module_path = _normalize_module_path(self._title.split(" - ", 2)[1])
        return {
            "module_path": module_path or self._fallback_module_path,
            "package_url": _package_page_url(self._fallback_module_path),
            "synopsis": self._description or module_path or self._fallback_module_path,
            "imported_by_count": None,
        }
