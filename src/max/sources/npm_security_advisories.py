"""npm security advisories source adapter -- package ecosystem risk signals."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

NPM_SECURITY_ADVISORY_URL = "https://registry.npmjs.org/-/npm/v1/security/advisories"
NPM_ADVISORY_URL = "https://www.npmjs.com/advisories/{advisory_id}"

_DEFAULT_MAX_RESULTS = 30
_SEVERITY_RANKS = {
    "info": 0,
    "low": 1,
    "moderate": 2,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


class NpmSecurityAdvisoriesAdapter(SourceAdapter):
    """Fetch npm package security advisory metadata."""

    config_keys = ["package_names", "packages", "severities", "advisory_url", "max_results"]
    required_keys: list[str] = []
    description = "Fetches npm security advisories as package ecosystem risk signals."

    @property
    def name(self) -> str:
        return "npm_security_advisories"

    @property
    def source_type(self) -> str:
        return SignalSourceType.SECURITY.value

    @property
    def package_names(self) -> list[str]:
        return _dedupe_terms(
            _raw_string_list(self._config.get("package_names"))
            + _raw_string_list(self._config.get("packages"))
            + _raw_string_list(self._config.get("watchlist_terms"))
        )

    @property
    def severities(self) -> list[str]:
        return _normalize_severities(self._config.get("severities"))

    @property
    def advisory_url(self) -> str:
        configured = str(self._config.get("advisory_url", NPM_SECURITY_ADVISORY_URL)).strip()
        return configured or NPM_SECURITY_ADVISORY_URL

    @property
    def max_results(self) -> int:
        return _positive_int(self._config.get("max_results"), _DEFAULT_MAX_RESULTS)

    @property
    def timeout(self) -> float:
        value = self._config.get("timeout", 30)
        if isinstance(value, bool):
            return 30.0
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 30.0
        return parsed if parsed > 0 else 30.0

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        item_limit = max(min(limit, self.max_results), 0)
        if item_limit == 0:
            return []

        payload = await self._fetch_advisories()
        if payload is None:
            return []

        package_filter = set(self.package_names)
        severity_filter = set(self.severities)
        signals: list[Signal] = []
        seen_ids: set[str] = set()

        for advisory in _iter_advisories(payload):
            if len(signals) >= item_limit:
                break

            signal = _advisory_to_signal(
                advisory,
                adapter_name=self.name,
                feed_url=self.advisory_url,
                package_filter=package_filter,
                severity_filter=severity_filter,
            )
            if signal is None or signal.id in seen_ids:
                continue
            seen_ids.add(signal.id)
            signals.append(signal)

        return signals[:item_limit]

    async def _fetch_advisories(self) -> object | None:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await fetch_with_retry(
                    self.advisory_url,
                    client,
                    adapter_name=self.name,
                    max_retries=2,
                    backoff_base=0,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "max-npm-security-advisories-adapter/0.1",
                    },
                )
                return response.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch npm advisories: %s", self.name, e)
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning("%s: npm advisory request failed: %s", self.name, e)
        except ValueError as e:
            logger.warning("%s: failed to parse npm advisory payload: %s", self.name, e)
        return None


def _advisory_to_signal(
    advisory: dict[str, Any],
    *,
    adapter_name: str,
    feed_url: str,
    package_filter: set[str],
    severity_filter: set[str],
) -> Signal | None:
    advisory_id = _advisory_id(advisory)
    package_name = _package_name(advisory)
    severity = _normalize_severity(advisory.get("severity"))
    vulnerable_range = _clean(
        advisory.get("vulnerable_range")
        or advisory.get("vulnerable_versions")
        or advisory.get("range")
    )
    patched_versions = _clean(advisory.get("patched_versions") or advisory.get("patched"))

    if not advisory_id or not package_name or severity == "unknown" or not vulnerable_range:
        return None

    normalized_package = _normalize_package_name(package_name)
    if package_filter and normalized_package not in package_filter:
        return None
    if severity_filter and severity not in severity_filter:
        return None

    identifiers = _identifiers(advisory)
    cves = sorted({item for item in identifiers if item.startswith("CVE-")})
    cwes = sorted({item for item in identifiers if item.startswith("CWE-")})
    canonical_url = _canonical_url(advisory, advisory_id)
    title = _clean(advisory.get("title") or advisory.get("overview"))
    if not title:
        title = f"{package_name} npm advisory {advisory_id}"

    content = _content(
        package_name,
        severity=severity,
        title=title,
        vulnerable_range=vulnerable_range,
        patched_versions=patched_versions,
        cves=cves,
        cwes=cwes,
    )

    return Signal(
        id=f"npm-security-advisory:{advisory_id}",
        source_type=SignalSourceType.SECURITY,
        source_adapter=adapter_name,
        title=f"npm advisory {advisory_id} [{severity.upper()}]: {title}"[:240],
        content=content,
        url=canonical_url,
        published_at=_parse_datetime(
            advisory.get("created")
            or advisory.get("created_at")
            or advisory.get("published")
            or advisory.get("published_at")
        ),
        tags=_build_tags(package_name, severity=severity, cves=cves, cwes=cwes),
        credibility=_credibility(severity),
        metadata={
            "signal_role": "problem",
            "signal_kind": "security_advisory",
            "evidence_type": "dependency_risk",
            "package_ecosystem": "npm",
            "package_name": package_name,
            "npm_name": package_name,
            "severity": severity,
            "vulnerable_range": vulnerable_range,
            "patched_versions": patched_versions or None,
            "identifiers": identifiers,
            "cves": cves,
            "cwes": cwes,
            "advisory_id": advisory_id,
            "canonical_url": canonical_url,
            "source_url": canonical_url,
            "feed_url": feed_url,
            "recommendation": _clean(advisory.get("recommendation")) or None,
            "updated_at": _iso_or_none(
                _parse_datetime(advisory.get("updated") or advisory.get("updated_at"))
            ),
        },
    )


def _iter_advisories(payload: object) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("advisories", "objects", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            return [item for item in value.values() if isinstance(item, dict)]

    if _looks_like_advisory(payload):
        return [payload]
    return [item for item in payload.values() if isinstance(item, dict) and _looks_like_advisory(item)]


def _looks_like_advisory(value: dict[str, Any]) -> bool:
    return bool(_advisory_id(value) and _package_name(value))


def _advisory_id(advisory: dict[str, Any]) -> str:
    for key in ("id", "advisory_id", "ghsa_id", "url"):
        value = advisory.get(key)
        cleaned = _clean(value)
        if cleaned:
            if key == "url":
                return cleaned.rstrip("/").rsplit("/", 1)[-1]
            return cleaned
    return ""


def _package_name(advisory: dict[str, Any]) -> str:
    for key in ("module_name", "package_name", "name"):
        cleaned = _clean(advisory.get(key))
        if cleaned:
            return cleaned
    package = advisory.get("package")
    if isinstance(package, dict):
        return _clean(package.get("name"))
    return ""


def _identifiers(advisory: dict[str, Any]) -> list[str]:
    values: list[str] = []
    values.extend(_string_list(advisory.get("identifiers")))
    values.extend(_string_list(advisory.get("cves")))
    values.extend(_string_list(advisory.get("cve")))
    values.extend(_string_list(advisory.get("cwes")))
    values.extend(_string_list(advisory.get("cwe")))

    identifiers = advisory.get("identifiers")
    if isinstance(identifiers, list):
        for item in identifiers:
            if isinstance(item, dict):
                values.append(_clean(item.get("value") or item.get("id") or item.get("name")))

    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        for identifier in re.findall(r"\b(?:CVE-\d{4}-\d{4,}|CWE-\d+|GHSA-[a-z0-9-]+)\b", value, re.I):
            cleaned = identifier.upper()
            if cleaned not in seen:
                seen.add(cleaned)
                normalized.append(cleaned)
    return normalized


def _canonical_url(advisory: dict[str, Any], advisory_id: str) -> str:
    for key in ("url", "advisory_url", "html_url"):
        value = _clean(advisory.get(key))
        if value:
            return value
    return NPM_ADVISORY_URL.format(advisory_id=quote(advisory_id, safe=""))


def _content(
    package_name: str,
    *,
    severity: str,
    title: str,
    vulnerable_range: str,
    patched_versions: str,
    cves: list[str],
    cwes: list[str],
) -> str:
    details = (
        f"{package_name} has a {severity} npm security advisory: {title}. "
        f"Vulnerable range: {vulnerable_range}."
    )
    if patched_versions:
        details += f" Patched versions: {patched_versions}."
    if cves:
        details += f" CVEs: {', '.join(cves)}."
    if cwes:
        details += f" CWEs: {', '.join(cwes)}."
    return details[:2000]


def _build_tags(package_name: str, *, severity: str, cves: list[str], cwes: list[str]) -> list[str]:
    tags = ["security", "vulnerability", "npm", "javascript", "dependency-risk", severity]
    tags.extend(_package_parts(package_name))
    tags.extend(cve.lower() for cve in cves[:2])
    tags.extend(cwe.lower() for cwe in cwes[:2])

    deduped: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        normalized = tag.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped[:10]


def _credibility(severity: str) -> float:
    return {
        "critical": 0.92,
        "high": 0.86,
        "medium": 0.76,
        "moderate": 0.76,
        "low": 0.64,
        "info": 0.55,
    }.get(severity, 0.6)


def _positive_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(parsed, 0)


def _normalize_severities(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        severity = _normalize_severity(item)
        if severity == "unknown" or severity in seen:
            continue
        seen.add(severity)
        normalized.append(severity)
    return normalized


def _normalize_severity(value: object) -> str:
    if not isinstance(value, str):
        return "unknown"
    normalized = value.strip().lower()
    if normalized == "moderate":
        return "medium"
    return normalized if normalized in _SEVERITY_RANKS else "unknown"


def _dedupe_terms(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _normalize_package_name(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _raw_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _normalize_package_name(value: object) -> str:
    return str(value).strip().lower() if isinstance(value, str) else ""


def _package_parts(package: str) -> list[str]:
    return [part for part in re.split(r"[/@._-]+", package.lower()) if part]


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    strings: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            strings.append(item.strip())
        elif isinstance(item, dict):
            text = _clean(item.get("value") or item.get("id") or item.get("name"))
            if text:
                strings.append(text)
    return strings


def _clean(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
