"""Security Advisories source adapter — CVEs from GitHub Advisory Database."""

from __future__ import annotations

import logging
import os
from datetime import datetime

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
ECOSYSTEMS = ["pip", "npm", "go"]
SEVERITIES = ["critical", "high"]


class SecurityAdvisoriesAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "security_advisories"

    @property
    def source_type(self) -> str:
        return SignalSourceType.SECURITY.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_ids: set[str] = set()
        per_query = max(limit // (len(ECOSYSTEMS) * len(SEVERITIES)), 3)

        headers = {"Accept": "application/vnd.github+json"}
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for ecosystem in ECOSYSTEMS:
                for severity in SEVERITIES:
                    if len(signals) >= limit:
                        break

                    try:
                        resp = await client.get(
                            f"{GITHUB_API}/advisories",
                            params={
                                "ecosystem": ecosystem,
                                "severity": severity,
                                "sort": "updated",
                                "direction": "desc",
                                "per_page": per_query,
                            },
                        )
                        resp.raise_for_status()
                        advisories = resp.json()
                    except Exception:
                        logger.warning(
                            "Failed to fetch advisories for %s/%s",
                            ecosystem,
                            severity,
                            exc_info=True,
                        )
                        continue

                for adv in advisories:
                    ghsa_id = adv.get("ghsa_id", "")
                    if ghsa_id in seen_ids:
                        continue
                    seen_ids.add(ghsa_id)

                    # Skip withdrawn advisories
                    if adv.get("withdrawn_at"):
                        continue

                    if len(signals) >= limit:
                        break

                    cvss_score = adv.get("cvss", {}).get("score") or 5.0
                    credibility = min(cvss_score / 10.0, 1.0)

                    cve_id = adv.get("cve_id")
                    severity = adv.get("severity", "unknown")
                    summary = adv.get("summary", "")
                    description = adv.get("description", "")

                    affected = _extract_affected(adv)
                    cwes = _extract_cwes(adv)

                    signals.append(
                        Signal(
                            source_type=SignalSourceType.SECURITY,
                            source_adapter=self.name,
                            title=f"[{severity.upper()}] {summary[:200]}",
                            content=(description or summary)[:500],
                            url=adv.get("html_url", f"https://github.com/advisories/{ghsa_id}"),
                            published_at=_parse_dt(adv.get("published_at")),
                            tags=_build_tags(ecosystem, cwes, severity),
                            credibility=credibility,
                            metadata={
                                "ghsa_id": ghsa_id,
                                "cve_id": cve_id,
                                "severity": severity,
                                "cvss_score": cvss_score,
                                "cvss_vector": adv.get("cvss", {}).get("vector_string"),
                                "ecosystem": ecosystem,
                                "affected_packages": affected[:10],
                                "cwes": cwes,
                            },
                        )
                    )

        return signals[:limit]


def _extract_affected(adv: dict) -> list[str]:
    """Extract affected package names from advisory vulnerabilities."""
    packages: list[str] = []
    for vuln in adv.get("vulnerabilities", []):
        pkg = vuln.get("package", {})
        pkg_name = pkg.get("name")
        if pkg_name:
            packages.append(pkg_name)
    return packages


def _extract_cwes(adv: dict) -> list[str]:
    """Extract CWE IDs from advisory."""
    return [cwe.get("cwe_id", "") for cwe in adv.get("cwes", []) if cwe.get("cwe_id")]


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _build_tags(ecosystem: str, cwes: list[str], severity: str) -> list[str]:
    """Build tags from ecosystem, CWEs, and severity."""
    tags: set[str] = {"security"}

    ecosystem_map = {"pip": "python", "npm": "javascript", "go": "go"}
    lang_tag = ecosystem_map.get(ecosystem)
    if lang_tag:
        tags.add(lang_tag)

    # Map common CWEs to readable tags
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
    for cwe_id in cwes:
        mapped = cwe_map.get(cwe_id)
        if mapped:
            tags.add(mapped)

    if severity in ("critical", "high"):
        tags.add(severity)

    return sorted(tags)[:10]
