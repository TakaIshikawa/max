"""Notion page publisher for Max design briefs."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

import httpx


DEFAULT_NOTION_API_URL = "https://api.notion.com/v1"
DEFAULT_NOTION_VERSION = "2022-06-28"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_RETRIES = 2
MAX_TEXT_CONTENT_LENGTH = 1900
MAX_CHILDREN_PER_REQUEST = 100
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class NotionPagePublishError(RuntimeError):
    """Raised when a Notion page publish cannot be completed."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


@dataclass(frozen=True)
class NotionPagePayload:
    """Notion page creation payload plus overflow children."""

    page: dict[str, Any]
    append_children: list[dict[str, Any]]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "append_children": self.append_children,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class NotionPagePublishResult:
    """Summary of a Notion page publish or dry run."""

    status_code: int | None
    page_id: str | None
    page_url: str | None
    dry_run: bool
    payload: dict[str, Any]
    attempts: int


class NotionPagePublisher:
    """Build and optionally create Notion pages from design brief Markdown."""

    def __init__(
        self,
        *,
        token: str | None = None,
        parent_page_id: str | None = None,
        parent_database_id: str | None = None,
        api_url: str = DEFAULT_NOTION_API_URL,
        notion_version: str = DEFAULT_NOTION_VERSION,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_RETRIES,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be greater than or equal to 0")
        self.token = token
        self.parent_page_id = _clean_text(parent_page_id)
        self.parent_database_id = _clean_text(parent_database_id)
        self.api_url = api_url.rstrip("/")
        self.notion_version = notion_version
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = client
        self._sleep = sleep
        _validate_parent(self.parent_page_id, self.parent_database_id)

    @classmethod
    def from_env(
        cls,
        *,
        token: str | None = None,
        parent_page_id: str | None = None,
        parent_database_id: str | None = None,
        api_url: str | None = None,
        notion_version: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_RETRIES,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> NotionPagePublisher:
        """Create a publisher using explicit values first, then environment variables."""
        return cls(
            token=token or os.getenv("NOTION_TOKEN"),
            parent_page_id=parent_page_id or os.getenv("NOTION_PARENT_PAGE_ID"),
            parent_database_id=parent_database_id or os.getenv("NOTION_PARENT_DATABASE_ID"),
            api_url=api_url or os.getenv("NOTION_API_URL", DEFAULT_NOTION_API_URL),
            notion_version=notion_version or os.getenv("NOTION_VERSION", DEFAULT_NOTION_VERSION),
            timeout=timeout,
            max_retries=max_retries,
            client=client,
            sleep=sleep,
        )

    @property
    def pages_endpoint(self) -> str:
        return f"{self.api_url}/pages"

    def append_children_endpoint(self, page_id: str) -> str:
        return f"{self.api_url}/blocks/{page_id}/children"

    @property
    def parent_target(self) -> str:
        if self.parent_database_id:
            return f"database:{self.parent_database_id}"
        return f"page:{self.parent_page_id}"

    def build_payload(
        self,
        design_brief: dict[str, Any],
        *,
        markdown: str,
        title: str | None = None,
    ) -> NotionPagePayload:
        """Convert a persisted design brief and rendered Markdown to Notion JSON."""
        brief = _brief_payload(design_brief)
        page_title = _truncate_plain_text(
            _clean_text(title) or _clean_text(brief.get("title")) or "Design Brief",
            200,
        )
        blocks = _markdown_to_blocks(_merge_structured_markdown(markdown, design_brief))
        if not blocks:
            blocks = [_paragraph_block("No design brief content was provided.")]

        page: dict[str, Any] = {
            "parent": self._parent_payload(),
            "properties": self._properties_payload(page_title, brief),
            "children": blocks[:MAX_CHILDREN_PER_REQUEST],
        }
        metadata = {
            "publisher": "max.notion_pages",
            "source_type": "design_brief",
            "design_brief_id": brief.get("id"),
            "schema_version": design_brief.get("schema_version") or "max.blueprint.source_brief.v1",
            "parent": self.parent_target,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "block_count": len(blocks),
        }
        return NotionPagePayload(
            page=page,
            append_children=blocks[MAX_CHILDREN_PER_REQUEST:],
            metadata=metadata,
        )

    def publish(
        self,
        design_brief: dict[str, Any],
        *,
        markdown: str,
        title: str | None = None,
        dry_run: bool = False,
    ) -> NotionPagePublishResult:
        """Build the Notion payload and optionally create the page."""
        payload = self.build_payload(design_brief, markdown=markdown, title=title)
        payload_dict = payload.to_dict()
        if dry_run:
            return NotionPagePublishResult(
                status_code=None,
                page_id=None,
                page_url=None,
                dry_run=True,
                payload=payload_dict,
                attempts=0,
            )

        if not self.token:
            raise NotionPagePublishError(
                "Notion token is required; pass token or set NOTION_TOKEN",
                status_code=400,
            )

        response, attempts = self._post_with_retries(self.pages_endpoint, payload.page)
        page_id = _response_page_id(response)
        page_url = _response_page_url(response)

        for batch in _batched(payload.append_children, MAX_CHILDREN_PER_REQUEST):
            self._patch_with_retries(
                self.append_children_endpoint(page_id),
                {"children": batch},
            )

        return NotionPagePublishResult(
            status_code=response.status_code,
            page_id=page_id,
            page_url=page_url,
            dry_run=False,
            payload=payload_dict,
            attempts=attempts,
        )

    def _parent_payload(self) -> dict[str, str]:
        if self.parent_database_id:
            return {"database_id": self.parent_database_id}
        return {"page_id": self.parent_page_id or ""}

    def _properties_payload(self, title: str, design_brief: dict[str, Any]) -> dict[str, Any]:
        properties: dict[str, Any] = {
            "title": {"title": [_text_rich_text(title)]},
        }
        if self.parent_database_id:
            properties = {
                "Name": {"title": [_text_rich_text(title)]},
            }
        return properties

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Notion-Version": self.notion_version,
            "User-Agent": "max-notion-page-publisher/1",
        }

    def _post_with_retries(self, url: str, json_payload: dict[str, Any]) -> tuple[httpx.Response, int]:
        return self._request_with_retries("POST", url, json_payload)

    def _patch_with_retries(self, url: str, json_payload: dict[str, Any]) -> tuple[httpx.Response, int]:
        return self._request_with_retries("PATCH", url, json_payload)

    def _request_with_retries(
        self,
        method: str,
        url: str,
        json_payload: dict[str, Any],
    ) -> tuple[httpx.Response, int]:
        attempts_allowed = self.max_retries + 1
        last_error: Exception | None = None
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            for attempt in range(1, attempts_allowed + 1):
                try:
                    response = client.request(
                        method,
                        url,
                        json=json_payload,
                        headers=self._headers(),
                        timeout=self.timeout,
                    )
                except (httpx.RequestError, httpx.TimeoutException) as exc:
                    last_error = exc
                    if attempt == attempts_allowed:
                        break
                    self._sleep(min(2 ** (attempt - 1), 8))
                    continue

                if 200 <= response.status_code < 300:
                    return response, attempt

                retryable = response.status_code in RETRYABLE_STATUS_CODES
                last_error = NotionPagePublishError(
                    _notion_error_message(response),
                    status_code=response.status_code,
                    retryable=retryable,
                )
                if not retryable or attempt == attempts_allowed:
                    break
                self._sleep(_retry_delay(response, attempt))
        finally:
            if close_client:
                client.close()

        if isinstance(last_error, NotionPagePublishError):
            raise last_error
        detail = str(last_error) if last_error else "unknown error"
        raise NotionPagePublishError(f"Notion page publish failed: {detail}", retryable=True)


NotionPagesPublisher = NotionPagePublisher


def _validate_parent(parent_page_id: str | None, parent_database_id: str | None) -> None:
    if bool(parent_page_id) == bool(parent_database_id):
        raise NotionPagePublishError(
            "Provide exactly one Notion parent: parent_page_id or parent_database_id",
            status_code=400,
        )


def _markdown_to_blocks(markdown: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph_lines:
            return
        text = "\n".join(paragraph_lines).strip()
        paragraph_lines.clear()
        if text:
            blocks.extend(_paragraph_block(chunk) for chunk in _split_text(text))

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            continue

        heading = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            text = _strip_inline_markdown(heading.group(2))
            for index, chunk in enumerate(_split_text(text)):
                if index == 0:
                    blocks.append(_heading_block(chunk, level))
                else:
                    blocks.append(_paragraph_block(chunk))
            continue

        bullet = re.match(r"^[-*]\s+(.+)$", stripped)
        if bullet:
            flush_paragraph()
            for chunk in _split_text(_strip_inline_markdown(bullet.group(1))):
                blocks.append(_bulleted_list_item_block(chunk))
            continue

        paragraph_lines.append(_strip_inline_markdown(stripped))

    flush_paragraph()
    return blocks


def _merge_structured_markdown(markdown: str, payload: dict[str, Any]) -> str:
    brief = _brief_payload(payload)
    source_ideas = payload.get("source_ideas") if isinstance(payload.get("source_ideas"), list) else []
    lead_source = next(
        (idea for idea in source_ideas if isinstance(idea, dict) and idea.get("role") == "lead"),
        source_ideas[0] if source_ideas and isinstance(source_ideas[0], dict) else {},
    )
    sections: list[str] = []

    problem = _clean_text(lead_source.get("problem"))
    if problem:
        sections.extend(["## Problem", "", problem, ""])

    solution = _clean_text(lead_source.get("solution")) or _clean_text(brief.get("merged_product_concept"))
    if solution:
        sections.extend(["## Solution", "", solution, ""])

    evidence = _clean_text(lead_source.get("evidence_rationale")) or _clean_text(brief.get("synthesis_rationale"))
    source_ids = [str(item) for item in brief.get("source_idea_ids", []) if item]
    if evidence or source_ids:
        sections.extend(["## Evidence", ""])
        if evidence:
            sections.extend([evidence, ""])
        if source_ids:
            sections.append("- Source ideas: " + ", ".join(source_ids))
        sections.append("")

    roadmap = [str(item) for item in brief.get("first_milestones", []) if item]
    if roadmap:
        sections.extend(["## Roadmap", ""])
        sections.extend(f"- {item}" for item in roadmap)
        sections.append("")

    risks = [str(item) for item in brief.get("risks", []) if item]
    if risks and "### risks" not in markdown.lower() and "## risks" not in markdown.lower():
        sections.extend(["## Risks", ""])
        sections.extend(f"- {risk}" for risk in risks)
        sections.append("")

    if not sections:
        return markdown
    return markdown.rstrip() + "\n\n" + "\n".join(sections)


def _brief_payload(payload: dict[str, Any]) -> dict[str, Any]:
    brief = payload.get("design_brief") if isinstance(payload.get("design_brief"), dict) else payload
    return brief if isinstance(brief, dict) else {}


def _heading_block(text: str, level: int) -> dict[str, Any]:
    block_type = {1: "heading_1", 2: "heading_2"}.get(level, "heading_3")
    return {"object": "block", "type": block_type, block_type: {"rich_text": [_text_rich_text(text)]}}


def _paragraph_block(text: str) -> dict[str, Any]:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [_text_rich_text(text)]}}


