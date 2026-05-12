"""Azure DevOps build timeline import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class AzureDevOpsBuildTimelineAdapter(SourceAdapter):
    """Import Azure DevOps build timeline records as failure-data signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        organization: str | None = None,
        project: str | None = None,
        personal_access_token: str | None = None,
        token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.organization = organization or _optional(self._config.get("organization")) or os.getenv("AZURE_DEVOPS_ORGANIZATION") or ""
        self.project = project or _optional(self._config.get("project")) or os.getenv("AZURE_DEVOPS_PROJECT") or ""
        configured_token = personal_access_token if personal_access_token is not None else token
        self.personal_access_token = (
            configured_token
            if configured_token is not None
            else (
                _optional(self._config.get("personal_access_token"))
                or _optional(self._config.get("token"))
                or os.getenv("AZURE_DEVOPS_PAT")
                or os.getenv("AZURE_DEVOPS_TOKEN")
            )
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or "https://dev.azure.com").rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "azure_devops_build_timeline_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def api_version(self) -> str:
        return _text(self._config.get("api_version")) or "7.1"

    @property
    def build_ids(self) -> list[str]:
        return _strings(self._config.get("build_ids") or self._config.get("build_id"))

    @property
    def include_successful(self) -> bool:
        return _bool(self._config.get("include_successful"))

    @property
    def record_types(self) -> set[str]:
        return {item.lower() for item in _strings(self._config.get("record_types") or self._config.get("record_type"))}

    @property
    def per_build_limit(self) -> int | None:
        value = self._config.get("per_build_limit")
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    @property
    def base_url(self) -> str:
        return f"{self.api_url}/{self.organization}/{self.project}".rstrip("/")

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.organization and self.project and self.personal_access_token and self.build_ids):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for build_id in self.build_ids:
                if len(signals) >= limit:
                    break
                build_limit = limit - len(signals)
                if self.per_build_limit:
                    build_limit = min(build_limit, self.per_build_limit)
                records = await self._fetch_timeline(client, build_id=build_id)
                build_count = 0
                for record in records:
                    if build_count >= build_limit:
                        break
                    if not self._matches_record(record):
                        continue
                    signals.append(
                        _record_signal(
                            record,
                            adapter_name=self.name,
                            organization=self.organization,
                            project=self.project,
                            build_id=build_id,
                        )
                    )
                    build_count += 1
                    if len(signals) >= limit:
                        break
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_timeline(self, client: httpx.AsyncClient, *, build_id: str) -> list[dict[str, Any]]:
        try:
            response = await client.get(
                f"{self.base_url}/_apis/build/builds/{build_id}/timeline",
                auth=("", self.personal_access_token or ""),
                headers={
                    "Accept": "application/json",
                    "User-Agent": "max-azure-devops-build-timeline-import/1",
                },
                params={"api-version": self.api_version},
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Azure DevOps build timeline fetch failed for build %s", build_id, exc_info=True)
            return []
        records = body.get("records") if isinstance(body, dict) else None
        return [item for item in records if isinstance(item, dict)] if isinstance(records, list) else []

    def _matches_record(self, record: dict[str, Any]) -> bool:
        record_type = _text(record.get("type")).lower()
        if self.record_types and record_type not in self.record_types:
            return False
        return self.include_successful or _is_notable_record(record)


AzureDevOpsBuildTimelineImportAdapter = AzureDevOpsBuildTimelineAdapter


def _record_signal(
    record: dict[str, Any],
    *,
    adapter_name: str,
    organization: str,
    project: str,
    build_id: str,
) -> Signal:
    record_id = _text(record.get("id"))
    name = _text(record.get("name")) or record_id or "timeline record"
    record_type = _text(record.get("type"))
    state = _text(record.get("state"))
    result = _text(record.get("result"))
    issues = record.get("issues") if isinstance(record.get("issues"), list) else []
    log = record.get("log") if isinstance(record.get("log"), dict) else {}
    log_url = _text(log.get("url"))
    url = log_url or f"https://dev.azure.com/{organization}/{project}/_build/results?buildId={build_id}"
    return Signal(
        id=f"azure-devops-build-timeline:{organization}/{project}:{build_id}:{record_id}",
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"{project} build {build_id} {name} {result or state or 'unknown'}",
        content=_content(record, issues)[:1000],
        url=url,
        author=None,
        published_at=_parse_dt(record.get("startTime") or record.get("finishTime")),
        tags=sorted({"azure-devops", "build-timeline", record_type, state, result} - {""})[:10],
        credibility=0.7,
        metadata={
            "organization": organization,
            "project": project,
            "build_id": build_id,
            "record_id": record.get("id"),
            "parent_id": record.get("parentId"),
            "type": record.get("type"),
            "name": record.get("name"),
            "state": record.get("state"),
            "result": record.get("result"),
            "worker_name": record.get("workerName"),
            "order": record.get("order"),
            "start_time": record.get("startTime"),
            "finish_time": record.get("finishTime"),
            "duration_seconds": _duration_seconds(record.get("startTime"), record.get("finishTime")),
            "log": _log_summary(log),
            "log_url": log_url,
            "issues": [_issue_summary(issue) for issue in issues if isinstance(issue, dict)],
            "raw": record,
        },
    )


def _content(record: dict[str, Any], issues: list[object]) -> str:
    messages = [_text(issue.get("message")) for issue in issues if isinstance(issue, dict) and _text(issue.get("message"))]
    if messages:
        return "\n".join(messages)
    parts = [f"Azure DevOps timeline record {_text(record.get('name')) or _text(record.get('id'))}"]
    for label, value in (("type", record.get("type")), ("state", record.get("state")), ("result", record.get("result"))):
        text = _text(value)
        if text:
            parts.append(f"{label} {text}")
    return "; ".join(parts)


def _is_notable_record(record: dict[str, Any]) -> bool:
    state = _text(record.get("state")).lower()
    result = _text(record.get("result")).lower()
    issues = record.get("issues") if isinstance(record.get("issues"), list) else []
    if state in {"inprogress", "in_progress", "pending"}:
        return True
    if result in {"failed", "canceled", "cancelled", "abandoned", "skipped", "partiallysucceeded", "succeededwithissues"}:
        return True
    return any(
        isinstance(issue, dict) and _text(issue.get("type")).lower() in {"error", "warning"}
        for issue in issues
    )


def _log_summary(log: dict[str, Any]) -> dict[str, Any]:
    return {"id": log.get("id"), "type": log.get("type"), "url": log.get("url")} if log else {}


def _issue_summary(issue: dict[str, Any]) -> dict[str, Any]:
    return {"type": issue.get("type"), "category": issue.get("category"), "message": issue.get("message")}


def _duration_seconds(start: object, end: object) -> int | None:
    started = _parse_dt(start)
    finished = _parse_dt(end)
    if not started or not finished:
        return None
    return max(0, int((finished - started).total_seconds()))


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _strings(value: object) -> list[str]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
    if isinstance(value, str):
        value = [item.strip() for item in value.split(",")]
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
