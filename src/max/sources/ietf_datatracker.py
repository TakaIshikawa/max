"""IETF Datatracker source adapter."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://datatracker.ietf.org"
DOCUMENT_ENDPOINT = "/api/v1/doc/document/"
DOCUMENT_WEB_BASE = "https://datatracker.ietf.org/doc"

_DEFAULT_KEYWORDS: list[str] = []
_DEFAULT_STREAMS: list[str] = []
_DEFAULT_STATUSES: list[str] = []
_DEFAULT_MAX_RESULTS = 100


class IetfDatatrackerAdapter(SourceAdapter):
    """Fetch recent IETF draft and RFC activity from the IETF Datatracker API."""

    config_keys = ["base_url", "keywords", "streams", "statuses", "max_results"]
    required_keys: list[str] = []
    description = "Fetches recent IETF Datatracker draft and RFC standards activity."

    @property
    def name(self) -> str:
        return "ietf_datatracker"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def base_url(self) -> str:
        configured = self._config.get("base_url")
        if isinstance(configured, str) and configured.strip():
            return configured.strip().rstrip("/")
        return DEFAULT_BASE_URL

    @property
    def keywords(self) -> list[str]:
        return self._configured_terms("keywords", _DEFAULT_KEYWORDS)

    @property
    def streams(self) -> list[str]:
        return _string_list(self._config.get("streams", _DEFAULT_STREAMS))

    @property
    def statuses(self) -> list[str]:
        return _string_list(self._config.get("statuses", _DEFAULT_STATUSES))

    @property
    def max_results(self) -> int:
        return max(_int_or_none(self._config.get("max_results")) or _DEFAULT_MAX_RESULTS, 1)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        effective_limit = min(max(limit, 1), self.max_results)
        fetch_limit = max(effective_limit * 3, effective_limit)

        async with httpx.AsyncClient(timeout=30) as client:
            records = await self._fetch_records(client, limit=fetch_limit)

        signals: list[Signal] = []
        seen_urls: set[str] = set()
        for record in records:
            if len(signals) >= effective_limit:
                break
            if not isinstance(record, dict):
                continue

            normalized = _normalize_record(record)
            if normalized is None or not self._passes_filters(normalized):
                continue

            url = normalized["url"]
            dedupe_key = url.lower()
            if dedupe_key in seen_urls:
                continue

            signal = _record_to_signal(normalized, adapter_name=self.name)
            if signal is None:
                continue

            seen_urls.add(dedupe_key)
            signals.append(signal)

        return signals

    async def _fetch_records(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        try:
            response = await fetch_with_retry(
                self._documents_url(),
                client,
                adapter_name=self.name,
                headers={"User-Agent": "max-ietf-datatracker-adapter/0.1"},
                params={"format": "json", "limit": str(limit), "order_by": "-time"},
            )
            data = response.json()
        except (AdapterFetchError, ValueError, httpx.RequestError) as e:
            logger.warning("%s: failed to fetch IETF Datatracker documents: %s", self.name, e)
            return []

        if isinstance(data, dict):
            objects = data.get("objects") or data.get("results") or data.get("documents")
            if isinstance(objects, list):
                return [item for item in objects if isinstance(item, dict)]
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        logger.warning("%s: IETF Datatracker payload did not contain document objects", self.name)
        return []

    def _documents_url(self) -> str:
        return f"{self.base_url}{DOCUMENT_ENDPOINT}"

    def _passes_filters(self, record: dict[str, Any]) -> bool:
        stream = _normalize_filter(record.get("stream"))
        status = _normalize_filter(record.get("status"))

        if self.streams and stream not in {_normalize_filter(value) for value in self.streams}:
            return False
        if self.statuses and status not in {_normalize_filter(value) for value in self.statuses}:
            return False

        if self.keywords:
            matched = _matched_keyword(record, self.keywords)
            if matched is None:
                return False
            record["matched_keyword"] = matched

        return True


def _normalize_record(record: dict[str, Any]) -> dict[str, Any] | None:
    name = _string_or_none(record.get("name") or record.get("document") or record.get("doc_name"))
    if name is None:
        return None

    title = _string_or_none(record.get("title")) or name
    abstract = _string_or_none(record.get("abstract") or record.get("description") or record.get("content"))
    url = _document_url(record, name)
    status = _extract_name(record.get("states")) or _extract_name(record.get("state") or record.get("status"))
    stream = _extract_name(record.get("stream"))
    area = _extract_name(record.get("area"))
    group = _extract_name(record.get("group"))
    published = _string_or_none(
        record.get("time")
        or record.get("published")
        or record.get("published_at")
        or record.get("created")
    )
    updated = _string_or_none(
        record.get("updated")
        or record.get("updated_at")
        or record.get("rev")
        or record.get("expires")
        or published
    )

    return {
        "name": name,
        "title": title,
        "abstract": abstract,
        "url": url,
        "status": status,
        "stream": stream,
        "area": area,
        "group": group,
        "published": published,
        "updated": updated,
        "raw": record,
    }


def _record_to_signal(record: dict[str, Any], *, adapter_name: str) -> Signal | None:
    title = record["title"]
    content = record["abstract"] or title
    url = record["url"]
    metadata = {
        "document_name": record["name"],
        "status": record["status"],
        "stream": record["stream"],
        "area": record["area"],
        "group": record["group"],
        "published": record["published"],
        "updated": record["updated"],
        "matched_keyword": record.get("matched_keyword"),
        "signal_kind": "ietf_datatracker_document",
        "signal_role": "market",
    }

    return Signal(
        id=_signal_id(url),
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"{record['name']}: {title}" if not title.startswith(record["name"]) else title,
        content=content[:4000],
        url=url,
        published_at=_parse_datetime(record["updated"] or record["published"]),
        tags=_build_tags(
            stream=record["stream"],
            status=record["status"],
            area=record["area"],
            group=record["group"],
            matched_keyword=record.get("matched_keyword"),
        ),
        credibility=0.75 if _normalize_filter(record["name"]).startswith("rfc") else 0.65,
        metadata=metadata,
    )


def _document_url(record: dict[str, Any], name: str) -> str:
    for key in ("url", "html_url", "web_url"):
        value = _string_or_none(record.get(key))
        if value and value.startswith("http"):
            return value
    return f"{DOCUMENT_WEB_BASE}/{name}/"


def _extract_name(value: object) -> str | None:
    if isinstance(value, list):
        for item in value:
            extracted = _extract_name(item)
            if extracted:
                return extracted
        return None
    if isinstance(value, dict):
        for key in ("slug", "acronym", "name", "label", "title"):
            extracted = _string_or_none(value.get(key))
            if extracted:
                return extracted
        return _slug_from_resource_uri(value.get("resource_uri"))
    extracted = _string_or_none(value)
    if extracted and extracted.startswith("/api/"):
        return _slug_from_resource_uri(extracted)
    return extracted


def _slug_from_resource_uri(value: object) -> str | None:
    text = _string_or_none(value)
    if text is None:
        return None
    parts = [part for part in text.strip("/").split("/") if part]
    return parts[-1] if parts else None


def _matched_keyword(record: dict[str, Any], keywords: list[str]) -> str | None:
    searchable = " ".join(
        str(value or "") for value in (record["name"], record["title"], record["abstract"])
    ).lower()
    for keyword in keywords:
        normalized = keyword.strip().lower()
        if normalized and normalized in searchable:
            return keyword
    return None


def _build_tags(
    *,
    stream: str | None,
    status: str | None,
    area: str | None,
    group: str | None,
    matched_keyword: str | None,
) -> list[str]:
    return _dedupe(["ietf", "standards", stream, status, area, group, matched_keyword])[:10]


def _signal_id(url: str) -> str:
    digest = hashlib.sha1(url.strip().lower().encode()).hexdigest()[:12]
    return f"ietf_datatracker:{digest}"


def _parse_datetime(value: object) -> datetime | None:
    text = _string_or_none(value)
    if text is None:
        return None
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            text = f"{text}T00:00:00+00:00"
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def _normalize_filter(value: object) -> str:
    return str(value or "").strip().lower()


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    else:
        try:
            values = list(value)  # type: ignore[arg-type]
        except TypeError:
            values = [value]
    return _dedupe([item for item in values if isinstance(item, str)])


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _dedupe(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        text = _string_or_none(value)
        if text is None:
            continue
        normalized = text.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(text)
    return deduped
