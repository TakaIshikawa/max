"""OSV.dev vulnerability source adapter."""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

OSV_QUERY_API = "https://api.osv.dev/v1/query"
OSV_QUERY_BATCH_API = "https://api.osv.dev/v1/querybatch"
OSV_VULN_URL = "https://osv.dev/vulnerability/{vuln_id}"

_DEFAULT_ECOSYSTEMS = ["PyPI", "npm", "Go"]
_DEFAULT_MODIFIED_SINCE_DAYS = 30
_DEFAULT_MAX_ITEMS = 30
_SEVERITY_RANKS = {
    "unknown": 0,
    "low": 1,
    "medium": 2,
    "moderate": 2,
    "high": 3,
    "critical": 4,
}


class OsvVulnerabilitiesAdapter(SourceAdapter):
    """Fetch package and ecosystem vulnerability records from OSV.dev."""

    config_keys = [
        "ecosystems",
        "packages",
        "queries",
        "severity_min",
        "modified_since_days",
        "max_items",
    ]
    required_keys: list[str] = []
    description = "Fetches OSV.dev package vulnerability signals by package or ecosystem."

    @property
    def name(self) -> str:
        return "osv_vulnerabilities"

    @property
    def source_type(self) -> str:
        return SignalSourceType.SECURITY.value

    @property
    def ecosystems(self) -> list[str]:
        return _string_list(self._config.get("ecosystems"), default=_DEFAULT_ECOSYSTEMS)

    @property
    def packages(self) -> list[dict[str, str]]:
        return _package_queries(self._config.get("packages"), self.ecosystems)

    @property
    def queries(self) -> list[str]:
        return self._configured_terms("queries", [])

    @property
    def severity_min(self) -> str | None:
        value = self._config.get("severity_min")
        if not isinstance(value, str) or not value.strip():
            return None
        normalized = value.strip().lower()
        return normalized if normalized in _SEVERITY_RANKS else None

    @property
    def modified_since_days(self) -> int:
        return _positive_int(self._config.get("modified_since_days"), _DEFAULT_MODIFIED_SINCE_DAYS)

    @property
    def max_items(self) -> int:
        return _positive_int(self._config.get("max_items"), _DEFAULT_MAX_ITEMS)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        item_limit = max(min(limit, self.max_items), 0)
        if item_limit == 0:
            return []

        cutoff = _modified_cutoff(self.modified_since_days)
        signals: list[Signal] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(timeout=30, headers={"Accept": "application/json"}) as client:
            package_queries = self._build_package_queries()
            if package_queries:
                payload = await self._fetch_package_vulnerabilities(client, package_queries)
                self._append_vulns(
                    payload,
                    signals=signals,
                    seen_ids=seen_ids,
                    cutoff=cutoff,
                    limit=item_limit,
                )

            if len(signals) < item_limit:
                for ecosystem in self.ecosystems:
                    if len(signals) >= item_limit:
                        break
                    payload = await self._fetch_ecosystem_vulnerabilities(client, ecosystem)
                    self._append_vulns(
                        payload,
                        signals=signals,
                        seen_ids=seen_ids,
                        cutoff=cutoff,
                        limit=item_limit,
                    )

        return signals[:item_limit]

    def _build_package_queries(self) -> list[dict[str, Any]]:
        package_queries = list(self.packages)

        for query in self.queries:
            for ecosystem in self.ecosystems:
                package_queries.append({"package": {"name": query, "ecosystem": ecosystem}})

        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for query in package_queries:
            package = query.get("package")
            if not isinstance(package, dict):
                continue
            name = str(package.get("name", "")).strip()
            ecosystem = str(package.get("ecosystem", "")).strip()
            if not name or not ecosystem:
                continue
            key = (ecosystem.lower(), name.lower())
            if key in seen:
                continue
            seen.add(key)
            deduped.append({"package": {"name": name, "ecosystem": ecosystem}})

        return deduped

    async def _fetch_package_vulnerabilities(
        self,
        client: httpx.AsyncClient,
        queries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        try:
            response = await fetch_with_retry(
                OSV_QUERY_BATCH_API,
                client,
                adapter_name=self.name,
                method="POST",
                json={"queries": queries},
                headers={"Content-Type": "application/json"},
            )
            payload = response.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch OSV package vulnerabilities: %s", self.name, e)
            return []
        except (httpx.RequestError, httpx.TimeoutException, ValueError) as e:
            logger.warning("%s: failed to fetch or parse OSV package vulnerabilities: %s", self.name, e)
            return []

        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            return []

        vulns: list[dict[str, Any]] = []
        for result in results:
            result_vulns = result.get("vulns") if isinstance(result, dict) else None
            if isinstance(result_vulns, list):
                vulns.extend(v for v in result_vulns if isinstance(v, dict))
        return vulns

    async def _fetch_ecosystem_vulnerabilities(
        self,
        client: httpx.AsyncClient,
        ecosystem: str,
    ) -> list[dict[str, Any]]:
        try:
            response = await fetch_with_retry(
                OSV_QUERY_API,
                client,
                adapter_name=self.name,
                method="POST",
                json={"package": {"ecosystem": ecosystem}},
                headers={"Content-Type": "application/json"},
            )
            payload = response.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch OSV ecosystem vulnerabilities for %s: %s", self.name, ecosystem, e)
            return []
        except (httpx.RequestError, httpx.TimeoutException, ValueError) as e:
            logger.warning("%s: failed to fetch or parse OSV ecosystem vulnerabilities for %s: %s", self.name, ecosystem, e)
            return []

        vulns = payload.get("vulns") if isinstance(payload, dict) else None
        return [vuln for vuln in vulns if isinstance(vuln, dict)] if isinstance(vulns, list) else []

    def _append_vulns(
        self,
        vulns: list[dict[str, Any]],
        *,
        signals: list[Signal],
        seen_ids: set[str],
        cutoff: datetime | None,
        limit: int,
    ) -> None:
        for vuln in vulns:
            if len(signals) >= limit:
                break
            signal = _signal_from_vuln(
                vuln,
                adapter_name=self.name,
                severity_min=self.severity_min,
                cutoff=cutoff,
            )
            if signal is None:
                continue
            vuln_id = signal.metadata["osv_id"]
            if vuln_id in seen_ids:
                continue
            seen_ids.add(vuln_id)
            signals.append(signal)


def _signal_from_vuln(
    vuln: dict[str, Any],
    *,
    adapter_name: str,
    severity_min: str | None,
    cutoff: datetime | None,
) -> Signal | None:
    vuln_id = _clean(vuln.get("id"))
    if not vuln_id:
        return None

    modified_at = _parse_dt(vuln.get("modified"))
    if cutoff is not None and (modified_at is None or modified_at < cutoff):
        return None

    severity = _extract_severity(vuln)
    if severity_min and _SEVERITY_RANKS[severity] < _SEVERITY_RANKS[severity_min]:
        return None

    affected_packages = _extract_affected_packages(vuln)
    ecosystems = sorted({pkg["ecosystem"] for pkg in affected_packages if pkg.get("ecosystem")})
    package_names = sorted({pkg["name"] for pkg in affected_packages if pkg.get("name")})
    aliases = _string_list(vuln.get("aliases"))
    summary = _clean(vuln.get("summary")) or _clean(vuln.get("details")) or vuln_id
    details = _clean(vuln.get("details")) or summary

    return Signal(
        id=f"{adapter_name}:{vuln_id}",
        source_type=SignalSourceType.SECURITY,
        source_adapter=adapter_name,
        title=f"OSV {vuln_id} [{severity.upper()}]: {summary}"[:240],
        content=details[:700],
        url=_advisory_url(vuln),
        published_at=_parse_dt(vuln.get("published")),
        tags=_build_tags(vuln_id, severity, ecosystems, package_names, aliases),
        credibility=_credibility(severity),
        metadata={
            "signal_role": "problem",
            "osv_id": vuln_id,
            "aliases": aliases,
            "severity": severity,
            "severity_source": _severity_source(vuln),
            "ecosystems": ecosystems,
            "packages": package_names,
            "affected_packages": affected_packages[:20],
            "published": vuln.get("published"),
            "modified": vuln.get("modified"),
            "modified_at": modified_at.isoformat() if modified_at else None,
            "advisory_url": _advisory_url(vuln),
            "source_catalog": "osv",
        },
    )


def _extract_affected_packages(vuln: dict[str, Any]) -> list[dict[str, str]]:
    affected: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for entry in vuln.get("affected", []):
        if not isinstance(entry, dict):
            continue
        package = entry.get("package")
        if not isinstance(package, dict):
            continue
        name = _clean(package.get("name"))
        ecosystem = _clean(package.get("ecosystem"))
        if not name and not ecosystem:
            continue
        key = (ecosystem.lower(), name.lower())
        if key in seen:
            continue
        seen.add(key)
        affected.append({"name": name, "ecosystem": ecosystem})
    return affected


def _extract_severity(vuln: dict[str, Any]) -> str:
    database_specific = vuln.get("database_specific")
    if isinstance(database_specific, dict):
        severity = _normalize_severity(database_specific.get("severity"))
        if severity != "unknown":
            return severity

    severities = vuln.get("severity")
    if isinstance(severities, list):
        for item in severities:
            if not isinstance(item, dict):
                continue
            severity = _severity_from_cvss(_clean(item.get("score")))
            if severity != "unknown":
                return severity

    return "unknown"


def _severity_source(vuln: dict[str, Any]) -> str | None:
    database_specific = vuln.get("database_specific")
    if isinstance(database_specific, dict) and database_specific.get("severity"):
        return "database_specific"
    if vuln.get("severity"):
        return "severity"
    return None


def _severity_from_cvss(value: str) -> str:
    match = re.search(r"/AV:", value)
    if match:
        score = _cvss_base_score(value)
        if score is not None:
            return _severity_from_score(score)
    return _normalize_severity(value)


def _cvss_base_score(vector: str) -> float | None:
    score_match = re.search(r"(?:^|/)BS:([0-9.]+)(?:/|$)", vector)
    if score_match:
        try:
            return float(score_match.group(1))
        except ValueError:
            return None

    metrics = _cvss_metrics(vector)
    if not metrics:
        return None

    try:
        av = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2}[metrics["AV"]]
        ac = {"L": 0.77, "H": 0.44}[metrics["AC"]]
        scope_changed = metrics["S"] == "C"
        if scope_changed:
            pr = {"N": 0.85, "L": 0.68, "H": 0.5}[metrics["PR"]]
        else:
            pr = {"N": 0.85, "L": 0.62, "H": 0.27}[metrics["PR"]]
        ui = {"N": 0.85, "R": 0.62}[metrics["UI"]]
        confidentiality = {"H": 0.56, "L": 0.22, "N": 0.0}[metrics["C"]]
        integrity = {"H": 0.56, "L": 0.22, "N": 0.0}[metrics["I"]]
        availability = {"H": 0.56, "L": 0.22, "N": 0.0}[metrics["A"]]
    except KeyError:
        return None

    impact_sub_score = 1 - ((1 - confidentiality) * (1 - integrity) * (1 - availability))
    if scope_changed:
        impact = (
            7.52 * (impact_sub_score - 0.029)
            - 3.25 * ((impact_sub_score - 0.02) ** 15)
        )
    else:
        impact = 6.42 * impact_sub_score

    if impact <= 0:
        return 0.0

    exploitability = 8.22 * av * ac * pr * ui
    if scope_changed:
        return min(_round_up_1_decimal(1.08 * (impact + exploitability)), 10.0)
    return min(_round_up_1_decimal(impact + exploitability), 10.0)