def _bulleted_list_item_block(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": [_text_rich_text(text)]},
    }


def _text_rich_text(text: str) -> dict[str, Any]:
    return {"type": "text", "text": {"content": text}}


def _split_text(text: str, *, limit: int = MAX_TEXT_CONTENT_LENGTH) -> list[str]:
    normalized = text.strip()
    if not normalized:
        return [""]
    chunks: list[str] = []
    remaining = normalized
    while len(remaining) > limit:
        split_at = remaining.rfind(" ", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _strip_inline_markdown(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text.strip()


def _notion_error_message(response: httpx.Response) -> str:
    body = _response_body(response)
    message = body
    try:
        data = response.json()
    except ValueError:
        data = None
    if isinstance(data, dict):
        notion_message = data.get("message")
        code = data.get("code")
        if notion_message:
            message = f"{code}: {notion_message}" if code else str(notion_message)
    return f"Notion API returned HTTP {response.status_code}: {message}"


def _response_body(response: httpx.Response, *, limit: int = 500) -> str:
    text = response.text.strip()
    return text if len(text) <= limit else text[:limit] + "..."


def _response_page_id(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError as exc:
        raise NotionPagePublishError("Notion API returned invalid JSON", status_code=response.status_code) from exc
    page_id = data.get("id") if isinstance(data, dict) else None
    if not page_id:
        raise NotionPagePublishError(
            "Notion API response did not include a page id",
            status_code=response.status_code,
        )
    return str(page_id)


def _response_page_url(response: httpx.Response) -> str | None:
    try:
        data = response.json()
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    url = data.get("url") or data.get("public_url")
    return str(url) if url else None


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    retry_after = response.headers.get("retry-after")
    if retry_after:
        try:
            return min(float(retry_after), 30.0)
        except ValueError:
            pass
    return min(2 ** (attempt - 1), 8)


def _batched(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _truncate_plain_text(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "..."


def _clean_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None
