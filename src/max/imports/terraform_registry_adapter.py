"""Terraform Registry import adapter for module and provider signals."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

TERRAFORM_REGISTRY_BASE_URL = "https://registry.terraform.io"
_DEFAULT_MODULE_QUERIES = ["ai", "data", "security", "platform"]
_DEFAULT_PROVIDER_NAMESPACES = ["hashicorp"]


class TerraformRegistryAdapter(SourceAdapter):
    """Fetch Terraform Registry modules and providers as normalized signals."""

    @property
    def name(self) -> str:
        return "terraform_registry_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def base_url(self) -> str:
        configured = self._config.get("base_url")
        if isinstance(configured, str) and configured.strip():
            return configured.strip().rstrip("/")
        return TERRAFORM_REGISTRY_BASE_URL

    @property
    def module_queries(self) -> list[str]:
        configured = self._config.get("module_queries")
        if configured is None:
            configured = self._config.get("queries")
        values = _string_values(configured) if configured is not None else list(_DEFAULT_MODULE_QUERIES)
        return _dedupe(values + _string_values(self._config.get("watchlist_terms")))

    @property
    def provider_namespaces(self) -> list[str]:
        configured = self._config.get("provider_namespaces")
        if configured is None:
            configured = self._config.get("namespaces")
        values = _string_values(configured) if configured is not None else list(_DEFAULT_PROVIDER_NAMESPACES)
        return _dedupe(values)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0:
            return []

        signals: list[Signal] = []
        seen: set[str] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            for query in self.module_queries:
                if len(signals) >= limit:
                    break
                await self._fetch_module_query(
                    client,
                    query=query,
                    signals=signals,
                    seen=seen,
                    limit=limit,
                )

            for namespace in self.provider_namespaces:
                if len(signals) >= limit:
                    break
                await self._fetch_provider_namespace(
                    client,
                    namespace=namespace,
                    signals=signals,
                    seen=seen,
                    limit=limit,
                )

        return signals[:limit]

    async def _fetch_module_query(
        self,
        client: httpx.AsyncClient,
        *,
        query: str,
        signals: list[Signal],
        seen: set[str],
        limit: int,
    ) -> None:
        offset = 0
        while len(signals) < limit:
            request_limit = min(100, max(1, limit - len(signals)))
            data = await self._fetch_json(
                client,
                f"{self.base_url}/v1/modules/search",
                context=f"module query '{query}'",
                params={"q": query, "limit": request_limit, "offset": offset},
            )
            items = _extract_items(data, "modules")
            if not items:
                break

            before = len(signals)
            self._append_signals(
                signals,
                items,
                seen=seen,
                limit=limit,
                item_type="module",
                search_query=query,
                provider_namespace=None,
            )
            next_offset = _next_offset(data)
            if len(signals) == before:
                break
            if next_offset is not None:
                offset = next_offset
                continue
            if len(items) < request_limit:
                break
            offset += len(items)

    async def _fetch_provider_namespace(
        self,
        client: httpx.AsyncClient,
        *,
        namespace: str,
        signals: list[Signal],
        seen: set[str],
        limit: int,
    ) -> None:
        offset = 0
        while len(signals) < limit:
            request_limit = min(100, max(1, limit - len(signals)))
            data = await self._fetch_json(
                client,
                f"{self.base_url}/v1/providers/{quote(namespace, safe='')}",
                context=f"provider namespace '{namespace}'",
                params={"limit": request_limit, "offset": offset},
            )
            items = _extract_items(data, "providers")
            if not items:
                break

            before = len(signals)
            self._append_signals(
                signals,
                items,
                seen=seen,
                limit=limit,
                item_type="provider",
                search_query=None,
                provider_namespace=namespace,
            )
            next_offset = _next_offset(data)
            if len(signals) == before:
                break
            if next_offset is not None:
                offset = next_offset
                continue
            if len(items) < request_limit:
                break
            offset += len(items)

    async def _fetch_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        context: str,
        params: dict[str, object],
    ) -> object | None:
        try:
            resp = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                params=params,
                headers={"User-Agent": "max-terraform-registry-import-adapter/0.1"},
            )
            return resp.json()
        except Exception:
            logger.warning("%s: failed to fetch Terraform Registry %s", self.name, context, exc_info=True)
            return None

    def _append_signals(
        self,
        signals: list[Signal],
        items: list[dict],
        *,
        seen: set[str],
        limit: int,
        item_type: str,
        search_query: str | None,
        provider_namespace: str | None,
    ) -> None:
        for item in items:
            if len(signals) >= limit:
                break
            try:
                signal = _item_to_signal(
                    item,
                    item_type=item_type,
                    adapter_name=self.name,
                    base_url=self.base_url,
                    search_query=search_query,
                    provider_namespace=provider_namespace,
                )
                identity = _identity(signal.metadata)
                if identity in seen:
                    continue
                seen.add(identity)
                signals.append(signal)
            except (TypeError, ValueError):
                logger.warning("%s: failed to parse Terraform Registry %s", self.name, item_type, exc_info=True)


def _item_to_signal(
    item: dict,
    *,
    item_type: str,
    adapter_name: str,
    base_url: str,
    search_query: str | None,
    provider_namespace: str | None,
) -> Signal:
    namespace = _string_or_none(item.get("namespace") or item.get("owner") or provider_namespace)
    name = _string_or_none(item.get("name") or item.get("type"))
    provider = _string_or_none(item.get("provider"))

    if item_type == "module":
        namespace, name, provider = _module_identity(item, namespace, name, provider)
    else:
        namespace, name = _provider_identity(item, namespace, name)
        provider = name

    if namespace is None or name is None:
        raise ValueError("missing namespace or name")
    if item_type == "module" and provider is None:
        raise ValueError("module missing provider")

    version = _string_or_none(item.get("version") or item.get("latest_version"))
    downloads = _int_or_none(
        item.get("downloads")
        or item.get("download_count")
        or item.get("downloads_count")
        or item.get("total_downloads")
    )
    verified = _bool_or_none(item.get("verified"))
    description = _string_or_none(item.get("description")) or _display_name(
        item_type=item_type,
        namespace=namespace,
        name=name,
        provider=provider,
    )
    published_at = _parse_datetime(
        item.get("published_at")
        or item.get("publishedAt")
        or item.get("created_at")
        or item.get("createdAt")
        or item.get("updated_at")
        or item.get("updatedAt")
    )
    source_url = _source_url(
        item,
        base_url=base_url,
        item_type=item_type,
        namespace=namespace,
        name=name,
        provider=provider,
    )

    metadata = {
        "type": item_type,
        "namespace": namespace,
        "name": name,
        "provider": provider,
        "version": version,
        "downloads": downloads,
        "verified": verified,
        "description": description,
        "published_at": published_at.isoformat() if published_at is not None else None,
        "source_url": source_url,
        "search_query": search_query,
        "provider_namespace": provider_namespace,
    }

    return Signal(
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=_title(item_type=item_type, namespace=namespace, name=name, provider=provider, version=version),
        content=description[:500],
        url=source_url,
        author=namespace,
        published_at=published_at,
        tags=_tags(item_type=item_type, search_query=search_query, provider=provider),
        credibility=_credibility(downloads=downloads, verified=verified),
        metadata=metadata,
    )


def _extract_items(data: object | None, key: str) -> list[dict]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    for candidate in (key, "results", "items"):
        value = data.get(candidate)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _next_offset(data: object | None) -> int | None:
    if not isinstance(data, dict):
        return None
    candidates = [data.get("next_offset"), data.get("nextOffset")]
    meta = data.get("meta")
    if isinstance(meta, dict):
        candidates.extend([meta.get("next_offset"), meta.get("nextOffset")])
    for candidate in candidates:
        parsed = _int_or_none(candidate)
        if parsed is not None:
            return parsed
    return None


def _module_identity(
    item: dict,
    namespace: str | None,
    name: str | None,
    provider: str | None,
) -> tuple[str | None, str | None, str | None]:
    if namespace and name and provider:
        return namespace, name, provider
    module_id = _string_or_none(item.get("id") or item.get("slug"))
    if module_id:
        parts = [part for part in module_id.strip("/").split("/") if part]
        if len(parts) >= 3:
            namespace = namespace or parts[-3]
            name = name or parts[-2]
            provider = provider or parts[-1]
    return namespace, name, provider


def _provider_identity(item: dict, namespace: str | None, name: str | None) -> tuple[str | None, str | None]:
    if namespace and name:
        return namespace, name
    provider_id = _string_or_none(item.get("id") or item.get("slug"))
    if provider_id:
        parts = [part for part in provider_id.strip("/").split("/") if part]
        if len(parts) >= 2:
            namespace = namespace or parts[-2]
            name = name or parts[-1]
    return namespace, name


def _display_name(*, item_type: str, namespace: str, name: str, provider: str | None) -> str:
    if item_type == "module":
        return f"{namespace}/{name}/{provider}"
    return f"{namespace}/{name}"


def _title(*, item_type: str, namespace: str, name: str, provider: str | None, version: str | None) -> str:
    base = _display_name(item_type=item_type, namespace=namespace, name=name, provider=provider)
    return f"{base}@{version}" if version else base


def _source_url(
    item: dict,
    *,
    base_url: str,
    item_type: str,
    namespace: str,
    name: str,
    provider: str | None,
) -> str:
    for key in ("source_url", "sourceUrl", "url", "html_url"):
        value = _string_or_none(item.get(key))
        if value:
            return value
    if item_type == "module":
        return f"{base_url}/modules/{quote(namespace, safe='')}/{quote(name, safe='')}/{quote(provider or '', safe='')}"
    return f"{base_url}/providers/{quote(namespace, safe='')}/{quote(name, safe='')}"


def _tags(*, item_type: str, search_query: str | None, provider: str | None) -> list[str]:
    values = [item_type]
    if provider:
        values.append(provider)
    if search_query:
        values.append(search_query)
    return _dedupe(values)


def _identity(metadata: dict) -> str:
    return "|".join(str(metadata.get(key) or "").lower() for key in ("type", "namespace", "name", "provider", "version"))


def _credibility(*, downloads: int | None, verified: bool | None) -> float:
    download_score = min(math.log10((downloads or 0) + 1) / 7, 0.75)
    verified_score = 0.15 if verified is True else 0.0
    return min(round(0.1 + download_score + verified_score, 3), 1.0)


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


def _string_values(value: object) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        return []
    return [item.strip() for item in values if isinstance(item, str) and item.strip()]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _int_or_none(value: object) -> int | None:
    try:
        if value is None:
            return None
        return max(int(value), 0)
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