def _cvss_metrics(vector: str) -> dict[str, str]:
    metrics: dict[str, str] = {}
    for part in vector.split("/"):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        metrics[key] = value
    required = {"AV", "AC", "PR", "UI", "S", "C", "I", "A"}
    return metrics if required.issubset(metrics) else {}


def _round_up_1_decimal(value: float) -> float:
    return math.ceil(value * 10) / 10


def _severity_from_score(score: float) -> str:
    if score >= 9.0:
        return "critical"
    if score >= 7.0:
        return "high"
    if score >= 4.0:
        return "medium"
    if score > 0:
        return "low"
    return "unknown"


def _normalize_severity(value: object) -> str:
    if not isinstance(value, str):
        return "unknown"
    normalized = value.strip().lower()
    if normalized == "moderate":
        return "medium"
    return normalized if normalized in _SEVERITY_RANKS else "unknown"


def _build_tags(
    vuln_id: str,
    severity: str,
    ecosystems: list[str],
    package_names: list[str],
    aliases: list[str],
) -> list[str]:
    tags: list[str] = ["security", "vulnerability", "osv", vuln_id.lower()]
    if severity in {"critical", "high", "medium", "low"}:
        tags.append(severity)
    tags.extend(_slug(ecosystem) for ecosystem in ecosystems)
    tags.extend(_slug(package) for package in package_names[:4])
    tags.extend(alias.lower() for alias in aliases[:3] if alias.startswith("CVE-"))

    deduped: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if not tag or tag in seen:
            continue
        seen.add(tag)
        deduped.append(tag)
    return deduped[:10]


