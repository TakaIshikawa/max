"""OpenAPI schema source adapter."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import httpx
import yaml

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

_HTTP_METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})
_DEFAULT_MAX_OPERATIONS_PER_SIGNAL = 25
_DEFAULT_REQUEST_TIMEOUT = 30.0


class OpenApiSpecsAdapter(SourceAdapter):
    """Reads OpenAPI 3.x documents as integration opportunity signals."""

    config_keys = [
        "urls",
        "local_paths",
        "max_operations_per_signal",
        "include_tags",
        "request_timeout",
    ]
    required_keys: list[str] = []
    description = "Reads local and remote OpenAPI 3.x schemas as integration opportunity signals."

    @property
    def name(self) -> str:
        return "openapi_specs"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def urls(self) -> list[str]:
        return _string_list(self._config.get("urls", []))

    @property
    def local_paths(self) -> list[str]:
        return _string_list(self._config.get("local_paths", []))

    @property
    def max_operations_per_signal(self) -> int:
        return max(_int_or_none(self._config.get("max_operations_per_signal")) or 25, 1)

    @property
    def include_tags(self) -> bool | set[str]:
        value = self._config.get("include_tags", True)
        if isinstance(value, str):
            normalized = value.strip()
            if normalized.lower() in {"0", "false", "no", "off"}:
                return False
            if normalized.lower() in {"1", "true", "yes", "on", "all"}:
                return True
            return {normalized}
        if isinstance(value, bool):
            return value
        if isinstance(value, (list, tuple, set)):
            return {item.strip() for item in value if isinstance(item, str) and item.strip()}
        return bool(value)

    @property
    def request_timeout(self) -> float:
        value = self._config.get("request_timeout", _DEFAULT_REQUEST_TIMEOUT)
        if isinstance(value, int | float):
            return max(float(value), 0.1)
        if isinstance(value, str):
            try:
                return max(float(value.strip()), 0.1)
            except ValueError:
                return _DEFAULT_REQUEST_TIMEOUT
        return _DEFAULT_REQUEST_TIMEOUT

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        effective_limit = max(limit, 1)
        documents: list[_LoadedDocument] = []

        for local_path in self.local_paths:
            loaded = self._load_local_document(local_path)
            if loaded is not None:
                documents.append(loaded)

        if self.urls:
            async with httpx.AsyncClient(timeout=self.request_timeout) as client:
                for url in self.urls:
                    loaded = await self._load_remote_document(client, url)
                    if loaded is not None:
                        documents.append(loaded)

        signals: list[Signal] = []
        seen: set[str] = set()
        for loaded in documents:
            for signal in _document_to_signals(
                loaded,
                adapter_name=self.name,
                max_operations_per_signal=self.max_operations_per_signal,
                include_tags=self.include_tags,
            ):
                if len(signals) >= effective_limit:
                    return signals
                if signal.id in seen:
                    continue
                seen.add(signal.id)
                signals.append(signal)

        return signals

    def _load_local_document(self, local_path: str) -> "_LoadedDocument | None":
        try:
            text = Path(local_path).read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("%s: failed to read OpenAPI schema %s: %s", self.name, local_path, exc)
            return None
        return _parse_document(text, source_label=local_path, source_kind="local_path", adapter_name=self.name)

    async def _load_remote_document(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> "_LoadedDocument | None":
        try:
            response = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                headers={"Accept": "application/json,application/yaml,text/yaml,*/*"},
            )
        except (AdapterFetchError, httpx.RequestError) as exc:
            logger.warning("%s: failed to fetch OpenAPI schema %s: %s", self.name, url, exc)
            return None
        return _parse_document(response.text, source_label=url, source_kind="url", adapter_name=self.name)


class _LoadedDocument(dict):
    pass


def _parse_document(
    text: str,
    *,
    source_label: str,
    source_kind: str,
    adapter_name: str,
) -> _LoadedDocument | None:
    try:
        if source_label.lower().endswith(".json"):
            data = json.loads(text)
        else:
            data = yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        logger.warning("%s: failed to parse OpenAPI schema %s: %s", adapter_name, source_label, exc)
        return None

    if not isinstance(data, dict):
        logger.warning("%s: OpenAPI schema %s was not an object", adapter_name, source_label)
        return None

    openapi_version = _string_or_none(data.get("openapi"))
    if openapi_version is None or not openapi_version.startswith("3."):
        logger.warning("%s: schema %s is not an OpenAPI 3.x document", adapter_name, source_label)
        return None

    loaded = _LoadedDocument(data)
    loaded["_max_source_label"] = source_label
    loaded["_max_source_kind"] = source_kind
    return loaded


def _document_to_signals(
    document: _LoadedDocument,
    *,
    adapter_name: str,
    max_operations_per_signal: int,
    include_tags: bool | set[str],
) -> list[Signal]:
    info = document.get("info") if isinstance(document.get("info"), dict) else {}
    title = _string_or_none(info.get("title")) or "Untitled API"
    version = _string_or_none(info.get("version"))
    description = _string_or_none(info.get("description")) or title
    source_label = str(document.get("_max_source_label") or "")
    source_kind = str(document.get("_max_source_kind") or "source")
    servers = _servers(document)
    auth_schemes = _auth_scheme_names(document)
    operations = _operations(document)
    tags = _tag_names(document, operations)

    signals = [
        _api_signal(
            adapter_name=adapter_name,
            title=title,
            version=version,
            description=description,
            openapi_version=str(document.get("openapi")),
            source_label=source_label,
            source_kind=source_kind,
            servers=servers,
            tags=tags,
            operations=operations,
            auth_schemes=auth_schemes,
            max_operations_per_signal=max_operations_per_signal,
        )
    ]

    if include_tags is False:
        return signals

    allowed_tags = include_tags if isinstance(include_tags, set) else None
    for tag in tags:
        if allowed_tags is not None and tag not in allowed_tags:
            continue
        tag_operations = [operation for operation in operations if tag in operation["tags"]]
        if not tag_operations:
            continue
        signals.append(
            _tag_signal(
                adapter_name=adapter_name,
                api_title=title,
                version=version,
                tag=tag,
                description=_tag_description(document, tag) or description,
                source_label=source_label,
                source_kind=source_kind,
                servers=servers,
                all_tags=tags,
                operations=tag_operations,
                total_operation_count=len(operations),
                auth_schemes=auth_schemes,
                max_operations_per_signal=max_operations_per_signal,
            )
        )

    return signals


def _api_signal(
    *,
    adapter_name: str,
    title: str,
    version: str | None,
    description: str,
    openapi_version: str,
    source_label: str,
    source_kind: str,
    servers: list[str],
    tags: list[str],
    operations: list[dict[str, Any]],
    auth_schemes: list[str],
    max_operations_per_signal: int,
) -> Signal:
    operation_count = len(operations)
    sampled_operations = operations[:max_operations_per_signal]
    metadata = _base_metadata(
        title=title,
        version=version,
        description=description,
        source_label=source_label,
        source_kind=source_kind,
        servers=servers,
        tags=tags,
        operation_count=operation_count,
        auth_schemes=auth_schemes,
        signal_kind="openapi_api",
    )
    metadata.update(
        {
            "openapi_version": openapi_version,
            "operations": sampled_operations,
            "max_operations_per_signal": max_operations_per_signal,
            "truncated_operations": operation_count > len(sampled_operations),
        }
    )
    return Signal(
        id=_signal_id(adapter_name, source_label, "api", title, version),
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=_format_title(title, version),
        content=_content(
            description=description,
            operation_count=operation_count,
            tags=tags,
            servers=servers,
            auth_schemes=auth_schemes,
        ),
        url=source_label,
        tags=_signal_tags(tags, auth_schemes),
        credibility=0.7,
        metadata=metadata,
    )


def _tag_signal(
    *,
    adapter_name: str,
    api_title: str,
    version: str | None,
    tag: str,
    description: str,
    source_label: str,
    source_kind: str,
    servers: list[str],
    all_tags: list[str],
    operations: list[dict[str, Any]],
    total_operation_count: int,
    auth_schemes: list[str],
    max_operations_per_signal: int,
) -> Signal:
    operation_count = len(operations)
    sampled_operations = operations[:max_operations_per_signal]
    metadata = _base_metadata(
        title=api_title,
        version=version,
        description=description,
        source_label=source_label,
        source_kind=source_kind,
        servers=servers,
        tags=all_tags,
        operation_count=operation_count,
        auth_schemes=auth_schemes,
        signal_kind="openapi_tag_group",
    )
    metadata.update(
        {
            "tag": tag,
            "total_operation_count": total_operation_count,
            "operations": sampled_operations,
            "max_operations_per_signal": max_operations_per_signal,
            "truncated_operations": operation_count > len(sampled_operations),
        }
    )
    return Signal(
        id=_signal_id(adapter_name, source_label, "tag", api_title, version, tag),
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=f"{api_title}: {tag} integration surface",
        content=_content(
            description=description,
            operation_count=operation_count,
            tags=[tag],
            servers=servers,
            auth_schemes=auth_schemes,
        ),
        url=source_label,
        tags=_signal_tags([tag], auth_schemes),
        credibility=0.65,
        metadata=metadata,
    )


def _base_metadata(
    *,
    title: str,
    version: str | None,
    description: str,
    source_label: str,
    source_kind: str,
    servers: list[str],
    tags: list[str],
    operation_count: int,
    auth_schemes: list[str],
    signal_kind: str,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "api_title": title,
        "version": version,
        "description": description,
        "server_urls": servers,
        "tags": tags,
        "operation_count": operation_count,
        "auth_schemes": auth_schemes,
        "source": source_label,
        "signal_kind": signal_kind,
        "signal_role": "solution",
    }
    if source_kind == "url":
        metadata["source_url"] = source_label
    else:
        metadata["source_path"] = source_label
    return metadata


def _operations(document: dict[str, Any]) -> list[dict[str, Any]]:
    paths = document.get("paths")
    if not isinstance(paths, dict):
        return []

    operations: list[dict[str, Any]] = []
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if not isinstance(method, str) or method.lower() not in _HTTP_METHODS:
                continue
            if not isinstance(operation, dict):
                continue
            operations.append(
                {
                    "method": method.upper(),
                    "path": path,
                    "operation_id": _string_or_none(operation.get("operationId")),
                    "summary": _string_or_none(operation.get("summary")),
                    "description": _string_or_none(operation.get("description")),
                    "tags": _string_list(operation.get("tags", [])),
                }
            )
    return operations


def _servers(document: dict[str, Any]) -> list[str]:
    servers = document.get("servers")
    if not isinstance(servers, list):
        return []
    values: list[str] = []
    for server in servers:
        if isinstance(server, dict):
            value = _string_or_none(server.get("url"))
            if value:
                values.append(value)
    return _dedupe(values)


def _auth_scheme_names(document: dict[str, Any]) -> list[str]:
    components = document.get("components")
    if not isinstance(components, dict):
        return []
    schemes = components.get("securitySchemes")
    if not isinstance(schemes, dict):
        return []
    return _dedupe([key for key in schemes if isinstance(key, str)])


def _tag_names(document: dict[str, Any], operations: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    declared = document.get("tags")
    if isinstance(declared, list):
        for tag in declared:
            if isinstance(tag, dict):
                name = _string_or_none(tag.get("name"))
                if name:
                    values.append(name)
            elif isinstance(tag, str) and tag.strip():
                values.append(tag.strip())
    for operation in operations:
        values.extend(operation["tags"])
    return _dedupe(values)


def _tag_description(document: dict[str, Any], tag_name: str) -> str | None:
    declared = document.get("tags")
    if not isinstance(declared, list):
        return None
    for tag in declared:
        if not isinstance(tag, dict):
            continue
        if _string_or_none(tag.get("name")) == tag_name:
            return _string_or_none(tag.get("description"))
    return None


def _content(
    *,
    description: str,
    operation_count: int,
    tags: list[str],
    servers: list[str],
    auth_schemes: list[str],
) -> str:
    parts = [description, f"Operations: {operation_count}."]
    if tags:
        parts.append(f"Tags: {', '.join(tags[:12])}.")
    if servers:
        parts.append(f"Servers: {', '.join(servers[:5])}.")
    if auth_schemes:
        parts.append(f"Auth schemes: {', '.join(auth_schemes)}.")
    return " ".join(parts)[:4000]


def _format_title(title: str, version: str | None) -> str:
    if version:
        return f"{title} OpenAPI ({version})"
    return f"{title} OpenAPI"


def _signal_tags(tags: list[str], auth_schemes: list[str]) -> list[str]:
    return _dedupe(["openapi", "api", *tags[:8], *auth_schemes[:4]])


def _signal_id(adapter_name: str, *parts: object) -> str:
    raw = "|".join(str(part or "") for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{adapter_name}:{digest}"


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, (list, tuple, set)):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
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


OpenApiSpecsAdapter = OpenApiSpecsAdapter
