"""Trello checklist item publisher for generated action items."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher.trello_cards import (
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_TRELLO_API_URL,
    _redact_text,
)
from max.publisher.trello_cards import _required_url as _required_trello_url


class TrelloChecklistItemPublishError(RuntimeError):
    """Raised when a Trello checklist item publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(_redact_text(message))
        self.status_code = status_code


@dataclass(frozen=True)
class TrelloChecklistItemPayload:
    """Trello checklist item creation payload."""

    card_id: str
    checklist_id: str
    name: str
    checked: bool
    position: str | float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable checklist item payload preview."""
        payload: dict[str, Any] = {
            "card_id": self.card_id,
            "checklist_id": self.checklist_id,
            "name": self.name,
            "checked": self.checked,
        }
        if self.position is not None:
            payload["pos"] = self.position
        return payload


@dataclass(frozen=True)
class TrelloChecklistItemPublishResult:
    """Summary of a Trello checklist item publish or dry run."""

    status_code: int | None
    provider: str
    card_id: str
    checklist_id: str
    check_item_id: str | None
    name: str
    state: str
    dry_run: bool
    payload: dict[str, Any]


class TrelloChecklistItemPublisher:
    """Create checklist items on existing Trello checklists."""

    def __init__(
        self,
        *,
        card_id: str | None = None,
        checklist_id: str | None = None,
        key: str | None = None,
        token: str | None = None,
        api_url: str = DEFAULT_TRELLO_API_URL,
        name: str | None = None,
        checked: bool = False,
        position: str | float | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.card_id = _optional_text(card_id)
        self.checklist_id = _optional_text(checklist_id)
        self.key = _optional_text(key)
        self.token = _optional_text(token)
        self.api_url = _required_url(api_url)
        self.name = _optional_text(name)
        self.checked = bool(checked)
        self.position = _optional_position(position)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        card_id: str | None = None,
        checklist_id: str | None = None,
        key: str | None = None,
        token: str | None = None,
        api_url: str | None = None,
        name: str | None = None,
        checked: bool = False,
        position: str | float | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> TrelloChecklistItemPublisher:
        """Create a publisher using API values first, then environment variables."""
        return cls(
            card_id=card_id or os.getenv("TRELLO_CARD_ID"),
            checklist_id=checklist_id or os.getenv("TRELLO_CHECKLIST_ID"),
            key=key or os.getenv("TRELLO_KEY"),
            token=token or os.getenv("TRELLO_TOKEN"),
            api_url=api_url or os.getenv("TRELLO_API_URL", DEFAULT_TRELLO_API_URL),
            name=name,
            checked=checked,
            position=position,
            timeout=timeout,
            client=client,
        )

    def checklist_item_endpoint(self, *, checklist_id: str | None = None) -> str:
        """Return the Trello REST endpoint used for checklist item creation."""
        return f"{self.api_url}/checklists/{self._resolve_checklist_id(checklist_id)}/checkItems"

    def build_checklist_item_payload(
        self,
        *,
        card_id: str | None = None,
        checklist_id: str | None = None,
        name: str | None = None,
        checked: bool | None = None,
        position: str | float | None = None,
    ) -> TrelloChecklistItemPayload:
        """Build and validate a Trello checklist item payload."""
        return TrelloChecklistItemPayload(
            card_id=self._resolve_card_id(card_id),
            checklist_id=self._resolve_checklist_id(checklist_id),
            name=_required_text(name or self.name, "Trello checklist item name is required"),
            checked=self.checked if checked is None else bool(checked),
            position=_optional_position(position) if position is not None else self.position,
        )

    def publish(
        self,
        *,
        dry_run: bool = True,
        card_id: str | None = None,
        checklist_id: str | None = None,
        name: str | None = None,
        checked: bool | None = None,
        position: str | float | None = None,
    ) -> TrelloChecklistItemPublishResult:
        """Create a checklist item in Trello or return the intended request."""
        self._validate_auth()
        payload = self.build_checklist_item_payload(
            card_id=card_id,
            checklist_id=checklist_id,
            name=name,
            checked=checked,
            position=position,
        ).to_dict()
        endpoint = self.checklist_item_endpoint(checklist_id=payload["checklist_id"])
        request_json = _trello_checklist_item_request(payload)

        if dry_run:
            return TrelloChecklistItemPublishResult(
                status_code=None,
                provider="trello",
                card_id=payload["card_id"],
                checklist_id=payload["checklist_id"],
                check_item_id=None,
                name=payload["name"],
                state=_state_from_checked(payload["checked"]),
                dry_run=True,
                payload={
                    **payload,
                    "request": {
                        "method": "POST",
                        "url": endpoint,
                        "params": {"key": self.key, "token": self.token},
                        "json": request_json,
                    },
                },
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    endpoint,
                    params={"key": self.key, "token": self.token},
                    json=request_json,
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "User-Agent": "max-trello-checklist-items-publisher/1",
                    },
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise TrelloChecklistItemPublishError(
                    f"Trello checklist item publish failed for {endpoint}: {exc}"
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise TrelloChecklistItemPublishError(
                f"Trello checklist item publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        body = _json_response(response)
        check_item_id = body.get("id")
        if not check_item_id:
            raise TrelloChecklistItemPublishError(
                "Trello checklist item publish failed: response did not include created check item id",
                status_code=response.status_code,
            )

        response_name = _optional_text(body.get("name")) or payload["name"]
        response_state = _optional_text(body.get("state")) or _state_from_checked(payload["checked"])
        return TrelloChecklistItemPublishResult(
            status_code=response.status_code,
            provider="trello",
            card_id=payload["card_id"],
            checklist_id=payload["checklist_id"],
            check_item_id=str(check_item_id),
            name=response_name,
            state=response_state,
            dry_run=False,
            payload={
                **payload,
                "check_item_id": str(check_item_id),
                "name": response_name,
                "state": response_state,
            },
        )

    def _resolve_card_id(self, card_id: str | None = None) -> str:
        return _required_text(card_id or self.card_id, "Trello card_id is required")

    def _resolve_checklist_id(self, checklist_id: str | None = None) -> str:
        return _required_text(checklist_id or self.checklist_id, "Trello checklist_id is required")

    def _validate_auth(self) -> None:
        _required_text(self.key, "Trello key is required")
        _required_text(self.token, "Trello token is required")


TrelloChecklistItemsPublisher = TrelloChecklistItemPublisher


def _trello_checklist_item_request(payload: dict[str, Any]) -> dict[str, Any]:
    request: dict[str, Any] = {
        "name": _required_text(payload.get("name"), "Trello checklist item name is required"),
        "checked": bool(payload.get("checked")),
    }
    if payload.get("pos") is not None:
        request["pos"] = payload["pos"]
    return request


def _state_from_checked(checked: bool) -> str:
    return "complete" if checked else "incomplete"


def _required_text(value: object, message: str) -> str:
    text = str(value).strip() if value else ""
    if not text:
        raise TrelloChecklistItemPublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _optional_position(value: object) -> str | float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip()
    return text or None


def _required_url(value: object) -> str:
    try:
        return _required_trello_url(value)
    except Exception as exc:
        raise TrelloChecklistItemPublishError(str(exc)) from exc


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = _redact_text(response.text.strip())
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise TrelloChecklistItemPublishError(
            "Trello checklist item publish failed: response was not valid JSON",
            status_code=response.status_code,
        ) from exc
    return body if isinstance(body, dict) else {}
