"""AgentSeal MCP security scan source adapter."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.sources.errors import SourceParseError
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

_DEFAULT_MAX_ITEMS = 100
_SEVERITY_ORDER = {
    "info": 0,
    "informational": 0,
    "low": 1,
    "medium": 2,
    "moderate": 2,
    "high": 3,
    "critical": 4,
}
_SEVERITY_CREDIBILITY = {
    "critical": 0.95,
    "high": 0.85,
    "medium": 0.65,
    "moderate": 0.65,
    "low": 0.45,
    "info": 0.3,
    "informational": 0.3,
}
_CONTAINER_KEYS = (
    "findings",
    "results",
    "items",
    "vulnerabilities",
    "scans",
    "data",
)
_SERVER_KEYS = ("server_name", "server", "mcp_server", "name")
_PACKAGE_KEYS = ("package", "package_name", "packageName", "module", "artifact")
_FINDING_ID_KEYS = ("finding_id", "findingId", "id", "rule_id", "ruleId", "check_id", "checkId")
_SEVERITY_KEYS = ("severity", "level", "risk")
_CATEGORY_KEYS = ("category", "finding_type", "type", "rule_category", "class")
_SUMMARY_KEYS = ("summary", "title", "description", "message")
_EVIDENCE_KEYS = ("evidence", "details", "proof", "observed", "snippet")
_REMEDIATION_KEYS = ("remediation", "recommendation", "fix", "mitigation", "solution")
_URL_KEYS = ("url", "finding_url", "evidence_url", "source_url", "link")
_DATE_KEYS = ("discovered_at", "published_at", "created_at", "scanned_at", "date")
_REMEDIATED_KEYS = ("remediated", "is_remediated", "fixed", "resolved")
_STATUS_KEYS = ("status", "state", "resolution")


class AgentSealMcpScanAdapter(SourceAdapter):
    """Read AgentSeal-style MCP server security scan exports as signals."""

    config_keys = [
        "local_paths",
        "report_urls",
        "severity_min",
        "categories",
        "max_items",
        "include_remediated",
    ]
    required_keys: list[str] = []
    description = (
        "Reads AgentSeal-style MCP server security scan JSON and JSONL exports "
        "as vulnerability, trust, and remediation signals."
    )

    @property
    def name(self) -> str:
        return "agentseal_mcp_scan"

    @property
    def source_type(self) -> str:
        return SignalSourceType.SECURITY.value

    @property
    def local_paths(self) -> list[str]:
        return _string_list(self._config.get("local_paths"))

    @property
    def report_urls(self) -> list[str]:
        return _string_list(self._config.get("report_urls"))

    @property
    def severity_min(self) -> str:
        value = self._config.get("severity_min", "info")
        if not isinstance(value, str):
            return "info"
        normalized = value.strip().lower()
        return normalized if normalized in _SEVERITY_ORDER else "info"

    @property
    def categories(self) -> list[str]:
        return _string_list(self._config.get("categories"))

    @property
    def max_items(self) -> int:
        value = self._config.get("max_items", _DEFAULT_MAX_ITEMS)
        if isinstance(value, bool):
            return _DEFAULT_MAX_ITEMS
        try:
            return max(int(value), 1)
        except (TypeError, ValueError):
            return _DEFAULT_MAX_ITEMS

    @property
    def include_remediated(self) -> bool:
        return _bool_value(self._config.get("include_remediated"), default=True)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        item_limit = min(limit, self.max_items)
        signals: list[Signal] = []
        seen: set[str] = set()

        for local_path in self.local_paths:
            if len(signals) >= item_limit:
                break
            text = self._read_local_path(local_path)
            self._append_signals(
                signals,
                text,
                source_label=local_path,
                source_url=_file_url(local_path),
                limit=item_limit,
                seen=seen,
            )

        if len(signals) < item_limit and self.report_urls:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                for report_url in self.report_urls:
                    if len(signals) >= item_limit:
                        break
                    text = await self._fetch_report_url(report_url, client)
                    if text is None:
                        continue
                    self._append_signals(
                        signals,
                        text,
                        source_label=report_url,
                        source_url=report_url,
                        limit=item_limit,
                        seen=seen,
                    )

        return signals[:item_limit]

    def _read_local_path(self, local_path: str) -> str:
        try:
            return Path(local_path).read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise SourceParseError(
                f"Unable to read AgentSeal MCP scan export: {local_path}",
                adapter_name=self.name,
            ) from exc

    async def _fetch_report_url(self, report_url: str, client: httpx.AsyncClient) -> str | None:
        try:
            response = await fetch_with_retry(report_url, client, adapter_name=self.name)
        except AdapterFetchError as exc:
            logger.warning("%s: failed to fetch report URL %s: %s", self.name, report_url, exc)
            return None
        except Exception as exc:
            logger.warning("%s: failed to fetch report URL %s: %s", self.name, report_url, exc)
            return None
        return response.text

    def _append_signals(
        self,
        signals: list[Signal],
        text: str,
        *,
        source_label: str,
        source_url: str,
        limit: int,
        seen: set[str],
    ) -> None:
        for item in _parse_export_items(text, source_label=source_label):
            if len(signals) >= limit:
                break
            signal = _signal_from_item(
                item,
                adapter_name=self.name,
                source_url=source_url,
                severity_min=self.severity_min,
                category_filters=self.categories,
                include_remediated=self.include_remediated,
            )
            if signal is None or signal.id in seen:
                continue
            seen.add(signal.id)
            signals.append(signal)


def _parse_export_items(text: str, *, source_label: str) -> list[dict[str, Any]]:
    stripped = text.strip()
    if not stripped:
        return []
    if _looks_like_jsonl(source_label, stripped):
        return _parse_jsonl(stripped, source_label)
    try:
        return _extract_items(json.loads(stripped))
    except json.JSONDecodeError:
        return _parse_jsonl(stripped, source_label)


def _looks_like_jsonl(source_label: str, stripped_text: str) -> bool:
    suffix = Path(urlparse(source_label).path or source_label).suffix.lower()
    return suffix == ".jsonl" and not stripped_text.startswith("[")


def _parse_jsonl(text: str, source_label: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise SourceParseError(
                f"Malformed AgentSeal MCP scan JSONL at {source_label}:{line_number}",
                adapter_name="agentseal_mcp_scan",
            ) from exc
        if isinstance(payload, dict):
            items.extend(_extract_items(payload))
    return items


def _extract_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []

    for key in _CONTAINER_KEYS:
        value = data.get(key)
        if isinstance(value, list):
            return [_merge_parent_context(data, item) for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _extract_items(value)
            if nested:
                return [_merge_parent_context(data, item) for item in nested]

    return [data]


def _merge_parent_context(parent: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    merged = dict(item)
    for keys in (_SERVER_KEYS, _PACKAGE_KEYS):
        for key in keys:
            if key in parent and key not in merged:
                merged[key] = parent[key]
    return merged


def _signal_from_item(
    item: dict[str, Any],
    *,
    adapter_name: str,
    source_url: str,
    severity_min: str,
    category_filters: list[str],
    include_remediated: bool,
) -> Signal | None:
    severity = (_first_text(item, _SEVERITY_KEYS) or "info").lower()
    if severity not in _SEVERITY_ORDER:
        severity = "info"
    if _SEVERITY_ORDER[severity] < _SEVERITY_ORDER[severity_min]:
        return None

    category = _first_text(item, _CATEGORY_KEYS) or "uncategorized"
    if category_filters and _slug(category) not in {_slug(value) for value in category_filters}:
        return None

    remediated = _is_remediated(item)
    if remediated and not include_remediated:
        return None

    server_name = _first_text(item, _SERVER_KEYS) or "unknown-mcp-server"
    package = _first_text(item, _PACKAGE_KEYS)
    finding_id = _first_text(item, _FINDING_ID_KEYS)
    summary = _first_text(item, _SUMMARY_KEYS) or f"{category} finding reported by AgentSeal"
    evidence = _field_value(item, _EVIDENCE_KEYS)
    remediation = _first_text(item, _REMEDIATION_KEYS)
    finding_url = _first_text(item, _URL_KEYS) or source_url
    published_at = _parse_datetime(_first_text(item, _DATE_KEYS))

    title = f"AgentSeal MCP {severity} finding: {server_name} - {summary}"
    content_parts = [summary]
    evidence_text = _stringify(evidence)
    if evidence_text:
        content_parts.append(f"Evidence: {evidence_text}")
    if remediation:
        content_parts.append(f"Remediation: {remediation}")
    content = " ".join(content_parts)

    metadata = {
        "scanner": "agentseal",
        "server_name": server_name,
        "package": package,
        "finding_id": finding_id,
        "severity": severity,
        "category": category,
        "summary": summary,
        "evidence": evidence,
        "remediation": remediation,
        "url": finding_url,
        "remediated": remediated,
        "raw_status": _first_text(item, _STATUS_KEYS),
        "signal_role": "problem",
    }

    return Signal(
        id=_signal_id(adapter_name, server_name, package, finding_id, category, summary),
        source_type=SignalSourceType.SECURITY,
        source_adapter=adapter_name,
        title=title[:240],
        content=content[:700],
        url=finding_url,
        published_at=published_at,
        tags=_build_tags(severity, category),
        credibility=_SEVERITY_CREDIBILITY.get(severity, 0.5),
        metadata=metadata,
    )


def _signal_id(
    adapter_name: str,
    server_name: str,
    package: str | None,
    finding_id: str | None,
    category: str,
    summary: str,
) -> str:
    stable_ref = finding_id or _hash_ref(server_name, package, category, summary)
    return f"{adapter_name}:{_slug(server_name)}:{_slug(stable_ref)}"


def _hash_ref(server_name: str, package: str | None, category: str, summary: str) -> str:
    raw = "\n".join([server_name, package or "", category, summary])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _build_tags(severity: str, category: str) -> list[str]:
    category_tag = _slug(category)
    severity_tag = _slug(severity)
    tags = [
        "security",
        "mcp",
        "mcp-security",
        "agentseal",
        severity_tag,
        f"severity:{severity_tag}",
        category_tag,
        f"category:{category_tag}",
    ]
    return [tag for index, tag in enumerate(tags) if tag and tag not in tags[:index]]


def _first_text(item: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    value = _field_value(item, keys)
    if value is None:
        return None
    text = _stringify(value)
    return text or None


def _field_value(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return None


def _stringify(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True)
    return str(value).strip() or None


def _is_remediated(item: dict[str, Any]) -> bool:
    value = _field_value(item, _REMEDIATED_KEYS)
    if value is not None:
        return _bool_value(value, default=False)
    status = (_first_text(item, _STATUS_KEYS) or "").lower()
    return status in {"remediated", "resolved", "fixed", "closed", "mitigated"}


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        return []
    result: list[str] = []
    for item in values:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if text and text not in result:
            result.append(text)
    return result


def _bool_value(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _file_url(path: str) -> str:
    try:
        return Path(path).resolve().as_uri()
    except ValueError:
        return path


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
