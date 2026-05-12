"""Miro board card publisher for generated TactSpec previews."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, markdown_summary, metadata, optional_text, quote_path, required_text, required_url, response_json, response_preview, title, validate_tact_spec

DEFAULT_API_URL = "https://api.miro.com"
DEFAULT_POSITION = {"x": 0, "y": 0}


class MiroBoardCardPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class MiroBoardCardPayload:
    board_id: str
    card: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"board_id": self.board_id, "card": self.card, "metadata": self.metadata}


@dataclass(frozen=True)
class MiroBoardCardPublishResult:
    status_code: int | None
    card_id: str | None
    card_link: str | None
    dry_run: bool
    payload: dict[str, Any]


class MiroBoardCardPublisher:
    def __init__(self, *, board_id: str | None = None, access_token: str | None = None, api_url: str = DEFAULT_API_URL, position: dict[str, float] | None = None, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> None:
        self.board_id = optional_text(board_id)
        self.access_token = optional_text(access_token)
        self.api_url = required_url(api_url, "Miro api_url must be an absolute http(s) URL")
        self.position = position or DEFAULT_POSITION
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, *, board_id: str | None = None, access_token: str | None = None, api_url: str | None = None, position: dict[str, float] | None = None, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> MiroBoardCardPublisher:
        return cls(board_id=board_id or os.getenv("MIRO_BOARD_ID"), access_token=access_token or os.getenv("MIRO_ACCESS_TOKEN"), api_url=api_url or os.getenv("MIRO_API_URL", DEFAULT_API_URL), position=position, timeout=timeout, client=client)

    @property
    def cards_endpoint(self) -> str:
        board_id = required_text(self.board_id, "MIRO_BOARD_ID is required for Miro board card publishing")
        return f"{self.api_url}/v2/boards/{quote_path(board_id)}/cards"

    def build_card_payload(self, tact_spec: dict[str, Any], *, board_id: str | None = None) -> MiroBoardCardPayload:
        try:
            validate_tact_spec(tact_spec, label="Miro board card")
            resolved_board_id = required_text(optional_text(board_id) or self.board_id, "MIRO_BOARD_ID is required for Miro board card publishing")
        except ValueError as exc:
            raise MiroBoardCardPublishError(str(exc)) from exc
        meta = metadata(tact_spec, publisher="max.miro_board_cards")
        card = {
            "data": {"title": title(tact_spec), "description": markdown_summary(tact_spec, meta)},
            "position": self.position,
            "style": {"cardTheme": "#2D9BF0"},
        }
        return MiroBoardCardPayload(resolved_board_id, card, meta)

    def publish(self, tact_spec: dict[str, Any], *, dry_run: bool = True, board_id: str | None = None) -> MiroBoardCardPublishResult:
        payload = self.build_card_payload(tact_spec, board_id=board_id).to_dict()
        if dry_run:
            return MiroBoardCardPublishResult(None, None, None, True, payload)
        if not self.access_token:
            raise MiroBoardCardPublishError("MIRO_ACCESS_TOKEN is required for live Miro board card publishing; use dry_run to preview")
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(self.cards_endpoint, json=payload["card"], headers={"Authorization": f"Bearer {self.access_token}", "Accept": "application/json", "Content-Type": "application/json", "User-Agent": "max-miro-board-cards-publisher/1"}, timeout=self.timeout)
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise MiroBoardCardPublishError(f"Miro board card publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.access_token])}", status_code=response.status_code)
        body = response_json(response, MiroBoardCardPublishError, "Miro board card publish failed: response was not valid JSON")
        return MiroBoardCardPublishResult(response.status_code, optional_text(body.get("id")), optional_text(body.get("viewLink")), False, payload)


MiroBoardCardsPublisher = MiroBoardCardPublisher
