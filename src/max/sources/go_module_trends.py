"""Go module proxy activity source adapter."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime
from urllib.parse import quote

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

GO_PROXY_INDEX_URL = "https://index.golang.org/index"
GO_PROXY_BASE_URL = "https://proxy.golang.org"
PKG_GO_DEV_BASE = "https://pkg.go.dev"

_DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain",
    "User-Agent": "max-go-module-trends-adapter/0.1",
}


class GoModuleTrendsAdapter(SourceAdapter):
    """Fetch Go module version activity from the public Go module proxy."""

    @property
    def name(self) -> str:
        return "go_module_trends"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def module_paths(self) -> list[str]:
        modules = self._configured_terms("module_paths", [])
        for key in ("modules", "packages"):
            for value in self._configured_terms(key, []):
                if value not in modules:
                    modules.append(value)
        return modules

    @property
    def max_results(self) -> int:
        return max(_int_or_none(self._config.get("max_results")) or 30, 1)

    @property
    def index_url(self) -> str:
        configured = str(self._config.get("index_url", GO_PROXY_INDEX_URL)).strip()
        return configured or GO_PROXY_INDEX_URL

    @property
    def proxy_base_url(self) -> str:
        configured = str(self._config.get("proxy_base_url", GO_PROXY_BASE_URL)).strip()
        return (configured or GO_PROXY_BASE_URL).rstrip("/")

    @property
    def pkg_go_dev_base_url(self) -> str:
        configured = str(self._config.get("pkg_go_dev_base_url", PKG_GO_DEV_BASE)).strip()
        return (configured or PKG_GO_DEV_BASE).rstrip("/")

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen: set[str] = set()
        item_limit = max(limit, 0)
        if item_limit == 0:
            return signals

        async with httpx.AsyncClient(timeout=30) as client:
            for module_path in self.module_paths:
                if len(signals) >= item_limit:
                    break

                normalized = _string_or_none(module_path)
                if normalized is None:
                    continue

                data = await self._fetch_module_versions(client, module_path=normalized)
                if data is None:
                    continue

                for item in _extract_records(data, fallback_module_path=normalized):
                    if len(signals) >= item_limit:
                        break
                    signal = _record_to_signal(
                        item,
                        adapter_name=self.name,
                        proxy_base_url=self.proxy_base_url,
                        pkg_go_dev_base_url=self.pkg_go_dev_base_url,
                        lookup_type="module_list",
                    )
                    if signal is None:
                        logger.warning("%s: skipping malformed Go module record: %r", self.name, item)
                        continue
                    if signal.id in seen:
                        continue
                    seen.add(signal.id)
                    signals.append(signal)

            if len(signals) < item_limit:
                data = await self._fetch_index(client, limit=min(self.max_results, item_limit - len(signals)))
                if data is not None:
                    for item in _extract_records(data, fallback_module_path=None):
                        if len(signals) >= item_limit:
                            break
                        signal = _record_to_signal(
                            item,
                            adapter_name=self.name,
                            proxy_base_url=self.proxy_base_url,
                            pkg_go_dev_base_url=self.pkg_go_dev_base_url,
                            lookup_type="index",
                        )
                        if signal is None:
                            logger.warning("%s: skipping malformed Go module record: %r", self.name, item)
                            continue
                        if signal.id in seen:
                            continue
                        seen.add(signal.id)
                        signals.append(signal)

        return signals[:item_limit]

    async def _fetch_index(self, client: httpx.AsyncClient, *, limit: int) -> dict | list | str | None:
        params: dict[str, object] = {"limit": limit}
        since = _string_or_none(self._config.get("since"))
        if since:
            params["since"] = since

        try:
            response = await fetch_with_retry(
                self.index_url,
                client,
                adapter_name=self.name,
                params=params,
                headers=_DEFAULT_HEADERS,
            )
            return _response_payload(response)
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch Go module index: %s", self.name, e)
        except (httpx.RequestError, httpx.TimeoutException, ValueError) as e:
            logger.warning("%s: failed to parse Go module index: %s", self.name, e)
        return None

    async def _fetch_module_versions(
        self,
        client: httpx.AsyncClient,
        *,
        module_path: str,
    ) -> dict | list | str | None:
        url = f"{self.proxy_base_url}/{_escape_module_path(module_path)}/@v/list"
        try:
            response = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                headers=_DEFAULT_HEADERS,
            )
            return _response_payload(response)
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch Go module version list for '%s': %s", self.name, module_path, e)
        except (httpx.RequestError, httpx.TimeoutException, ValueError) as e:
            logger.warning("%s: failed to parse Go module version list for '%s': %s", self.name, module_path, e)
        return None


def _response_payload(response: httpx.Response) -> dict | list | str:
    content_type = response.headers.get("content-type", "")
    if "json" in content_type:
        try:
            payload = response.json()
            if isinstance(payload, (dict, list)):
                return payload
            return str(payload)
        except ValueError:
            return response.text
    try:
        payload = response.json()
        if isinstance(payload, (dict, list)):
            return payload
    except ValueError:
        pass
    return response.text


def _extract_records(
    payload: dict | list | str,
    *,
    fallback_module_path: str | None,
) -> list[dict]:
    if isinstance(payload, list):
        return [_normalize_record(item, fallback_module_path=fallback_module_path) for item in payload]

    if isinstance(payload, dict):
        for key in ("items", "results", "records", "modules", "versions"):
            value = payload.get(key)
            if isinstance(value, list):
                return [_normalize_record(item, fallback_module_path=fallback_module_path) for item in value]
        return [_normalize_record(payload, fallback_module_path=fallback_module_path)]

    records: list[dict] = []
    for line in payload.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("{"):
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                records.append({"raw": line})
                continue
            records.append(_normalize_record(parsed, fallback_module_path=fallback_module_path))
            continue
        records.append(_normalize_record(line, fallback_module_path=fallback_module_path))
    return records


def _normalize_record(item: object, *, fallback_module_path: str | None) -> dict:
    if isinstance(item, dict):
        record = dict(item)
        if fallback_module_path:
            record.setdefault("Path", fallback_module_path)
            record.setdefault("module_path", fallback_module_path)
        return record
    if isinstance(item, str):
        return {"Path": fallback_module_path, "Version": item}
    return {"Path": fallback_module_path}


def _record_to_signal(
    record: dict,
    *,
    adapter_name: str,
    proxy_base_url: str,
    pkg_go_dev_base_url: str,
    lookup_type: str,
) -> Signal | None:
    module_path = _module_path(record)
    version = _version(record)
    if not module_path or not version:
        return None

    timestamp = _parse_datetime(
        record.get("Timestamp")
        or record.get("timestamp")
        or record.get("time")
        or record.get("published_at")
        or record.get("publishedAt")
    )
    module_url = _module_url(record, module_path, version, pkg_go_dev_base_url=pkg_go_dev_base_url)
    proxy_url = _proxy_info_url(module_path, version, proxy_base_url=proxy_base_url)
    title = f"{module_path}@{version}"
    timestamp_text = timestamp.isoformat() if timestamp else None

    metadata = {
        "signal_role": "solution",
        "signal_kind": "module_version_activity",
        "package_ecosystem": "go",
        "registry": "go_proxy",
        "module_path": module_path,
        "package_name": module_path,
        "version": version,
        "timestamp": timestamp_text,
        "module_url": module_url,
        "source_url": module_url,
        "proxy_url": proxy_url,
        "lookup_type": lookup_type,
    }

    content = f"Go module proxy activity for {title}."
    if timestamp_text:
        content = f"Go module proxy activity recorded {title} at {timestamp_text}."

    return Signal(
        id=_signal_id(module_path, version),
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=title,
        content=content,
        url=module_url,
        published_at=timestamp,
        tags=_build_tags(module_path),
        credibility=0.75 if timestamp else 0.6,
        metadata=metadata,
    )


def _module_path(record: dict) -> str | None:
    for key in ("Path", "path", "module_path", "modulePath", "module", "name"):
        value = _string_or_none(record.get(key))
        if value:
            return value.strip().strip("/")
    return None


def _version(record: dict) -> str | None:
    for key in ("Version", "version", "latest_version", "latestVersion"):
        value = _string_or_none(record.get(key))
        if value:
            return value.strip()
    return None


def _module_url(
    record: dict,
    module_path: str,
    version: str,
    *,
    pkg_go_dev_base_url: str,
) -> str:
    configured = _string_or_none(record.get("url")) or _string_or_none(record.get("module_url"))
    if configured:
        return configured
    return f"{pkg_go_dev_base_url}/{quote(module_path, safe='/')}@{quote(version, safe='')}"


def _proxy_info_url(module_path: str, version: str, *, proxy_base_url: str) -> str:
    return f"{proxy_base_url}/{_escape_module_path(module_path)}/@v/{quote(version, safe='')}.info"


def _escape_module_path(module_path: str) -> str:
    escaped = []
    for char in module_path:
        if "A" <= char <= "Z":
            escaped.append(f"!{char.lower()}")
        else:
            escaped.append(char)
    return quote("".join(escaped).strip("/"), safe="/!")


def _build_tags(module_path: str) -> list[str]:
    tags = ["go", "golang", "go-module", "module-activity"]
    host = module_path.split("/", 1)[0].lower()
    if host:
        tags.append(host)
    return tags[:10]


def _signal_id(module_path: str, version: str) -> str:
    raw = "\x1f".join([module_path.strip().lower(), version.strip()])
    digest = hashlib.sha1(raw.encode()).hexdigest()[:12]
    return f"go_module_trends:{digest}"


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _int_or_none(value: object) -> int | None:
    if isinstance(value, str):
        value = value.strip()
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return re.sub(r"\s+", " ", value).strip()
    return None