def _advisory_url(vuln: dict[str, Any]) -> str:
    vuln_id = _clean(vuln.get("id"))
    references = vuln.get("references")
    if isinstance(references, list):
        for ref in references:
            if isinstance(ref, dict) and _clean(ref.get("type")).upper() in {"ADVISORY", "WEB"}:
                url = _clean(ref.get("url"))
                if url:
                    return url
    return OSV_VULN_URL.format(vuln_id=vuln_id)


def _credibility(severity: str) -> float:
    return {
        "critical": 0.92,
        "high": 0.85,
        "medium": 0.75,
        "low": 0.65,
    }.get(severity, 0.6)


def _package_queries(value: object, ecosystems: list[str]) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    queries: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, str):
            name = item.strip()
            if name:
                for ecosystem in ecosystems:
                    queries.append({"package": {"name": name, "ecosystem": ecosystem}})
            continue
        if isinstance(item, dict):
            name = _clean(item.get("name") or item.get("package"))
            ecosystem = _clean(item.get("ecosystem"))
            if name and ecosystem:
                queries.append({"package": {"name": name, "ecosystem": ecosystem}})
    return queries


def _modified_cutoff(modified_since_days: int) -> datetime | None:
    if modified_since_days <= 0:
        return None
    return datetime.now(timezone.utc) - timedelta(days=modified_since_days)


def _positive_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(parsed, 0)


def _string_list(value: object, default: list[str] | None = None) -> list[str]:
    values = default if value is None else value
    if not isinstance(values, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def _clean(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
