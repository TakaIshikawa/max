"""Utilities for importing third-party MCP security findings."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from max.types.signal import Signal, SignalSourceType

SOURCE_ADAPTER = "mcp_security_import"

_SEVERITY_CREDIBILITY = {
    "critical": 0.95,
    "high": 0.85,
    "medium": 0.65,
    "moderate": 0.65,
    "low": 0.45,
    "info": 0.3,
    "informational": 0.3,
}


def signal_from_mcp_security_finding(finding: Any) -> Signal:
    """Validate an imported MCP scanner finding and convert it to a Signal."""
    raw = finding.model_dump() if hasattr(finding, "model_dump") else dict(finding)

    scanner = _required_text(raw, "scanner")
    server_name = _required_text(raw, "server_name")
    severity = _required_text(raw, "severity").lower()
    finding_type = _required_text(raw, "finding_type")
    title = _required_text(raw, "title")
    description = _required_text(raw, "description")
    evidence_url = _required_text(raw, "evidence_url")
    if not evidence_url.startswith(("http://", "https://")):
        raise ValueError("evidence_url must be an HTTP(S) URL")

    package_name = _optional_text(raw, "package_name")
    package_version = _optional_text(raw, "package_version")
    remediation = _optional_text(raw, "remediation")
    discovered_at = _parse_discovered_at(raw.get("discovered_at"))

    metadata = {
        "scanner": scanner,
        "server_name": server_name,
        "package_name": package_name,
        "package_version": package_version,
        "severity": severity,
        "finding_type": finding_type,
        "remediation": remediation,
        "evidence_url": evidence_url,
        "discovered_at": discovered_at.isoformat() if discovered_at else None,
        "signal_role": "problem",
    }

    return Signal(
        source_type=SignalSourceType.SECURITY,
        source_adapter=SOURCE_ADAPTER,
        title=title,
        content=description,
        url=evidence_url,
        published_at=discovered_at,
        tags=_build_tags(severity, finding_type),
        credibility=_SEVERITY_CREDIBILITY.get(severity, 0.5),
        metadata=metadata,
    )


def _required_text(raw: dict[str, Any], field: str) -> str:
    value = raw.get(field)
    if value is None:
        raise ValueError(f"missing required field: {field}")
    text = str(value).strip()
    if not text:
        raise ValueError(f"missing required field: {field}")
    return text


def _optional_text(raw: dict[str, Any], field: str) -> str | None:
    value = raw.get(field)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_discovered_at(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("discovered_at must be an ISO 8601 datetime") from exc


def _build_tags(severity: str, finding_type: str) -> list[str]:
    severity_tag = _slug(severity)
    finding_tag = _slug(finding_type)
    tags = [
        "security",
        "mcp",
        severity_tag,
        f"severity:{severity_tag}",
        finding_tag,
        f"finding:{finding_tag}",
    ]
    return [tag for index, tag in enumerate(tags) if tag and tag not in tags[:index]]


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
