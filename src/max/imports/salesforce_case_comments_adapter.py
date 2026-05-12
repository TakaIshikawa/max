"""Salesforce CaseComment import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
DEFAULT_API_VERSION = "v60.0"
DEFAULT_CASE_COMMENT_FIELDS = (
    "Id",
    "ParentId",
    "CommentBody",
    "IsPublished",
    "CreatedById",
    "CreatedBy.Name",
    "CreatedDate",
    "LastModifiedDate",
)


class SalesforceCaseCommentsAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        instance_url: str | None = None,
        access_token: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.instance_url = (
            instance_url
            or _optional(self._config.get("instance_url"))
            or os.getenv("SALESFORCE_INSTANCE_URL")
            or ""
        ).rstrip("/")
        self.access_token = (
            access_token
            if access_token is not None
            else (_optional(self._config.get("access_token")) or os.getenv("SALESFORCE_ACCESS_TOKEN"))
        )
        self._client = client

    @property
    def name(self) -> str:
        return "salesforce_case_comments_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.SURVEY.value

    @property
    def api_version(self) -> str:
        version = _optional(self._config.get("api_version")) or DEFAULT_API_VERSION
        return version if version.startswith("v") else f"v{version}"

    @property
    def case_ids(self) -> list[str]:
        return _strings(
            self._config.get("case_ids")
            or self._config.get("cases")
            or self._config.get("case_id")
        )

    @property
    def limit(self) -> int | None:
        value = self._config.get("limit")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
        return None

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("batch_size"), default=200, maximum=2000)

    @property
    def query(self) -> str:
        fields = ", ".join(DEFAULT_CASE_COMMENT_FIELDS)
        case_ids = ", ".join(_soql_string(case_id) for case_id in self.case_ids)
        return f"SELECT {fields} FROM CaseComment WHERE ParentId IN ({case_ids}) ORDER BY CreatedDate DESC"

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        effective_limit = min(limit, self.limit) if self.limit else limit
        if effective_limit <= 0 or not (self.instance_url and self.access_token and self.case_ids):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            records: list[dict[str, Any]] = []
            seen: set[str] = set()
            path: str | None = f"/services/data/{self.api_version}/query"
            params: dict[str, Any] | None = {"q": self.query}
            while path and len(records) < effective_limit:
                body = await self._get(client, path=path, params=params)
                page = body.get("records") if isinstance(body.get("records"), list) else []
                for record in page:
                    if not isinstance(record, dict):
                        continue
                    comment_id = _text(record.get("Id"))
                    if not comment_id or comment_id in seen:
                        continue
                    seen.add(comment_id)
                    records.append(record)
                    if len(records) >= effective_limit:
                        break
                next_url = _optional(body.get("nextRecordsUrl"))
                path = next_url if next_url and len(records) < effective_limit else None
                params = None
        finally:
            if close_client:
                await client.aclose()
        return [_comment_signal(record, self.name, self.instance_url) for record in records[:effective_limit]]

    async def _get(self, client: httpx.AsyncClient, *, path: str, params: dict[str, Any] | None) -> dict[str, Any]:
        try:
            response = await client.get(
                f"{self.instance_url}{path}",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Accept": "application/json",
                    "Sforce-Query-Options": f"batchSize={self.page_size}",
                    "User-Agent": "max-salesforce-case-comments-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Salesforce CaseComment fetch failed", exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


SalesforceCaseCommentAdapter = SalesforceCaseCommentsAdapter


def _comment_signal(record: dict[str, Any], adapter_name: str, instance_url: str) -> Signal:
    created_by = record.get("CreatedBy") if isinstance(record.get("CreatedBy"), dict) else {}
    comment_id = _text(record.get("Id"))
    case_id = _text(record.get("ParentId"))
    body = _text(record.get("CommentBody"))
    record_url = f"{instance_url}/lightning/r/Case/{case_id}/view" if case_id else instance_url
    title = f"Salesforce case comment {comment_id}" if comment_id else "Salesforce case comment"
    return Signal(
        id=f"salesforce-case-comment:{comment_id}" if comment_id else "",
        source_type=SignalSourceType.SURVEY,
        source_adapter=adapter_name,
        title=title,
        content=body[:1000],
        url=record_url,
        author=_text(created_by.get("Name")) or None,
        published_at=_parse_dt(record.get("CreatedDate")),
        tags=sorted({"salesforce", "case-comment", "customer-feedback"} - {""})[:10],
        credibility=0.7,
        metadata={
            "salesforce_case_comment_id": record.get("Id"),
            "salesforce_case_id": record.get("ParentId"),
            "comment_body": record.get("CommentBody"),
            "is_published": record.get("IsPublished"),
            "created_by_id": record.get("CreatedById"),
            "created_by": created_by.get("Name"),
            "created_date": record.get("CreatedDate"),
            "last_modified_date": record.get("LastModifiedDate"),
            "raw": record,
        },
    )


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
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


def _soql_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _strings(value: object) -> list[str]:
    if isinstance(value, (str, int)) and not isinstance(value, bool):
        value = [value]
    if not isinstance(value, list | tuple | set):
        return []
    strings: list[str] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, bool):
            continue
        if isinstance(item, dict):
            item = item.get("id") or item.get("case_id") or item.get("ParentId")
        text = _text(item)
        if text and text not in seen:
            seen.add(text)
            strings.append(text)
    return strings


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
