"""Notion database publisher for approved Max buildable units."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

import httpx


DEFAULT_NOTION_API_URL = "https://api.notion.com/v1"
DEFAULT_NOTION_VERSION = "2022-06-28"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RETRIES = 2
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class NotionDatabasePublishError(RuntimeError):
    """Raised when a Notion database page cannot be published."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class NotionDatabasePayload:
    """Notion page creation payload for one BuildableUnit."""

    parent: dict[str, str]
    properties: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent": self.parent,
            "properties": self.properties,
            "metadata": self.metadata,
        }


class NotionDatabasePublisher:
    """Create Notion database pages from approved BuildableUnit dictionaries."""

    def __init__(
        self,
        *,
        token: str | None = None,
        database_id: str | None = None,
        api_url: str = DEFAULT_NOTION_API_URL,
        notion_version: str = DEFAULT_NOTION_VERSION,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.token = _required_text(
            token or os.getenv("NOTION_API_TOKEN"),
            "Notion API token is required; pass token or set NOTION_API_TOKEN",
        )
        self.database_id = _required_text(
            database_id or os.getenv("NOTION_DATABASE_ID"),
            "Notion database ID is required; pass database_id or set NOTION_DATABASE_ID",
        )
        self.api_url = _required_text(api_url, "Notion API URL is required").rstrip("/")
        self.notion_version = _required_text(notion_version, "Notion API version is required")
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self._client = client
        self._sleep = sleep

    @classmethod
    def from_env(
        cls,
        *,
        token: str | None = None,
        database_id: str | None = None,
        api_url: str | None = None,
        notion_version: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> NotionDatabasePublisher:
        """Create a publisher using explicit values first, then environment variables."""
        return cls(
            token=token,
            database_id=database_id,
            api_url=api_url or os.getenv("NOTION_API_URL", DEFAULT_NOTION_API_URL),
            notion_version=notion_version
            or os.getenv("NOTION_VERSION", DEFAULT_NOTION_VERSION),
            timeout=timeout,
            max_retries=max_retries,
            client=client,
            sleep=sleep,
        )

    @property
    def pages_endpoint(self) -> str:
        return f"{self.api_url}/pages"

    def build_payload(self, unit: dict[str, Any]) -> NotionDatabasePayload:
        """Map a BuildableUnit dictionary to Notion API v1 page properties."""
        title = _first_text(unit, "title", "name", default="Untitled idea")
        status = _first_text(unit, "status", default="approved")
        categories = _list_property(unit.get("category"))
        problem = _first_text(unit, "problem_statement", "problem")
        solution = _first_text(unit, "solution_approach", "solution")
        tech_stack = _tech_stack_values(unit)
        score = _score(unit)

        properties: dict[str, Any] = {
            "Title": {"title": [_rich_text(title)]},
            "Status": {"select": {"name": status}},
            "Category": {"multi_select": [{"name": value} for value in categories]},
            "Problem Statement": {"rich_text": [_rich_text(problem)] if problem else []},
            "Solution Approach": {"rich_text": [_rich_text(solution)] if solution else []},
            "Tech Stack": {"multi_select": [{"name": value} for value in tech_stack]},
        }
        if score is not None:
            properties["Score"] = {"number": score}

        return NotionDatabasePayload(
            parent={"database_id": self.database_id},
            properties=properties,
            metadata={
                "publisher": "max.notion_database",
                "source_type": "buildable_unit",
                "unit_id": _first_text(unit, "id", "idea_id"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def publish(self, unit: dict[str, Any]) -> dict[str, str]:
        """Create a Notion database page and return Notion's page identifiers."""
        payload = self.build_payload(unit)
        response = self._post_with_retries(payload.to_dict())
        data = _response_json(response)
        page_id = _required_response_text(data, "id", response.status_code)
        return {
            "id": page_id,
            "url": str(data.get("url") or data.get("public_url") or ""),
            "created_time": str(data.get("created_time") or ""),
        }

    def _post_with_retries(self, payload: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        last_error: Exception | None = None
        try:
            for attempt in range(1, self.max_retries + 2):
                try:
                    response = client.post(
                        self.pages_endpoint,
                        json={key: payload[key] for key in ("parent", "properties")},
                        headers=self._headers(),
                        timeout=self.timeout,
                    )
                except (httpx.RequestError, httpx.TimeoutException) as exc:
                    last_error = exc
                    if attempt > self.max_retries:
                        break
                    self._sleep(min(2 ** (attempt - 1), 8))
                    continue

                if 200 <= response.status_code < 300:
                    return response
                last_error = NotionDatabasePublishError(
                    _notion_error_message(response),
                    status_code=response.status_code,
                )
                if response.status_code not in RETRYABLE_STATUS_CODES or attempt > self.max_retries:
                    break
                self._sleep(_retry_delay(response, attempt))
        finally:
            if close_client:
                client.close()

        if isinstance(last_error, NotionDatabasePublishError):
            raise last_error
        raise NotionDatabasePublishError(f"Notion database publish failed: {last_error}")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Notion-Version": self.notion_version,
            "User-Agent": "max-notion-database-publisher/1",
        }


NotionDatabasesPublisher = NotionDatabasePublisher


def _rich_text(text: str) -> dict[str, Any]:
    return {"type": "text", "text": {"content": text}}


def _first_text(mapping: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = mapping.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def _required_text(value: str | None, message: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(message)
    return text


def _list_property(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, dict):
        if "name" in value:
            return _list_property(value["name"])
        values: list[str] = []
        for item in value.values():
            values.extend(_list_property(item))
        return _dedupe(values)
    if isinstance(value, list | tuple | set):
        values = []
        for item in value:
            values.extend(_list_property(item))
        return _dedupe(values)
    text = str(value).strip()
    return [text] if text else []


def _tech_stack_values(unit: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("tech_stack", "technology_stack", "suggested_stack"):
        values.extend(_list_property(unit.get(key)))
    solution = unit.get("solution")
    if isinstance(solution, dict):
        values.extend(_list_property(solution.get("tech_stack")))
        values.extend(_list_property(solution.get("suggested_stack")))
    return _dedupe(values)


def _score(unit: dict[str, Any]) -> float | None:
    for key in ("score", "overall_score", "quality_score", "usefulness_score"):
        value = unit.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    evaluation = unit.get("evaluation")
    if isinstance(evaluation, dict):
        return _score(evaluation)
    return None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        text = str(value).strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            deduped.append(text)
    return deduped


def _response_json(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError as exc:
        raise NotionDatabasePublishError(
            "Notion API returned invalid JSON",
            status_code=response.status_code,
        ) from exc
    if not isinstance(data, dict):
        raise NotionDatabasePublishError(
            "Notion API returned a non-object JSON response",
            status_code=response.status_code,
        )
    return data


def _required_response_text(
    data: dict[str, Any],
    key: str,
    status_code: int,
) -> str:
    value = data.get(key)
    text = str(value).strip() if value is not None else ""
    if not text:
        raise NotionDatabasePublishError(
            f"Notion API response did not include {key}",
            status_code=status_code,
        )
    return text


def _notion_error_message(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        data = None
    if isinstance(data, dict):
        code = data.get("code")
        message = data.get("message")
        if message:
            detail = f"{code}: {message}" if code else str(message)
            return f"Notion API returned HTTP {response.status_code}: {detail}"
    return f"Notion API returned HTTP {response.status_code}: {response.text.strip()}"


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    retry_after = response.headers.get("retry-after")
    if retry_after:
        try:
            return min(float(retry_after), 30.0)
        except ValueError:
            pass
    return min(2 ** (attempt - 1), 8)
