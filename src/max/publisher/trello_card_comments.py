"""Trello card comment publisher for generated specs and review notes."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from max.publisher.trello_cards import (
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_TRELLO_API_URL,
    _redact_text,
)
from max.publisher.trello_cards import _required_url as _required_trello_url


class TrelloCardCommentPublishError(RuntimeError):
    """Raised when a Trello card comment publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(_redact_text(message))
        self.status_code = status_code


@dataclass(frozen=True)
class TrelloCardCommentPayload:
    """Trello card comment payload plus Max-specific metadata."""

    text: str
    card_id: str | None
    card_short_link: str | None
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable card comment payload preview."""
        payload: dict[str, Any] = {
            "text": self.text,
            "metadata": self.metadata,
        }
        if self.card_id:
            payload["card_id"] = self.card_id
        if self.card_short_link:
            payload["card_short_link"] = self.card_short_link
        return payload


@dataclass(frozen=True)
class TrelloCardCommentPublishResult:
    """Summary of a Trello card comment publish or dry run."""

    status_code: int | None
    card_id: str
    card_url: str | None
    comment_id: str | None
    dry_run: bool
    payload: dict[str, Any]


class TrelloCardCommentPublisher:
    """Build and optionally append generated artifacts to existing Trello cards."""

    def __init__(
        self,
        *,
        card_id: str | None = None,
        card_short_link: str | None = None,
        key: str | None = None,
        token: str | None = None,
        api_url: str = DEFAULT_TRELLO_API_URL,
        artifact_title: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.card_id = _optional_text(card_id)
        self.card_short_link = _optional_text(card_short_link)
        self.key = _optional_text(key)
        self.token = _optional_text(token)
        self.api_url = _required_url(api_url)
        self.artifact_title = _optional_text(artifact_title)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        card_id: str | None = None,
        card_short_link: str | None = None,
        key: str | None = None,
        token: str | None = None,
        api_url: str | None = None,
        artifact_title: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> TrelloCardCommentPublisher:
        """Create a publisher using API values first, then environment variables."""
        return cls(
            card_id=card_id or os.getenv("TRELLO_CARD_ID"),
            card_short_link=card_short_link or os.getenv("TRELLO_CARD_SHORT_LINK"),
            key=key or os.getenv("TRELLO_KEY"),
            token=token or os.getenv("TRELLO_TOKEN"),
            api_url=api_url or os.getenv("TRELLO_API_URL", DEFAULT_TRELLO_API_URL),
            artifact_title=artifact_title or os.getenv("TRELLO_ARTIFACT_TITLE"),
            timeout=timeout,
            client=client,
        )

    def comment_endpoint(
        self,
        *,
        card_id: str | None = None,
        card_short_link: str | None = None,
    ) -> str:
        """Return the Trello REST endpoint used for card comment creation."""
        return f"{self.api_url}/cards/{self._resolve_card_identifier(card_id, card_short_link)}/actions/comments"

    @property
    def has_auth(self) -> bool:
        """Return whether live Trello card comment publishing has credentials."""
        return bool(self.key and self.token)

    def build_comment_payload(
        self,
        artifact: dict[str, Any] | str,
        *,
        card_id: str | None = None,
        card_short_link: str | None = None,
        text: str | None = None,
        markdown: str | None = None,
        artifact_title: str | None = None,
    ) -> TrelloCardCommentPayload:
        """Convert generated text or an artifact dictionary into a Trello comment payload."""
        resolved_card_id = self._resolve_card_identifier(card_id, card_short_link)
        resolved_short_link = _optional_text(card_short_link) or self.card_short_link
        return TrelloCardCommentPayload(
            text=_comment_text(
                artifact,
                text=text,
                markdown=markdown,
                artifact_title=artifact_title or self.artifact_title,
            ),
            card_id=resolved_card_id,
            card_short_link=resolved_short_link,
            metadata=_metadata(
                artifact,
                card_id=resolved_card_id,
                card_short_link=resolved_short_link,
            ),
        )

    def publish(
        self,
        artifact: dict[str, Any] | str,
        *,
        dry_run: bool = True,
        card_id: str | None = None,
        card_short_link: str | None = None,
        text: str | None = None,
        markdown: str | None = None,
        artifact_title: str | None = None,
    ) -> TrelloCardCommentPublishResult:
        """Build the comment payload and optionally append it to a Trello card."""
        payload = self.build_comment_payload(
            artifact,
            card_id=card_id,
            card_short_link=card_short_link,
            text=text,
            markdown=markdown,
            artifact_title=artifact_title,
        ).to_dict()
        return self.publish_comment_payload(payload, dry_run=dry_run)

    def publish_comment_payload(
        self,
        payload: dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> TrelloCardCommentPublishResult:
        """Publish a caller-rendered Trello card comment payload."""
        card_identifier = self._resolve_card_identifier(
            _optional_text(payload.get("card_id")),
            _optional_text(payload.get("card_short_link")),
        )
        comment_payload = {
            **payload,
            "card_id": card_identifier,
            "metadata": payload.get("metadata") or {},
        }
        endpoint = self.comment_endpoint(card_id=card_identifier)
        if dry_run:
            return TrelloCardCommentPublishResult(
                status_code=None,
                card_id=card_identifier,
                card_url=_card_url(comment_payload, None),
                comment_id=None,
                dry_run=True,
                payload={
                    **comment_payload,
                    "request": {
                        "method": "POST",
                        "url": endpoint,
                        "params": {"key": self.key, "token": self.token},
                        "json": _trello_card_comment_request(comment_payload),
                    },
                },
            )

        if not self.has_auth:
            raise TrelloCardCommentPublishError(
                "TRELLO_KEY and TRELLO_TOKEN are required for live Trello card comment "
                "publishing; use dry_run to preview"
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    endpoint,
                    params={"key": self.key, "token": self.token},
                    json=_trello_card_comment_request(comment_payload),
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "User-Agent": "max-trello-card-comments-publisher/1",
                    },
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise TrelloCardCommentPublishError(
                    f"Trello card comment publish failed for {endpoint}: {exc}"
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise TrelloCardCommentPublishError(
                f"Trello card comment publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        body = _json_response(response)
        comment_id = body.get("id")
        if not comment_id:
            raise TrelloCardCommentPublishError(
                "Trello card comment publish failed: response did not include created comment id",
                status_code=response.status_code,
            )

        response_card_id = _response_card_id(body) or card_identifier
        card_url = _card_url(comment_payload, body)
        return TrelloCardCommentPublishResult(
            status_code=response.status_code,
            card_id=response_card_id,
            card_url=card_url,
            comment_id=str(comment_id),
            dry_run=False,
            payload={
                **comment_payload,
                "card_id": response_card_id,
                "metadata": {
                    **comment_payload["metadata"],
                    "trello_card_id": response_card_id,
                    "trello_card_comment_id": str(comment_id),
                    "trello_card_url": card_url,
                },
            },
        )

    def _resolve_card_identifier(
        self,
        card_id: str | None = None,
        card_short_link: str | None = None,
    ) -> str:
        return _required_text(
            card_id or self.card_id or card_short_link or self.card_short_link,
            "Trello card_id or card_short_link is required; pass one or set TRELLO_CARD_ID "
            "or TRELLO_CARD_SHORT_LINK",
        )


TrelloCardCommentsPublisher = TrelloCardCommentPublisher


def _trello_card_comment_request(payload: dict[str, Any]) -> dict[str, Any]:
    return {"text": _required_text(payload.get("text"), "Trello comment text is required")}


def _comment_text(
    artifact: dict[str, Any] | str,
    *,
    text: str | None,
    markdown: str | None,
    artifact_title: str | None,
) -> str:
    explicit = _optional_text(text) or _optional_text(markdown)
    if explicit:
        return explicit
    if isinstance(artifact, str):
        return _required_text(artifact, "Trello comment text is required")
    title = _optional_text(artifact_title) or _artifact_title(artifact)
    return "\n".join([f"## {title}", "", _artifact_summary(artifact)])


def _artifact_title(artifact: dict[str, Any]) -> str:
    project = _dict_value(artifact, "project")
    source = _dict_value(artifact, "source")
    return _text_or_placeholder(
        project.get("title")
        or artifact.get("title")
        or source.get("idea_id")
        or source.get("design_brief_id")
        or "Generated Artifact"
    )


def _artifact_summary(artifact: dict[str, Any]) -> str:
    project = _dict_value(artifact, "project")
    source = _dict_value(artifact, "source")
    lines = [
        _text_or_placeholder(project.get("summary") or artifact.get("summary")),
        "",
        "### Source",
        f"- Idea ID: {_text_or_placeholder(source.get('idea_id'))}",
        f"- Design brief ID: {_text_or_placeholder(source.get('design_brief_id'))}",
        f"- Kind: {_text_or_placeholder(artifact.get('kind'))}",
        f"- Schema: {_text_or_placeholder(artifact.get('schema_version'))}",
    ]
    return "\n".join(lines)


def _metadata(
    artifact: dict[str, Any] | str,
    *,
    card_id: str,
    card_short_link: str | None,
) -> dict[str, Any]:
    if not isinstance(artifact, dict):
        return {
            "publisher": "max.trello_card_comments",
            "source_system": "max",
            "source_type": "text",
            "card_id": card_id,
            "card_short_link": card_short_link,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    source = _dict_value(artifact, "source")
    return {
        "publisher": "max.trello_card_comments",
        "source_system": source.get("system", "max"),
        "source_type": source.get("type", "artifact"),
        "idea_id": source.get("idea_id"),
        "design_brief_id": source.get("design_brief_id"),
        "schema_version": artifact.get("schema_version"),
        "kind": artifact.get("kind"),
        "card_id": card_id,
        "card_short_link": card_short_link,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _card_url(payload: dict[str, Any], response_body: dict[str, Any] | None) -> str | None:
    data = response_body.get("data") if isinstance(response_body, dict) else {}
    card = data.get("card") if isinstance(data, dict) else {}
    if isinstance(card, dict):
        for key in ("url", "shortUrl"):
            if card.get(key):
                return str(card[key])
        if card.get("shortLink"):
            return f"https://trello.com/c/{card['shortLink']}"
    if payload.get("card_short_link"):
        return f"https://trello.com/c/{payload['card_short_link']}"
    return None


def _response_card_id(response_body: dict[str, Any]) -> str | None:
    data = response_body.get("data")
    if not isinstance(data, dict):
        return None
    card = data.get("card")
    if not isinstance(card, dict) or not card.get("id"):
        return None
    return str(card["id"])


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _required_text(value: object, message: str) -> str:
    text = str(value).strip() if value else ""
    if not text:
        raise TrelloCardCommentPublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _text_or_placeholder(value: object) -> str:
    text = str(value).strip() if value else ""
    return text or "Not specified"


def _required_url(value: object) -> str:
    try:
        return _required_trello_url(value)
    except Exception as exc:
        raise TrelloCardCommentPublishError(str(exc)) from exc


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = _redact_text(response.text.strip())
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise TrelloCardCommentPublishError(
            "Trello card comment publish failed: response was not valid JSON",
            status_code=response.status_code,
        ) from exc
    return body if isinstance(body, dict) else {}
