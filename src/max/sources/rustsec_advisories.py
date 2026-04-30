"""RustSec advisory source adapter."""

from __future__ import annotations

import json
import logging
import re
import tomllib
import zipfile
from datetime import datetime
from io import BytesIO
from typing import Any

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

RUSTSEC_OSV_ARCHIVE_URL = "https://codeload.github.com/RustSec/advisory-db/zip/refs/heads/osv"
RUSTSEC_ADVISORY_URL = "https://rustsec.org/advisories/{advisory_id}"

_DEFAULT_MAX_ITEMS = 30
_SEVERITY_RANKS = {
    "unknown": 0,
    "info": 0,
    "low": 1,
    "medium": 2,
    "moderate": 2,
    "high": 3,
    "critical": 4,
}


class RustSecAdvisoriesAdapter(SourceAdapter):
    """Fetch RustSec crate security advisory records."""

    config_keys = ["index_url", "base_url", "packages", "severity_min", "max_items"]
    required_keys: list[str] = []
    description = "Fetches RustSec advisory database records for vulnerable Rust crates."

    @property
    def name(self) -> str:
        return "rustsec_advisories"

    @property
    def source_type(self) -> str:
        return SignalSourceType.SECURITY.value

    @property
    def index_url(self) -> str:
        return str(self._config.get("index_url") or RUSTSEC_OSV_ARCHIVE_URL)

    @property
    def base_url(self) -> str:
        return str(self._config.get("base_url") or "https://rustsec.org/advisories")

    @property
    def packages(self) -> list[str]:
        return _string_list(self._config.get("packages"), default=[])

    @property
    def severity_min(self) -> str | None:
        value = self._config.get("severity_min")
        if not isinstance(value, str) or not value.strip():
            return None
        severity = value.strip().lower()
        return severity if severity in _SEVERITY_RANKS else None

    @property
    def max_items(self) -> int:
        return _positive_int(self._config.get("max_items"), _DEFAULT_MAX_ITEMS)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        item_limit = max(min(limit, self.max_items), 0)
        if item_limit == 0:
            return []

        try:
            async with httpx.AsyncClient(timeout=30, headers={"Accept": "application/json"}) as client:
                response = await fetch_with_retry(
                    self.index_url,
                    client,
                    adapter_name=self.name,
                )
        except (AdapterFetchError, httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning("%s: failed to fetch RustSec advisories: %s", self.name, e)
            return []

        records = _records_from_response(response)
        signals = parse_rustsec_advisories(
            records,
            adapter_name=self.name,
            base_url=self.base_url,
            packages=self.packages,
            severity_min=self.severity_min,
            limit=item_limit,
        )
        return signals[:item_limit]


def parse_rustsec_advisories(
    records: list[dict[str, Any]],
    *,
    adapter_name: str = "rustsec_advisories",
    base_url: str = "https://rustsec.org/advisories",
    packages: list[str] | None = None,
    severity_min: str | None = None,
    limit: int = 30,
) -> list[Signal]:
    """Convert RustSec OSV/TOML records into signals."""
    package_filter = {package.lower() for package in (packages or [])}
    signals: list[Signal] = []
    seen_ids: set[str] = set()

    for record in records:
        if len(signals) >= limit:
            break

        try:
            signal = _signal_from_record(record, adapter_name=adapter_name, base_url=base_url)
        except (TypeError, ValueError) as e:
            logger.warning("%s: skipping malformed RustSec advisory record: %s", adapter_name, e)
            continue

        if signal is None:
            continue
        rustsec_id = signal.metadata["rustsec_id"]
        if rustsec_id in seen_ids:
            continue
        seen_ids.add(rustsec_id)

        affected_crate = str(signal.metadata.get("affected_crate") or "").lower()
        if package_filter and affected_crate not in package_filter:
            continue

        severity = str(signal.metadata.get("severity") or "unknown").lower()
        if severity_min and _SEVERITY_RANKS[severity] < _SEVERITY_RANKS[severity_min]:
            continue

        signals.append(signal)

    return signals[:limit]


def _records_from_response(response: httpx.Response) -> list[dict[str, Any]]:
    try:
        payload = response.json()
    except (ValueError, TypeError):
        payload = None

    if payload is not None:
        return _records_from_json_payload(payload)

    content = getattr(response, "content", b"") or b""
    if not isinstance(content, bytes):
        return []

    try:
        return _records_from_zip(content)
    except zipfile.BadZipFile as e:
        logger.warning("rustsec_advisories: failed to parse advisory archive: %s", e)
        return []


def _records_from_json_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("advisories", "vulns", "vulnerabilities"):
        records = payload.get(key)
        if isinstance(records, list):
            return [item for item in records if isinstance(item, dict)]

    if payload.get("id") or payload.get("advisory"):
        return [payload]
    return []


def _records_from_zip(content: bytes) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with zipfile.ZipFile(BytesIO(content)) as archive:
        for name in sorted(archive.namelist()):
            if name.endswith("/"):
                continue
            suffix = name.rsplit(".", 1)[-1].lower()
            if suffix not in {"json", "toml", "md"}:
                continue

            raw = archive.read(name).decode("utf-8")
            try:
                if suffix == "json":
                    payload = json.loads(raw)
                    if isinstance(payload, dict):
                        records.append(payload)
                else:
                    records.append(_toml_record_from_text(raw))
            except (json.JSONDecodeError, tomllib.TOMLDecodeError, ValueError) as e:
                logger.warning("rustsec_advisories: skipping malformed advisory %s: %s", name, e)
    return records


def _toml_record_from_text(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```toml"):
        _, _, rest = stripped.partition("\n")
        toml_text, separator, _ = rest.partition("```")
        if not separator:
            raise ValueError("missing TOML front matter terminator")
        return tomllib.loads(toml_text)

    marker = stripped.find("[advisory]")
    if marker < 0:
        raise ValueError("missing advisory table")

    candidate = stripped[marker:]
    lines = candidate.splitlines()
    for end in range(len(lines), 0, -1):
        try:
            return tomllib.loads("\n".join(lines[:end]))
        except tomllib.TOMLDecodeError:
            continue
    raise ValueError("invalid TOML advisory")


def _signal_from_record(
    record: dict[str, Any],
    *,
    adapter_name: str,
    base_url: str,
) -> Signal | None:
    if "advisory" in record:
        return _signal_from_toml_record(record, adapter_name=adapter_name, base_url=base_url)
    return _signal_from_osv_record(record, adapter_name=adapter_name, base_url=base_url)


def _signal_from_osv_record(
    record: dict[str, Any],
    *,
    adapter_name: str,
    base_url: str,
) -> Signal | None:
    rustsec_id = _clean(record.get("id"))
    if not rustsec_id:
        raise ValueError("missing id")
    if record.get("withdrawn"):
        return None

    affected_crate = _affected_crate_from_osv(record)
    if not affected_crate:
        raise ValueError(f"{rustsec_id}: missing affected crate")

    severity = _extract_severity(record)
    patched_versions = _patched_versions_from_osv(record)
    aliases = _string_list(record.get("aliases"), default=[])
    summary = _clean(record.get("summary")) or f"RustSec advisory for {affected_crate}"
    details = _clean(record.get("details")) or summary
    advisory_url = _advisory_url(record, rustsec_id=rustsec_id, base_url=base_url)

    return Signal(
        id=f"{adapter_name}:{rustsec_id}",
        source_type=SignalSourceType.SECURITY,
        source_adapter=adapter_name,
        title=f"RustSec {rustsec_id} [{severity.upper()}]: {summary}"[:240],
        content=_content(details, affected_crate=affected_crate, patched_versions=patched_versions),
        url=advisory_url,
        published_at=_parse_dt(record.get("published")),
        tags=_build_tags(severity, affected_crate, aliases, record.get("database_specific")),
        credibility=_credibility(severity),
        metadata={
            "signal_role": "problem",
            "rustsec_id": rustsec_id,
            "advisory_id": rustsec_id,
            "affected_crate": affected_crate,
            "patched_versions": patched_versions,
            "severity": severity,
            "aliases": aliases,
            "cve_ids": [alias for alias in aliases if alias.startswith("CVE-")],
            "advisory_url": advisory_url,
            "published": record.get("published"),
            "modified": record.get("modified"),
            "database_specific": record.get("database_specific") or {},
            "source_catalog": "rustsec",
        },
    )


def _signal_from_toml_record(
    record: dict[str, Any],
    *,
    adapter_name: str,
    base_url: str,
) -> Signal | None:
    advisory = record.get("advisory")
    if not isinstance(advisory, dict):
        raise ValueError("missing advisory table")
    if advisory.get("withdrawn"):
        return None

    rustsec_id = _clean(advisory.get("id"))
    affected_crate = _clean(advisory.get("package"))
    if not rustsec_id:
        raise ValueError("missing advisory id")
    if not affected_crate:
        raise ValueError(f"{rustsec_id}: missing affected crate")

    versions = record.get("versions") if isinstance(record.get("versions"), dict) else {}
    patched_versions = _string_list(versions.get("patched") if versions else None, default=[])
    aliases = _string_list(advisory.get("aliases"), default=[])
    severity = _severity_from_cvss(_clean(advisory.get("cvss"))) or "info"
    advisory_url = _clean(advisory.get("url")) or _rustsec_url(rustsec_id, base_url)
    summary = _clean(advisory.get("title")) or f"RustSec advisory for {affected_crate}"
    details = _clean(advisory.get("description")) or summary

    return Signal(
        id=f"{adapter_name}:{rustsec_id}",
        source_type=SignalSourceType.SECURITY,
        source_adapter=adapter_name,
        title=f"RustSec {rustsec_id} [{severity.upper()}]: {summary}"[:240],
        content=_content(details, affected_crate=affected_crate, patched_versions=patched_versions),
        url=advisory_url,
        published_at=_parse_dt(advisory.get("date")),
        tags=_build_tags(severity, affected_crate, aliases, advisory),
        credibility=_credibility(severity),
        metadata={
            "signal_role": "problem",
            "rustsec_id": rustsec_id,
            "advisory_id": rustsec_id,
            "affected_crate": affected_crate,
            "patched_versions": patched_versions,
            "severity": severity,
            "aliases": aliases,
            "cve_ids": [alias for alias in aliases if alias.startswith("CVE-")],
            "advisory_url": advisory_url,
            "published": advisory.get("date"),
            "modified": None,
            "database_specific": {
                "categories": _string_list(advisory.get("categories"), default=[]),
                "keywords": _string_list(advisory.get("keywords"), default=[]),
                "informational": advisory.get("informational"),
            },
            "source_catalog": "rustsec",
        },
    )


def _affected_crate_from_osv(record: dict[str, Any]) -> str:
    for item in record.get("affected", []):
        if not isinstance(item, dict):
            continue
        package = item.get("package")
        if not isinstance(package, dict):
            continue
        if _clean(package.get("ecosystem")).lower() in {"crates.io", "cargo", ""}:
            name = _clean(package.get("name"))
            if name:
                return name
    return ""


def _patched_versions_from_osv(record: dict[str, Any]) -> list[str]:
    versions: list[str] = []
    for item in record.get("affected", []):
        if not isinstance(item, dict):
            continue
        for range_item in item.get("ranges", []):
            if not isinstance(range_item, dict):
                continue
            for event in range_item.get("events", []):
                if not isinstance(event, dict):
                    continue
                fixed = _clean(event.get("fixed"))
                if fixed and fixed not in versions:
                    versions.append(f">= {fixed}")
    return versions


def _extract_severity(record: dict[str, Any]) -> str:
    database_specific = record.get("database_specific")
    if isinstance(database_specific, dict):
        severity = _clean(database_specific.get("severity")).lower()
        if severity in _SEVERITY_RANKS:
            return "medium" if severity == "moderate" else severity
        if _clean(database_specific.get("informational")):
            return "info"

    for item in record.get("severity", []):
        if not isinstance(item, dict):
            continue
        severity = _severity_from_cvss(_clean(item.get("score")))
        if severity:
            return severity

    return "unknown"


def _severity_from_cvss(score: str) -> str | None:
    if not score:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", score)
    if match and not score.startswith("CVSS:"):
        value = float(match.group(1))
        if value >= 9:
            return "critical"
        if value >= 7:
            return "high"
        if value >= 4:
            return "medium"
        return "low"

    if "/C:H" in score and "/I:H" in score and "/A:H" in score:
        return "critical"
    if "/C:H" in score or "/I:H" in score or "/A:H" in score:
        return "high"
    if "/C:L" in score or "/I:L" in score or "/A:L" in score:
        return "medium"
    return None


def _advisory_url(record: dict[str, Any], *, rustsec_id: str, base_url: str) -> str:
    for reference in record.get("references", []):
        if not isinstance(reference, dict):
            continue
        url = _clean(reference.get("url"))
        if url and ("rustsec.org" in url or reference.get("type") == "ADVISORY"):
            return url
    return _rustsec_url(rustsec_id, base_url)


def _rustsec_url(rustsec_id: str, base_url: str) -> str:
    return f"{base_url.rstrip('/')}/{rustsec_id}"


def _content(details: str, *, affected_crate: str, patched_versions: list[str]) -> str:
    lines = [details[:650], f"Affected crate: {affected_crate}"]
    if patched_versions:
        lines.append(f"Patched versions: {', '.join(patched_versions)}")
    return "\n".join(line for line in lines if line)[:900]


def _build_tags(
    severity: str,
    affected_crate: str,
    aliases: list[str],
    extra: Any,
) -> list[str]:
    tags: set[str] = {"security", "rust", "rustsec", _slug(affected_crate)}
    if severity in {"critical", "high", "medium", "low"}:
        tags.add(severity)
    if any(alias.startswith("CVE-") for alias in aliases):
        tags.add("cve")

    if isinstance(extra, dict):
        for value in _string_list(extra.get("categories"), default=[]):
            tags.add(_slug(value))
        for value in _string_list(extra.get("keywords"), default=[]):
            tags.add(_slug(value))
        informational = _clean(extra.get("informational"))
        if informational:
            tags.add(_slug(informational))

    return sorted(tag for tag in tags if tag)[:12]


def _credibility(severity: str) -> float:
    return {
        "critical": 0.95,
        "high": 0.9,
        "medium": 0.8,
        "low": 0.7,
        "info": 0.65,
    }.get(severity, 0.75)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _string_list(value: Any, *, default: list[str]) -> list[str]:
    if value is None:
        return list(default)
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        return list(default)

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = _clean(item)
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    return cleaned


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _clean(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:40]
