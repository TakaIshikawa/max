"""Snyk vulnerability issues import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

DEFAULT_SNYK_API_URL = "https://api.snyk.io"
MAX_PER_PAGE = 100


class SnykVulnerabilitiesImportAdapter(SourceAdapter):
    """Fetch current Snyk vulnerability issues and convert them to security signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        organization_id: str | None = None,
        token: str | None = None,
        api_url: str | None = None,
        project_ids: list[str] | str | None = None,
        severity: list[str] | str | None = None,
        status: list[str] | str | None = None,
        per_page: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.organization_id = _optional(organization_id or self._config.get("organization_id") or os.getenv("SNYK_ORGANIZATION_ID"))
        self.token = _optional(token or self._config.get("token") or os.getenv("SNYK_TOKEN"))
        self.api_url = (api_url or _optional(self._config.get("api_url")) or os.getenv("SNYK_API_URL") or DEFAULT_SNYK_API_URL).rstrip("/")
        self.project_ids = _strings(project_ids if project_ids is not None else self._config.get("project_ids"))
        self.severity = _strings(severity if severity is not None else self._config.get("severity"))
        self.status = _strings(status if status is not None else self._config.get("status"))
        self.per_page = _positive_int(per_page if per_page is not None else self._config.get("per_page"), default=50, maximum=MAX_PER_PAGE)
        self._client = client

    @property
    def name(self) -> str:
        return "snyk_vulnerabilities_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.SECURITY.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.organization_id and self.token):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            issues = await self._fetch_issues(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()
        return [_issue_signal(issue, adapter_name=self.name) for issue in issues[:limit] if isinstance(issue, dict)]

    async def _fetch_issues(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        page = 1
        while len(issues) < limit:
            page_size = min(self.per_page, limit - len(issues))
            try:
                response = await client.get(
                    f"{self.api_url}/v1/org/{self.organization_id}/issues",
                    headers=self._headers(),
                    params=self._params(page=page, per_page=page_size),
                )
                response.raise_for_status()
                body = response.json()
            except Exception:
                logger.warning("Snyk vulnerabilities fetch failed", exc_info=True)
                return []

            page_items = _issue_items(body)
            issues.extend(page_items)
            if len(page_items) < page_size:
                break
            page += 1
        return issues[:limit]

    def _headers(self) -> dict[str, str]:
        assert self.token is not None
        return {
            "Accept": "application/json",
            "Authorization": f"token {self.token}",
            "User-Agent": "max-snyk-vulnerabilities-import/1",
        }

    def _params(self, *, page: int, per_page: int) -> dict[str, Any]:
        params: dict[str, Any] = {"page": page, "perPage": per_page}
        if self.project_ids:
            params["projectId"] = self.project_ids
        if self.severity:
            params["severity"] = self.severity
        if self.status:
            params["status"] = self.status
        return params


SnykVulnerabilitiesAdapter = SnykVulnerabilitiesImportAdapter


def _issue_items(body: object) -> list[dict[str, Any]]:
    if isinstance(body, list):
        return [item for item in body if isinstance(item, dict)]
    if not isinstance(body, dict):
        return []
    for key in ("issues", "data", "results"):
        value = body.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _issue_signal(issue: dict[str, Any], *, adapter_name: str) -> Signal:
    issue_data = _dict(issue.get("issue"))
    pkg = _dict(issue.get("pkg") or issue.get("package"))
    project = _dict(issue.get("project"))
    identifiers = _dict(issue_data.get("identifiers") or issue.get("identifiers"))
    title = _text(issue_data.get("title") or issue.get("title") or issue.get("id") or issue_data.get("id"))
    severity = _text(issue_data.get("severity") or issue.get("severity")).lower()
    package_name = _text(pkg.get("name") or issue.get("packageName"))
    project_name = _text(project.get("name") or issue.get("projectName"))
    issue_id = _text(issue_data.get("id") or issue.get("id"))
    status = _text(issue.get("status") or issue_data.get("status")).lower()
    url = _text(issue.get("url") or issue.get("issueUrl") or issue_data.get("url"))
    cvss_score = _number(issue_data.get("cvssScore") or issue.get("cvssScore"))
    exploit_maturity = _text(issue_data.get("exploitMaturity") or issue.get("exploitMaturity"))
    disclosure_date = _text(issue_data.get("disclosureTime") or issue_data.get("publicationTime") or issue.get("disclosureDate"))
    cves = _strings(identifiers.get("CVE"))
    cwes = _strings(identifiers.get("CWE"))
    content_bits = [title]
    if package_name:
        content_bits.append(f"package {package_name}")
    if project_name:
        content_bits.append(f"project {project_name}")
    if cvss_score is not None:
        content_bits.append(f"CVSS {cvss_score:g}")
    return Signal(
        source_type=SignalSourceType.SECURITY,
        source_adapter=adapter_name,
        title=title,
        content="; ".join(content_bits)[:1000],
        url=url,
        author=None,
        published_at=_parse_dt(disclosure_date),
        tags=sorted({"snyk", "vulnerability", severity, status, package_name, project_name, *cves[:3]} - {""})[:10],
        credibility=0.82,
        metadata={
            "signal_role": "security",
            "snyk_issue_id": issue_id,
            "title": title,
            "severity": severity or None,
            "package": package_name or None,
            "project": project_name or None,
            "project_id": project.get("id") or issue.get("projectId"),
            "issue_url": url or None,
            "identifiers": {"CVE": cves, "CWE": cwes},
            "cvss_score": cvss_score,
            "exploit_maturity": exploit_maturity or None,
            "disclosure_date": disclosure_date or None,
            "status": status or None,
            "is_patchable": issue.get("isPatchable"),
            "is_pinnable": issue.get("isPinnable"),
            "priority_score": issue.get("priorityScore") or issue_data.get("priorityScore"),
        },
    )


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _parse_dt(value: object) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _number(value: object) -> float | int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, int | float):
        return value
    try:
        return float(str(value))
    except ValueError:
        return None


def _positive_int(value: object, *, default: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number <= 0:
        return default
    return min(number, maximum)


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",")]
    if not isinstance(value, list | tuple | set):
        return []
    return [_text(item) for item in value if _text(item)]


def _optional(value: object) -> str | None:
    return _text(value) or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
