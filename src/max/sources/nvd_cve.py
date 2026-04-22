"""NVD CVE source adapter — vulnerabilities from the NVD 2.0 CVE API."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

NVD_CVE_API = "https://services.nvd.nist.gov/rest/json/cves/2.0"
NVD_CVE_URL = "https://nvd.nist.gov/vuln/detail"

_DEFAULT_SEVERITIES = ["critical", "high"]
_DEFAULT_KEYWORDS: list[str] = []
_DEFAULT_CVSS_MIN: float | None = None
_DEFAULT_MAX_AGE_DAYS = 30
_DEFAULT_API_KEY_ENV = "NVD_API_KEY"
_MAX_RESULTS_PER_PAGE = 2000


class NvdCveAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "nvd_cve"

    @property
    def source_type(self) -> str:
        return SignalSourceType.SECURITY.value

    @property
    def keywords(self) -> list[str]:
        return list(self._config.get("keywords", _DEFAULT_KEYWORDS))

    @property
    def severities(self) -> list[str]:
        return list(self._config.get("severities", _DEFAULT_SEVERITIES))

    @property
    def cvss_min(self) -> float | None:
        value = self._config.get("cvss_min", _DEFAULT_CVSS_MIN)
        return float(value) if value is not None else None

    @property
    def max_age_days(self) -> int:
        return int(self._config.get("max_age_days", _DEFAULT_MAX_AGE_DAYS))

    @property
    def api_key_env(self) -> str:
        return str(self._config.get("api_key_env", _DEFAULT_API_KEY_ENV))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_ids: set[str] = set()

        keywords = self.keywords or [None]
        severities = self.severities or [None]
        per_query = min(
            max(limit // max(len(keywords) * len(severities), 1), 3),
            _MAX_RESULTS_PER_PAGE,
        )

        headers = {"Accept": "application/json"}
        api_key = os.environ.get(self.api_key_env)
        if api_key:
            headers["apiKey"] = api_key

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for keyword in keywords:
                for severity in severities:
                    if len(signals) >= limit:
                        break

                    params = _build_params(
                        keyword=keyword,
                        severity=severity,
                        max_age_days=self.max_age_days,
                        results_per_page=per_query,
                    )

                    try:
                        resp = await fetch_with_retry(
                            NVD_CVE_API,
                            client,
                            adapter_name=self.name,
                            params=params,
                        )
                    except AdapterFetchError:
                        logger.warning(
                            "Failed to fetch NVD CVEs for keyword=%s severity=%s",
                            keyword,
                            severity,
                            exc_info=True,
                        )
                        continue

                    try:
                        payload = resp.json()
                        vulnerabilities = payload["vulnerabilities"]
                        if not isinstance(vulnerabilities, list):
                            raise ValueError("vulnerabilities is not a list")
                    except (KeyError, TypeError, ValueError) as e:
                        logger.warning(
                            "%s: failed to parse JSON response for keyword=%s severity=%s: %s",
                            self.name,
                            keyword,
                            severity,
                            e,
                        )
                        continue

                    for item in vulnerabilities:
                        if len(signals) >= limit:
                            break

                        signal = _signal_from_vulnerability(
                            item,
                            adapter_name=self.name,
                            cvss_min=self.cvss_min,
                        )
                        if signal is None or signal.metadata["cve_id"] in seen_ids:
                            continue

                        seen_ids.add(signal.metadata["cve_id"])
                        signals.append(signal)

        return signals[:limit]


def _build_params(
    *,
    keyword: str | None,
    severity: str | None,
    max_age_days: int,
    results_per_page: int,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "resultsPerPage": results_per_page,
        "startIndex": 0,
    }

    if keyword:
        params["keywordSearch"] = keyword
    if severity:
        params["cvssV3Severity"] = severity.upper()

    if max_age_days > 0:
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=max_age_days)
        params["pubStartDate"] = _format_nvd_dt(start)
        params["pubEndDate"] = _format_nvd_dt(now)

    return params


def _signal_from_vulnerability(
    item: dict[str, Any],
    *,
    adapter_name: str,
    cvss_min: float | None,
) -> Signal | None:
    cve = item.get("cve")
    if not isinstance(cve, dict):
        return None

    cve_id = cve.get("id")
    if not cve_id:
        return None

    cvss_score, severity, cvss_vector = _extract_cvss(cve)
    if cvss_min is not None and (cvss_score is None or cvss_score < cvss_min):
        return None

    description = _extract_description(cve)
    cwes = _extract_cwes(cve)
    affected_products = _extract_affected_products(cve)
    score_for_credibility = cvss_score if cvss_score is not None else 5.0

    title_score = f" CVSS {cvss_score:.1f}" if cvss_score is not None else ""
    title = f"[{severity.upper()}]{title_score} {cve_id}: {description[:160]}"

    return Signal(
        source_type=SignalSourceType.SECURITY,
        source_adapter=adapter_name,
        title=title[:240],
        content=description[:500],
        url=f"{NVD_CVE_URL}/{cve_id}",
        published_at=_parse_dt(cve.get("published")),
        tags=_build_tags(cwes, severity, affected_products),
        credibility=min(score_for_credibility / 10.0, 1.0),
        metadata={
            "cve_id": cve_id,
            "severity": severity,
            "cvss_score": cvss_score,
            "cvss_vector": cvss_vector,
            "cwes": cwes,
            "affected_products": affected_products[:10],
            "source_identifier": cve.get("sourceIdentifier"),
            "last_modified": cve.get("lastModified"),
            "vuln_status": cve.get("vulnStatus"),
        },
    )


def _extract_description(cve: dict[str, Any]) -> str:
    descriptions = cve.get("descriptions", [])
    if not isinstance(descriptions, list):
        return ""

    for desc in descriptions:
        if desc.get("lang") == "en" and desc.get("value"):
            return str(desc["value"])
    for desc in descriptions:
        if desc.get("value"):
            return str(desc["value"])
    return ""


def _extract_cvss(cve: dict[str, Any]) -> tuple[float | None, str, str | None]:
    metrics = cve.get("metrics", {})
    if not isinstance(metrics, dict):
        return None, "unknown", None

    for metric_key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        metric_entries = metrics.get(metric_key, [])
        if not isinstance(metric_entries, list) or not metric_entries:
            continue

        primary = _select_primary_metric(metric_entries)
        cvss_data = primary.get("cvssData", {})
        if not isinstance(cvss_data, dict):
            continue

        score = cvss_data.get("baseScore")
        severity = cvss_data.get("baseSeverity") or primary.get("baseSeverity") or "unknown"
        vector = cvss_data.get("vectorString")

        try:
            parsed_score = float(score) if score is not None else None
        except (TypeError, ValueError):
            parsed_score = None

        return parsed_score, str(severity).lower(), str(vector) if vector else None

    return None, "unknown", None


def _select_primary_metric(metric_entries: list[dict[str, Any]]) -> dict[str, Any]:
    for entry in metric_entries:
        if entry.get("type") == "Primary":
            return entry
    return metric_entries[0]


def _extract_cwes(cve: dict[str, Any]) -> list[str]:
    cwes: list[str] = []
    for weakness in cve.get("weaknesses", []):
        for desc in weakness.get("description", []):
            value = desc.get("value")
            if value and value != "NVD-CWE-noinfo" and value not in cwes:
                cwes.append(str(value))
    return cwes


def _extract_affected_products(cve: dict[str, Any]) -> list[str]:
    products: list[str] = []
    for config in cve.get("configurations", []):
        for node in config.get("nodes", []):
            _collect_cpe_products(node, products)
    return products


def _collect_cpe_products(node: dict[str, Any], products: list[str]) -> None:
    for match in node.get("cpeMatch", []):
        if not match.get("vulnerable", True):
            continue

        product = _product_from_cpe(match.get("criteria", ""))
        if product and product not in products:
            products.append(product)

    for child in node.get("children", []):
        _collect_cpe_products(child, products)


def _product_from_cpe(cpe: str) -> str | None:
    parts = cpe.split(":")
    if len(parts) < 5 or parts[0] != "cpe" or parts[1] != "2.3":
        return None

    vendor = _clean_cpe_part(parts[3])
    product = _clean_cpe_part(parts[4])
    if not product or product in {"*", "-"}:
        return None
    if vendor and vendor not in {"*", "-"}:
        return f"{vendor}/{product}"
    return product


def _clean_cpe_part(value: str) -> str:
    return value.replace("\\:", ":").replace("_", " ")


def _build_tags(cwes: list[str], severity: str, affected_products: list[str]) -> list[str]:
    tags: set[str] = {"security", "cve"}
    if severity in {"critical", "high"}:
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

    return sorted(tags)[:10]


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_nvd_dt(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
