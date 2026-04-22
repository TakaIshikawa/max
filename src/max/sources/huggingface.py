"""Hugging Face Hub source adapter — model, dataset, and Space discovery signals."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

HUGGINGFACE_MODELS = "https://huggingface.co/api/models"
HUGGINGFACE_DATASETS = "https://huggingface.co/api/datasets"
HUGGINGFACE_SPACES = "https://huggingface.co/api/spaces"

_DEFAULT_QUERIES = ["ai agent", "llm", "developer tools", "mcp", "automation"]
_DEFAULT_RESOURCE_TYPES = ["model", "dataset", "space"]
_RESOURCE_ENDPOINTS = {
    "model": HUGGINGFACE_MODELS,
    "dataset": HUGGINGFACE_DATASETS,
    "space": HUGGINGFACE_SPACES,
}
_RESOURCE_ALIASES = {
    "models": "model",
    "dataset": "dataset",
    "datasets": "dataset",
    "space": "space",
    "spaces": "space",
    "model": "model",
}


class HuggingFaceAdapter(SourceAdapter):
    """Fetch Hugging Face Hub model, dataset, and Space discovery signals."""

    @property
    def name(self) -> str:
        return "huggingface"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def queries(self) -> list[str]:
        return self._configured_terms("queries", _DEFAULT_QUERIES)

    @property
    def resource_types(self) -> list[str]:
        configured = self._config.get("resource_types")
        values = _DEFAULT_RESOURCE_TYPES if configured is None else configured
        if not isinstance(values, list):
            return list(_DEFAULT_RESOURCE_TYPES)

        resource_types: list[str] = []
        seen: set[str] = set()
        for value in values:
            if not isinstance(value, str):
                continue
            normalized = _RESOURCE_ALIASES.get(value.strip().lower())
            if normalized is None or normalized in seen:
                continue
            seen.add(normalized)
            resource_types.append(normalized)
        return resource_types

    @property
    def sort(self) -> str:
        configured = self._config.get("sort")
        if isinstance(configured, str) and configured.strip():
            return configured.strip()
        return "downloads"

    @property
    def limit_per_query(self) -> int:
        value = _int_or_none(self._config.get("limit_per_query"))
        if value is None:
            return 10
        return max(1, min(value, 100))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen: set[tuple[str, str]] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            for resource_type in self.resource_types:
                if len(signals) >= limit:
                    break

                for query in self.queries:
                    if len(signals) >= limit:
                        break

                    data = await self._fetch_json(
                        client,
                        resource_type=resource_type,
                        search_query=query,
                        limit=min(self.limit_per_query, max(1, limit - len(signals))),
                    )
                    if data is None:
                        continue

                    entries = data if isinstance(data, list) else data.get("items", [])
                    for entry in entries:
                        if len(signals) >= limit:
                            break
                        if not isinstance(entry, dict):
                            continue

                        repo_id = _repo_id(entry)
                        if repo_id is None:
                            continue

                        dedupe_key = (resource_type, repo_id.lower())
                        if dedupe_key in seen:
                            continue

                        try:
                            signal = _entry_to_signal(
                                entry,
                                adapter_name=self.name,
                                resource_type=resource_type,
                                search_query=query,
                            )
                        except (TypeError, ValueError) as e:
                            logger.warning(
                                "%s: failed to parse Hugging Face %s entry %s: %s",
                                self.name,
                                resource_type,
                                repo_id,
                                e,
                            )
                            continue

                        seen.add(dedupe_key)
                        signals.append(signal)

        return signals[:limit]

    async def _fetch_json(
        self,
        client: httpx.AsyncClient,
        *,
        resource_type: str,
        search_query: str,
        limit: int,
    ) -> list | dict | None:
        try:
            resp = await fetch_with_retry(
                _RESOURCE_ENDPOINTS[resource_type],
                client,
                adapter_name=self.name,
                params={
                    "search": search_query,
                    "sort": self.sort,
                    "direction": "-1",
                    "limit": limit,
                    "full": "true",
                },
                headers={"User-Agent": "max-huggingface-adapter/0.1"},
            )
            return resp.json()
        except (AdapterFetchError, httpx.RequestError) as e:
            logger.warning(
                "%s: failed to fetch Hugging Face %s data for query '%s': %s",
                self.name,
                resource_type,
                search_query,
                e,
            )
        except ValueError as e:
            logger.warning(
                "%s: failed to parse JSON response for Hugging Face %s query '%s': %s",
                self.name,
                resource_type,
                search_query,
                e,
            )
        return None


def _entry_to_signal(
    entry: dict[str, Any],
    *,
    adapter_name: str,
    resource_type: str,
    search_query: str,
) -> Signal:
    repo_id = _repo_id(entry)
    if repo_id is None:
        raise ValueError("missing repository id")

    author = _string_or_none(entry.get("author")) or _author_from_repo_id(repo_id)
    downloads = _int_or_none(entry.get("downloads")) or 0
    likes = _int_or_none(entry.get("likes")) or 0
    last_modified = _parse_datetime(
        entry.get("lastModified")
        or entry.get("last_modified")
        or entry.get("updatedAt")
        or entry.get("modified")
    )
    raw_tags = _extract_tags(entry)
    tags = _build_tags(entry, raw_tags=raw_tags, resource_type=resource_type, search_query=search_query)
    description = _description(entry) or repo_id
    url = _resource_url(resource_type, repo_id)

    metadata = {
        "resource_type": resource_type,
        "repo_id": repo_id,
        "author": author,
        "downloads": downloads,
        "likes": likes,
        "last_modified": last_modified.isoformat() if last_modified else None,
        "search_query": search_query,
        "tags": raw_tags,
        "pipeline_tag": _string_or_none(entry.get("pipeline_tag")),
        "library_name": _string_or_none(entry.get("library_name")),
        "sdk": _string_or_none(entry.get("sdk")),
        "private": entry.get("private"),
        "gated": entry.get("gated"),
    }

    return Signal(
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=repo_id,
        content=description[:500],
        url=url,
        author=author,
        published_at=last_modified,
        tags=tags,
        credibility=_credibility(downloads=downloads, likes=likes, last_modified=last_modified),
        metadata=metadata,
    )


def _repo_id(entry: dict[str, Any]) -> str | None:
    return (
        _string_or_none(entry.get("id"))
        or _string_or_none(entry.get("modelId"))
        or _string_or_none(entry.get("datasetId"))
        or _string_or_none(entry.get("spaceId"))
        or _string_or_none(entry.get("name"))
    )


def _description(entry: dict[str, Any]) -> str | None:
    for key in ("description", "summary"):
        value = _string_or_none(entry.get(key))
        if value:
            return value

    card_data = entry.get("cardData")
    if isinstance(card_data, dict):
        for key in ("description", "summary", "pretty_name"):
            value = _string_or_none(card_data.get(key))
            if value:
                return value
    return None


def _extract_tags(entry: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    raw_tags = entry.get("tags")
    if isinstance(raw_tags, list):
        tags.extend(value.strip() for value in raw_tags if isinstance(value, str) and value.strip())

    card_data = entry.get("cardData")
    if isinstance(card_data, dict):
        for value in card_data.get("tags") or []:
            if isinstance(value, str) and value.strip():
                tags.append(value.strip())

    return _dedupe(tags)


def _build_tags(
    entry: dict[str, Any],
    *,
    raw_tags: list[str],
    resource_type: str,
    search_query: str,
) -> list[str]:
    tags = [resource_type, *raw_tags]
    for key in ("pipeline_tag", "library_name", "sdk"):
        value = _string_or_none(entry.get(key))
        if value:
            tags.append(value)
    tags.append(search_query)
    return _dedupe(tags)[:10]


def _resource_url(resource_type: str, repo_id: str) -> str:
    if resource_type == "dataset":
        return f"https://huggingface.co/datasets/{repo_id}"
    if resource_type == "space":
        return f"https://huggingface.co/spaces/{repo_id}"
    return f"https://huggingface.co/{repo_id}"


def _credibility(*, downloads: int, likes: int, last_modified: datetime | None) -> float:
    download_score = min(math.log10(downloads + 1) / 10, 0.45)
    like_score = min(math.log10(likes + 1) / 5, 0.35)
    freshness_score = 0.0
    if last_modified is not None:
        age_days = (datetime.now(timezone.utc) - last_modified).days
        if age_days <= 30:
            freshness_score = 0.15
        elif age_days <= 180:
            freshness_score = 0.1
        elif age_days <= 365:
            freshness_score = 0.05
    return min(round(0.1 + download_score + like_score + freshness_score, 3), 1.0)


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


def _author_from_repo_id(repo_id: str) -> str | None:
    if "/" not in repo_id:
        return None
    return repo_id.split("/", 1)[0] or None


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
