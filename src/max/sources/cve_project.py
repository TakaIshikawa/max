"""CVEProject cvelist v5 source adapter."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urljoin

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

CVE_PROJECT_RECENT_URL = "https://cveawg.mitre.org/api/cve/recent"
CVE_RECORD_URL = "https://www.cve.org/CVERecord?id="

_DEFAULT_MAX_AGE_DAYS = 30


class CveProjectAdapter(SourceAdapter):
    """Fetch recent CVE JSON 5 records from the CVEProject cvelist feed."""

    config_keys = ["base_url", "recent_path", "keywords", "max_age_days", "include_rejected"]
    required_keys: list[str] = []
    description = "Fetches recent CVEProject cvelist v5 records as security signals."

    @property
    def name(self) -> str:
        return "cve_project"

    @property
    def source_type(self) -> str:
        return SignalSourceType.SECURITY.value

    @property
    def base_url(self) -> str:
        return str(self._config.get("base_url", CVE_PROJECT_RECENT_URL))

    @property
    def recent_path(self) -> str:
        return str(self._config.get("recent_path", ""))

    @property
    def keywords(self) -> list[str]:
        return self._configured_terms("keywords", [])

    @property
    def max_age_days(self) -> int:
        value = self._config.get("max_age_days", _DEFAULT_MAX_AGE_DAYS)
        if isinstance(value, bool):
            return _DEFAULT_MAX_AGE_DAYS
        try:
            return int(value)
        except (TypeError, ValueError):
            return _DEFAULT_MAX_AGE_DAYS

    @property
    def include_rejected(self) -> bool:
        return _parse_bool(self._config.get("include_rejected", False))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                response = await fetch_with_retry(
                    _feed_url(self.base_url, self.recent_path),
                    client,
                    adapter_name=self.name,
                    headers={"Accept": "application/json"},
                    params={"limit": limit},
                )
                payload = response.json()
        except AdapterFetchError:
            logger.warning("%s: failed to fetch CVEProject records", self.name, exc_info=True)
            return []
        except (httpx.RequestError, httpx.TimeoutException):
            logger.warning("%s: failed to fetch CVEProject records", self.name, exc_info=True)
            return []
        except ValueError:
            logger.warning("%s: failed to parse CVEProject JSON response", self.name, exc_info=True)
            return []

        return parse_cve_project_records(
            payload,
            adapter_name=self.name,
            keywords=self.keywords,
            max_age_days=self.max_age_days,
            include_rejected=self.include_rejected,
            limit=limit,
        )


def parse_cve_project_records(
    payload: Any,
    *,
    adapter_name: str = "cve_project",
    keywords: list[str] | None = None,
    max_age_days: int = _DEFAULT_MAX_AGE_DAYS,
    include_rejected: bool = False,
    limit: int = 30,
    now: datetime | None = None,
) -> list[Signal]:
    """Parse CVE JSON 5 records into deterministic security signals."""
    records = _extract_records(payload)
    cutoff = _age_cutoff(max_age_days, now=now)
    signals: list[Signal] = []
    seen_cves: set[str] = set()

    for record in records:
        if len(signals) >= limit:
            break
        if not isinstance(record, dict):
            continue

        signal = _signal_from_record(
            record,
            adapter_name=adapter_name,
            cutoff=cutoff,
            keywords=keywords or [],
            include_rejected=include_rejected,
        )
        if signal is None:
            continue

        cve_id = signal.metadata["cve_id"]
        if cve_id in seen_cves:
            continue
        seen_cves.add(cve_id)
        signals.append(signal)

    return signals


def _signal_from_record(
    record: dict[str, Any],
    *,
    adapter_name: str,
    cutoff: datetime | None,
    keywords: list[str],
    include_rejected: bool,
) -> Signal | None:
    metadata = record.get("cveMetadata")
    if not isinstance(metadata, dict):
        return None

    cve_id = _clean(metadata.get("cveId") or metadata.get("cveID") or metadata.get("id"))
    if not cve_id:
        return None

    state = _clean(metadata.get("state")).upper()
    if state == "REJECTED" and not include_rejected:
        return None

    containers = record.get("containers")
    if not isinstance(containers, dict):
        containers = {}
    cna = containers.get("cna")
    if not isinstance(cna, dict):
        cna = {}
    adp_containers = containers.get("adp")
    if not isinstance(adp_containers, list):
        adp_containers = []

    published_at = _parse_dt(metadata.get("datePublished") or metadata.get("dateReserved"))
    updated_at = _parse_dt(
        metadata.get("dateUpdated")
        or cna.get("dateUpdated")
        or _nested(cna, "providerMetadata", "dateUpdated")
    )
    activity_at = updated_at or published_at
    if cutoff is not None and (activity_at is None or activity_at < cutoff):
        return None

    description = _extract_description(cna)
    if not description and state == "REJECTED":
        description = _extract_rejected_reason(cna)
    title_subject = _clean(cna.get("title")) or description or cve_id

    cvss_score, severity, cvss_vector, cvss_version = _extract_cvss(cna, adp_containers)
    cwes = _extract_cwes(cna)
    affected_products = _extract_affected_products(cna)
    references = _extract_references(cna)

    if keywords and not _matches_any(
        " ".join([cve_id, title_subject, description, " ".join(affected_products), " ".join(cwes)]),
        keywords,
    ):
        return None

    score_for_credibility = cvss_score if cvss_score is not None else 5.0
    title_score = f" CVSS {cvss_score:.1f}" if cvss_score is not None else ""
    severity_label = severity.upper() if severity != "unknown" else state or "CVE"

    return Signal(
        id=f"{adapter_name}:{cve_id}",
        source_type=SignalSourceType.SECURITY,
        source_adapter=adapter_name,
        title=f"[{severity_label}]{title_score} {cve_id}: {title_subject}"[:240],
        content=(description or title_subject)[:700],
        url=f"{CVE_RECORD_URL}{cve_id}",
        published_at=published_at,
        tags=_build_tags(cve_id, state, severity, cwes, affected_products),
        credibility=min(score_for_credibility / 10.0, 1.0),
        metadata={
            "cve_id": cve_id,
            "state": state,
            "severity": severity,
            "cvss_score": cvss_score,
            "cvss_vector": cvss_vector,
            "cvss_version": cvss_version,
            "cwes": cwes,
            "affected_products": affected_products[:10],
            "references": references[:10],
            "assigner_short_name": _clean(metadata.get("assignerShortName")),
            "date_updated": updated_at.isoformat() if updated_at else "",
            "source_catalog": "cve_project",
            "signal_role": "problem",
        },
    )


def _extract_records(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("cveMetadata"), dict):
        return [payload]

    for key in ("records", "cves", "vulnerabilities", "items", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return value

    return []


def _extract_description(cna: dict[str, Any]) -> str:
    descriptions = cna.get("descriptions")
    if not isinstance(descriptions, list):
        return ""

    for desc in descriptions:
        if isinstance(desc, dict) and desc.get("lang") == "en" and desc.get("value"):
            return str(desc["value"])
    for desc in descriptions:
        if isinstance(desc, dict) and desc.get("value"):
            return str(desc["value"])
    return ""


def _extract_rejected_reason(cna: dict[str, Any]) -> str:
    reasons = cna.get("rejectedReasons")
    if not isinstance(reasons, list):
        return ""
    for reason in reasons:
        if isinstance(reason, dict) and reason.get("value"):
            return str(reason["value"])
    return ""


def _extract_cvss(
    cna: dict[str, Any],
    adp_containers: list[Any],
) -> tuple[float | None, str, str | None, str | None]:
    for container in [cna, *[item for item in adp_containers if isinstance(item, dict)]]:
        metrics = container.get("metrics")
        if not isinstance(metrics, list):
            continue
        for metric in metrics:
            if not isinstance(metric, dict):
                continue
            parsed = _metric_cvss(metric)
            if parsed[0] is not None:
                return parsed
    return None, "unknown", None, None


def _metric_cvss(metric: dict[str, Any]) -> tuple[float | None, str, str | None, str | None]:
    for key in ("cvssV4_0", "cvssV3_1", "cvssV3_0", "cvssV2_0"):
        cvss_data = metric.get(key)
        if not isinstance(cvss_data, dict):
            continue

        score = cvss_data.get("baseScore")
        try:
            parsed_score = float(score) if score is not None else None
        except (TypeError, ValueError):
            parsed_score = None

        severity = (
            cvss_data.get("baseSeverity")
            or cvss_data.get("severity")
            or _severity_from_score(parsed_score)
        )
        vector = cvss_data.get("vectorString")
        version = cvss_data.get("version") or key.removeprefix("cvssV").replace("_", ".")

        return (
            parsed_score,
            str(severity).lower() if severity else "unknown",
            str(vector) if vector else None,
            str(version) if version else None,
        )

    return None, "unknown", None, None


def _severity_from_score(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score >= 9.0:
        return "critical"
    if score >= 7.0:
        return "high"
    if score >= 4.0:
        return "medium"
    if score > 0:
        return "low"
    return "none"


def _extract_cwes(cna: dict[str, Any]) -> list[str]:
    cwes: list[str] = []
    problem_types = cna.get("problemTypes")
    if not isinstance(problem_types, list):
        return cwes

    for problem_type in problem_types:
        if not isinstance(problem_type, dict):
            continue
        descriptions = problem_type.get("descriptions")
        if not isinstance(descriptions, list):
            continue
        for desc in descriptions:
            if not isinstance(desc, dict):
                continue
            value = _clean(desc.get("cweId") or desc.get("description"))
            if value.startswith("CWE-") and value not in cwes:
                cwes.append(value)
    return cwes


def _extract_affected_products(cna: dict[str, Any]) -> list[str]:
    products: list[str] = []
    affected = cna.get("affected")
    if not isinstance(affected, list):
        return products

    for item in affected:
        if not isinstance(item, dict):
            continue
        vendor = _clean(item.get("vendor"))
        product = _clean(item.get("product"))
        if not product or product in {"n/a", "N/A", "-"}:
            continue
        value = f"{vendor}/{product}" if vendor and vendor not in {"n/a", "N/A", "-"} else product
        if value not in products:
            products.append(value)
    return products


def _extract_references(cna: dict[str, Any]) -> list[str]:
    references: list[str] = []
    refs = cna.get("references")
    if not isinstance(refs, list):
        return references

    for ref in refs:
        if not isinstance(ref, dict):
            continue
        url = _clean(ref.get("url"))
        if url and url not in references:
            references.append(url)
    return references


def _build_tags(
    cve_id: str,
    state: str,
    severity: str,
    cwes: list[str],
    affected_products: list[str],
) -> list[str]:
    tags: set[str] = {"security", "cve", "cve-project"}
    if state:
        tags.add(state.lower())
    if severity in {"critical", "high", "medium", "low"}:
        tags.add(severity)

    cwe_map = {
        "CWE-79": "xss",
        "CWE-89": "sql-injection",
        "CWE-94": "code-injection",
        "CWE-200": "info-exposure",
        "CWE-287": "auth-bypass",
        "CWE-352": "csrf",
        "CWE-502": "deserialization",
        "CWE-918": "ssrf",
    }
    for cwe in cwes:
        tags.add(cwe.lower())
        mapped = cwe_map.get(cwe)
        if mapped:
            tags.add(mapped)

    for product in affected_products[:3]:
        normalized = product.split("/")[-1].lower().replace(" ", "-")
        if normalized and normalized not in {"*", "-"}:
            tags.add(normalized)

    year = cve_id.split("-")[1] if cve_id.count("-") >= 2 else ""
    if year.isdigit():
        tags.add(f"cve-{year}")

    return sorted(tags)[:10]


def _age_cutoff(max_age_days: int, *, now: datetime | None = None) -> datetime | None:
    if max_age_days <= 0:
        return None
    reference = now or datetime.now(timezone.utc)
    return reference.astimezone(timezone.utc) - timedelta(days=max_age_days)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _feed_url(base_url: str, recent_path: str) -> str:
    if not recent_path:
        return base_url
    return urljoin(base_url.rstrip("/") + "/", recent_path.lstrip("/"))


def _matches_any(text: str, needles: list[str]) -> bool:
    haystack = text.lower()
    return any(needle.lower() in haystack for needle in needles)


def _nested(mapping: dict[str, Any], *keys: str) -> Any:
    value: Any = mapping
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _clean(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "known", "published"}
    return bool(value)
