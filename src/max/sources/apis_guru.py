"""APIs.guru source adapter — public OpenAPI directory signals."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.apis.guru/v2"
DEFAULT_ENDPOINT = "/list.json"
_DEFAULT_QUERIES: list[str] = []
_DEFAULT_PROVIDERS: list[str] = []
_DEFAULT_CATEGORIES: list[str] = []


class ApisGuruAdapter(SourceAdapter):
    """Fetch API catalog discovery signals from the APIs.guru OpenAPI Directory."""

    @property
    def name(self) -> str:
        return "apis_guru"

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
    def queries(self) -> list[str]:
        return self._configured_terms("queries", _DEFAULT_QUERIES)

    @property
    def providers(self) -> list[str]:
        return self._configured_terms("providers", _DEFAULT_PROVIDERS)

    @property
    def categories(self) -> list[str]:
        return self._configured_terms("categories", _DEFAULT_CATEGORIES)

    @property
    def preferred_versions_only(self) -> bool:
        value = self._config.get("preferred_versions_only", True)
        if isinstance(value, str):
            return value.strip().lower() not in {"0", "false", "no", "off"}
        return bool(value)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        async with httpx.AsyncClient(timeout=30) as client:
            data = await self._fetch_json(client)

        if not isinstance(data, dict):
            logger.warning("%s: APIs.guru list payload was not an object", self.name)
            return []

        signals: list[Signal] = []
        seen: set[str] = set()
        for record in _flatten_directory(data, preferred_versions_only=self.preferred_versions_only):
            if len(signals) >= limit:
                break
            if not self._passes_filters(record):
                continue

            dedupe_key = _dedupe_key(record)
            if dedupe_key in seen:
                continue

            signal = _record_to_signal(record, adapter_name=self.name)
            if signal is None:
                continue

            seen.add(dedupe_key)
            signals.append(signal)

        return signals

    async def _fetch_json(self, client: httpx.AsyncClient) -> dict | list | None:
        try:
            resp = await fetch_with_retry(
                self._list_url(),
                client,
                adapter_name=self.name,
                headers={"User-Agent": "max-apis-guru-adapter/0.1"},
            )
            return resp.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch APIs.guru data: %s", self.name, e)
        except ValueError as e:
            logger.warning("%s: failed to parse APIs.guru JSON response: %s", self.name, e)
        return None

    def _list_url(self) -> str:
        return f"{self.base_url}{DEFAULT_ENDPOINT}"

    def _passes_filters(self, record: dict[str, Any]) -> bool:
        if self.providers and not _matches_any(record["provider"], self.providers):
            return False

        searchable = _searchable_text(record)
        if self.queries and not any(term.lower() in searchable for term in self.queries_lower):
            return False

        if self.categories:
            category_text = " ".join(record["categories"]).lower()
            if not any(term.lower() in category_text for term in self.categories):
                return False

        return True

    @property
    def queries_lower(self) -> list[str]:
        return [term.lower() for term in self.queries]


def _flatten_directory(
    data: dict[str, Any],
    *,
    preferred_versions_only: bool,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for api_key, entry in data.items():
        if not isinstance(api_key, str) or not isinstance(entry, dict):
            continue

        versions = entry.get("versions")
        if not isinstance(versions, dict):
            continue

        preferred = _string_or_none(entry.get("preferred"))
        version_items = _selected_versions(versions, preferred, preferred_versions_only)
        for version, payload in version_items:
            if not isinstance(payload, dict):
                continue
            info = payload.get("info")
            if not isinstance(info, dict):
                info = {}

            provider = _provider(api_key, entry, payload, info)
            api_name = _api_name(api_key, info)
            if provider is None or api_name is None:
                continue

            records.append(
                {
                    "provider": provider,
                    "api_name": api_name,
                    "version": version,
                    "preferred": preferred is not None and version == preferred,
                    "title": _string_or_none(info.get("title")) or api_name,
                    "description": _string_or_none(info.get("description")),
                    "api_url": _api_url(payload, info),
                    "swagger_url": _string_or_none(
                        payload.get("swaggerUrl")
                        or payload.get("swagger_url")
                        or payload.get("url")
                    ),
                    "openapi_ver": _string_or_none(
                        payload.get("openapiVer")
                        or payload.get("openapi")
                        or payload.get("swagger")
                    ),
                    "added": _string_or_none(payload.get("added") or entry.get("added")),
                    "updated": _string_or_none(payload.get("updated") or entry.get("updated")),
                    "categories": _categories(entry, payload, info),
                }
            )

    return records


def _selected_versions(
    versions: dict[str, Any],
    preferred: str | None,
    preferred_versions_only: bool,
) -> list[tuple[str, Any]]:
    if preferred_versions_only:
        if preferred and preferred in versions:
            return [(preferred, versions[preferred])]
        first = next(iter(versions.items()), None)
        return [first] if first is not None else []
    return list(versions.items())


def _record_to_signal(record: dict[str, Any], *, adapter_name: str) -> Signal | None:
    title = _title(record)
    description = record["description"] or title
    url = record["api_url"] or record["swagger_url"]
    if not url:
        return None

    updated_at = _parse_datetime(record["updated"] or record["added"])
    tags = _dedupe([record["provider"], *record["categories"]])[:10]
    metadata = {
        "provider": record["provider"],
        "api_name": record["api_name"],
        "version": record["version"],
        "preferred": record["preferred"],
        "swagger_url": record["swagger_url"],
        "openapi_ver": record["openapi_ver"],
        "added": record["added"],
        "updated": record["updated"],
        "api_url": url,
        "categories": record["categories"],
    }

    return Signal(
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=title,
        content=description[:500],
        url=url,
        published_at=updated_at,
        tags=tags,
        credibility=0.65 if record["preferred"] else 0.55,
        metadata=metadata,
    )


def _provider(
    api_key: str,
    entry: dict[str, Any],
    payload: dict[str, Any],
    info: dict[str, Any],
) -> str | None:
    configured = _string_or_none(
        info.get("x-providerName")
        or payload.get("x-providerName")
        or entry.get("x-providerName")
        or entry.get("provider")
    )
    if configured:
        return configured
    return _string_or_none(api_key.split(":", 1)[0])


def _api_name(api_key: str, info: dict[str, Any]) -> str | None:
    service = _string_or_none(info.get("x-serviceName"))
    if service:
        return service
    if ":" in api_key:
        return _string_or_none(api_key.split(":", 1)[1])
    return _string_or_none(api_key)


def _api_url(payload: dict[str, Any], info: dict[str, Any]) -> str | None:
    explicit = _string_or_none(
        info.get("x-apiClientRegistration")
        or info.get("termsOfService")
        or payload.get("apiUrl")
        or payload.get("api_url")
    )
    if explicit:
        return explicit

    contact = info.get("contact")
    if isinstance(contact, dict):
        return _string_or_none(contact.get("url"))
    return None


def _categories(
    entry: dict[str, Any],
    payload: dict[str, Any],
    info: dict[str, Any],
) -> list[str]:
    values: list[object] = []
    for item in (entry, payload, info):
        raw = item.get("categories") or item.get("x-apisguru-categories")
        if isinstance(raw, list):
            values.extend(raw)
        elif isinstance(raw, str):
            values.extend(part.strip() for part in raw.split(","))
    return _dedupe([value for value in values if isinstance(value, str)])


def _title(record: dict[str, Any]) -> str:
    version = record["version"]
    title = record["title"]
    if version:
        return f"{title} ({version})"
    return title


def _searchable_text(record: dict[str, Any]) -> str:
    values = [
        record["provider"],
        record["api_name"],
        record["title"],
        record["description"] or "",
        *record["categories"],
    ]
    return " ".join(values).lower()


def _matches_any(value: str, terms: list[str]) -> bool:
    normalized = value.lower()
    return any(term.lower() == normalized for term in terms)


def _dedupe_key(record: dict[str, Any]) -> str:
    return "|".join(
        str(record.get(key) or "").strip().lower()
        for key in ("provider", "api_name", "version", "swagger_url")
    )


def _parse_datetime(value: object) -> datetime | None:
    text = _string_or_none(value)
    if text is None:
        return None
    try:
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
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


ApisGuruAdapter = ApisGuruAdapter
