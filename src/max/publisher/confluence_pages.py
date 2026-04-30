"""Confluence Cloud page publisher for Max design briefs."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from xml.sax.saxutils import escape

import httpx


DEFAULT_CONFLUENCE_API_PATH = "/wiki/rest/api/content"
DEFAULT_TIMEOUT_SECONDS = 10.0


class ConfluencePagePublishError(RuntimeError):
    """Raised when a Confluence page publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ConfluencePagePayload:
    """Confluence page creation payload plus Max-specific metadata."""

    title: str
    space_key: str
    parent_page_id: str | None
    body: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable Confluence page payload preview."""
        payload: dict[str, Any] = {
            "type": "page",
            "title": self.title,
            "space": {"key": self.space_key},
            "body": {"storage": {"value": self.body, "representation": "storage"}},
            "metadata": self.metadata,
        }
        if self.parent_page_id:
            payload["ancestors"] = [{"id": self.parent_page_id}]
            payload["parent_page_id"] = self.parent_page_id
        return payload


@dataclass(frozen=True)
class ConfluencePagePublishResult:
    """Summary of a Confluence page publish or dry run."""

    status_code: int | None
    space_key: str
    page_id: str | None
    page_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class ConfluencePagePublisher:
    """Build and optionally create Confluence Cloud pages from design briefs."""

    def __init__(
        self,
        site_url: str,
        space_key: str,
        *,
        parent_page_id: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
        bearer_token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.site_url = _required_url(site_url)
        self.space_key = _required_text(space_key, "Confluence space_key is required")
        self.parent_page_id = _optional_text(parent_page_id)
        self.email = _optional_text(email)
        self.api_token = _optional_text(api_token)
        self.bearer_token = _optional_text(bearer_token)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        site_url: str | None = None,
        space_key: str | None = None,
        parent_page_id: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
        bearer_token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> ConfluencePagePublisher:
        """Create a publisher using explicit values first, then environment variables."""
        resolved_site_url = site_url or os.getenv("CONFLUENCE_SITE_URL")
        if not resolved_site_url:
            raise ConfluencePagePublishError(
                "Confluence site_url is required; pass site_url or set CONFLUENCE_SITE_URL"
            )
        resolved_space_key = space_key or os.getenv("CONFLUENCE_SPACE_KEY")
        if not resolved_space_key:
            raise ConfluencePagePublishError(
                "Confluence space_key is required; pass space_key or set CONFLUENCE_SPACE_KEY"
            )
        return cls(
            resolved_site_url,
            resolved_space_key,
            parent_page_id=parent_page_id or os.getenv("CONFLUENCE_PARENT_PAGE_ID"),
            email=email or os.getenv("CONFLUENCE_EMAIL"),
            api_token=api_token or os.getenv("CONFLUENCE_API_TOKEN"),
            bearer_token=bearer_token or os.getenv("CONFLUENCE_BEARER_TOKEN"),
            timeout=timeout,
            client=client,
        )

    @property
    def page_endpoint(self) -> str:
        """Return the Confluence REST endpoint used for page creation."""
        return f"{self.site_url}{DEFAULT_CONFLUENCE_API_PATH}"

    def build_page_payload(
        self,
        design_brief: dict[str, Any],
        *,
        title: str | None = None,
    ) -> ConfluencePagePayload:
        """Convert a persisted design brief into a Confluence storage-format page."""
        brief = _brief_payload(design_brief)
        page_title = _truncate_text(
            _optional_text(title) or _optional_text(brief.get("title")) or "Design Brief",
            255,
        )
        metadata = {
            "publisher": "max.confluence_pages",
            "source_type": "design_brief",
            "design_brief_id": brief.get("id"),
            "schema_version": design_brief.get("schema_version") or "max.blueprint.source_brief.v1",
            "space_key": self.space_key,
            "parent_page_id": self.parent_page_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return ConfluencePagePayload(
            title=page_title,
            space_key=self.space_key,
            parent_page_id=self.parent_page_id,
            body=_storage_body(design_brief, page_title),
            metadata=metadata,
        )

    async def publish(
        self,
        design_brief: dict[str, Any],
        *,
        title: str | None = None,
        dry_run: bool = True,
    ) -> ConfluencePagePublishResult:
        """Build the page payload and optionally create it in Confluence Cloud."""
        payload = self.build_page_payload(design_brief, title=title).to_dict()
        return await self.publish_page_payload(payload, dry_run=dry_run)

    async def publish_page_payload(
        self,
        payload: dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> ConfluencePagePublishResult:
        """Publish a caller-rendered Confluence page payload."""
        page_payload = {
            **payload,
            "type": payload.get("type") or "page",
            "space": payload.get("space") or {"key": self.space_key},
        }
        if self.parent_page_id and not page_payload.get("ancestors"):
            page_payload["ancestors"] = [{"id": self.parent_page_id}]
            page_payload["parent_page_id"] = self.parent_page_id

        if dry_run:
            return ConfluencePagePublishResult(
                status_code=None,
                space_key=self.space_key,
                page_id=None,
                page_url=None,
                dry_run=True,
                payload=page_payload,
            )

        if not self._has_auth:
            raise ConfluencePagePublishError(
                "Confluence email/api_token or bearer_token is required for live page publishing; "
                "use dry_run to preview"
            )

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.timeout)
        try:
            try:
                response = await client.post(
                    self.page_endpoint,
                    json=_confluence_page_request(page_payload),
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise ConfluencePagePublishError(
                    f"Confluence page publish failed for {self.page_endpoint}: {exc}"
                ) from exc
        finally:
            if close_client:
                await client.aclose()

        if not 200 <= response.status_code < 300:
            raise ConfluencePagePublishError(
                f"Confluence page publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        body = _json_response(response)
        page_id = body.get("id")
        if not page_id:
            raise ConfluencePagePublishError(
                "Confluence page publish failed: response did not include created page id",
                status_code=response.status_code,
            )
        page_url = _page_url(self.site_url, body)
        metadata = {
            **(page_payload.get("metadata") or {}),
            "confluence_page_id": str(page_id),
            "confluence_page_url": page_url,
        }
        return ConfluencePagePublishResult(
            status_code=response.status_code,
            space_key=self.space_key,
            page_id=str(page_id),
            page_url=page_url,
            dry_run=False,
            payload={**page_payload, "metadata": metadata},
        )

    @property
    def _has_auth(self) -> bool:
        return bool(self.bearer_token or (self.email and self.api_token))

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "max-confluence-pages-publisher/1",
        }
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        else:
            assert self.email is not None and self.api_token is not None
            credentials = f"{self.email}:{self.api_token}".encode("utf-8")
            headers["Authorization"] = f"Basic {base64.b64encode(credentials).decode('ascii')}"
        return headers


ConfluencePagesPublisher = ConfluencePagePublisher


def _confluence_page_request(payload: dict[str, Any]) -> dict[str, Any]:
    request = {
        "type": payload.get("type") or "page",
        "title": payload["title"],
        "space": payload["space"],
        "body": payload["body"],
    }
    if payload.get("ancestors"):
        request["ancestors"] = payload["ancestors"]
    return request


def _storage_body(payload: dict[str, Any], title: str) -> str:
    brief = _brief_payload(payload)
    source_ideas = payload.get("source_ideas") if isinstance(payload.get("source_ideas"), list) else []
    lead_source = next(
        (idea for idea in source_ideas if isinstance(idea, dict) and idea.get("role") == "lead"),
        source_ideas[0] if source_ideas and isinstance(source_ideas[0], dict) else {},
    )

    sections = [
        _heading(title, 1),
        _paragraph(brief.get("merged_product_concept") or "No product concept was provided."),
    ]
    sections.extend(
        _section(
            "Problem",
            lead_source.get("problem"),
        )
    )
    sections.extend(
        _section(
            "Solution",
            lead_source.get("solution") or brief.get("merged_product_concept"),
        )
    )
    sections.extend(
        _section(
            "Evidence",
            lead_source.get("evidence_rationale") or brief.get("synthesis_rationale"),
            bullets=_text_items(brief.get("source_idea_ids"), prefix="Source idea: "),
        )
    )
    sections.extend(_section("Roadmap", None, bullets=_text_items(brief.get("first_milestones"))))
    sections.extend(_section("Risks", None, bullets=_text_items(brief.get("risks"))))
    sections.extend(
        _section(
            "Metadata",
            None,
            bullets=[
                f"Design brief ID: {_text_or_placeholder(brief.get('id'))}",
                f"Domain: {_text_or_placeholder(brief.get('domain'))}",
            ],
        )
    )
    return "\n".join(section for section in sections if section)


def _section(title: str, body: object, *, bullets: list[str] | None = None) -> list[str]:
    lines: list[str] = []
    text = _optional_text(body)
    bullet_items = bullets or []
    if not text and not bullet_items:
        return lines
    lines.append(_heading(title, 2))
    if text:
        lines.append(_paragraph(text))
    if bullet_items:
        lines.append("<ul>")
        lines.extend(f"<li>{_escape_text(item)}</li>" for item in bullet_items)
        lines.append("</ul>")
    return lines


def _heading(text: object, level: int) -> str:
    return f"<h{level}>{_escape_text(text)}</h{level}>"


def _paragraph(text: object) -> str:
    return f"<p>{_escape_text(text)}</p>"


def _escape_text(text: object) -> str:
    return escape(str(text).strip() if text is not None else "")


def _text_items(value: object, *, prefix: str = "") -> list[str]:
    if not isinstance(value, list):
        return []
    return [f"{prefix}{item}" for item in value if _optional_text(item)]


def _brief_payload(payload: dict[str, Any]) -> dict[str, Any]:
    brief = payload.get("design_brief") if isinstance(payload.get("design_brief"), dict) else payload
    return brief if isinstance(brief, dict) else {}


def _page_url(site_url: str, response_body: dict[str, Any]) -> str | None:
    links = response_body.get("_links") if isinstance(response_body.get("_links"), dict) else {}
    webui = links.get("webui")
    if webui:
        return f"{site_url}{webui}" if str(webui).startswith("/") else str(webui)
    tinyui = links.get("tinyui")
    if tinyui:
        return f"{site_url}{tinyui}" if str(tinyui).startswith("/") else str(tinyui)
    page_id = response_body.get("id")
    return f"{site_url}/wiki/spaces/{response_body.get('space', {}).get('key', '')}/pages/{page_id}" if page_id else None


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError as exc:
        raise ConfluencePagePublishError(
            "Confluence page publish failed: response was not valid JSON",
            status_code=response.status_code,
        ) from exc
    if not isinstance(data, dict):
        raise ConfluencePagePublishError(
            "Confluence page publish failed: response JSON was not an object",
            status_code=response.status_code,
        )
    return data


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = response.text.strip()
    return text if len(text) <= limit else text[:limit] + "..."


def _required_url(value: str) -> str:
    text = _required_text(value, "Confluence site_url is required")
    if not text.startswith(("http://", "https://")):
        raise ConfluencePagePublishError("Confluence site_url must start with http:// or https://")
    return text.rstrip("/")


def _required_text(value: object, message: str) -> str:
    text = _optional_text(value)
    if not text:
        raise ConfluencePagePublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _text_or_placeholder(value: object) -> str:
    return _optional_text(value) or "Not specified"


def _truncate_text(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "..."
