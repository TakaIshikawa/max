"""Basecamp message board publisher for Max buildable units."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, optional_text, redact_text, required_text, required_url, response_json, response_preview
from max.publisher.stripe_customer_notes import _RETRYABLE_STATUS_CODES, _unit_fields

DEFAULT_API_URL = "https://3.basecampapi.com"


class BasecampMessagePublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class BasecampMessagePayload:
    account_id: str
    project_id: str
    message_board_id: str
    subject: str
    content: str
    metadata: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {"account_id": self.account_id, "project_id": self.project_id, "message_board_id": self.message_board_id, "subject": self.subject, "content": self.content, "metadata": self.metadata}

    def to_request_json(self) -> dict[str, str]:
        return {"subject": self.subject, "content": self.content}


@dataclass(frozen=True)
class BasecampMessagePublishResult:
    status_code: int | None
    message_id: str | None
    message_url: str | None
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class BasecampMessagePublisher:
    def __init__(self, *, account_id: str | None = None, project_id: str | None = None, message_board_id: str | None = None, token: str | None = None, api_url: str = DEFAULT_API_URL, timeout: float = DEFAULT_TIMEOUT_SECONDS, max_retries: int = 2, client: httpx.Client | None = None) -> None:
        self.account_id = optional_text(account_id)
        self.project_id = optional_text(project_id)
        self.message_board_id = optional_text(message_board_id)
        self.token = optional_text(token)
        self.api_url = required_url(api_url, "Basecamp api_url must be an absolute http(s) URL")
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> BasecampMessagePublisher:
        return cls(account_id=kwargs.pop("account_id", None) or os.getenv("BASECAMP_ACCOUNT_ID"), project_id=kwargs.pop("project_id", None) or os.getenv("BASECAMP_PROJECT_ID"), message_board_id=kwargs.pop("message_board_id", None) or os.getenv("BASECAMP_MESSAGE_BOARD_ID"), token=kwargs.pop("token", None) or os.getenv("BASECAMP_ACCESS_TOKEN"), api_url=kwargs.pop("api_url", None) or os.getenv("BASECAMP_API_URL", DEFAULT_API_URL), **kwargs)

    @property
    def messages_endpoint(self) -> str:
        account_id = required_text(self.account_id, "BASECAMP_ACCOUNT_ID is required for Basecamp message publishing")
        project_id = required_text(self.project_id, "BASECAMP_PROJECT_ID is required for Basecamp message publishing")
        board_id = required_text(self.message_board_id, "BASECAMP_MESSAGE_BOARD_ID is required for Basecamp message publishing")
        return f"{self.api_url}/{quote(account_id, safe='')}/buckets/{quote(project_id, safe='')}/message_boards/{quote(board_id, safe='')}/messages.json"

    def build_message_payload(self, unit: dict[str, Any]) -> BasecampMessagePayload:
        fields = _unit_fields(unit)
        account_id = required_text(self.account_id, "BASECAMP_ACCOUNT_ID is required for Basecamp message publishing")
        project_id = required_text(self.project_id, "BASECAMP_PROJECT_ID is required for Basecamp message publishing")
        board_id = required_text(self.message_board_id, "BASECAMP_MESSAGE_BOARD_ID is required for Basecamp message publishing")
        metadata = {"publisher": "max.basecamp_messages", "idea_id": fields["idea_id"], "status": fields["status"], "category": fields["category"], "score": fields["score"]}
        return BasecampMessagePayload(account_id, project_id, board_id, f"Max idea: {fields['title']}", _content(fields, unit), metadata)

    def publish(self, unit: dict[str, Any], *, dry_run: bool = True) -> BasecampMessagePublishResult:
        payload = self.build_message_payload(unit)
        endpoint = self.messages_endpoint
        if dry_run:
            return BasecampMessagePublishResult(None, None, None, True, endpoint, payload.to_dict())
        if not self.token:
            raise BasecampMessagePublishError("BASECAMP_ACCESS_TOKEN is required for live Basecamp message publishing; use dry_run to preview")
        response = self._post_with_retries(endpoint, payload.to_request_json())
        body = response_json(response, BasecampMessagePublishError, "Basecamp message publish failed: response was not valid JSON")
        return BasecampMessagePublishResult(response.status_code, optional_text(body.get("id")), optional_text(body.get("app_url")) or optional_text(body.get("url")), False, endpoint, payload.to_dict(), body)

    def _post_with_retries(self, endpoint: str, payload: dict[str, str]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            last_response: httpx.Response | None = None
            for attempt in range(self.max_retries + 1):
                response = client.post(endpoint, json=payload, headers=self._headers(), timeout=self.timeout)
                last_response = response
                if response.status_code not in _RETRYABLE_STATUS_CODES or attempt >= self.max_retries:
                    break
            assert last_response is not None
            if not 200 <= last_response.status_code < 300:
                raise BasecampMessagePublishError(f"Basecamp message publish failed with HTTP {last_response.status_code}: {response_preview(last_response, secrets=[self.token])}", status_code=last_response.status_code, token=self.token)
            return last_response
        finally:
            if close_client:
                client.close()

    def _headers(self) -> dict[str, str]:
        assert self.token is not None
        return {"Accept": "application/json", "Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "User-Agent": "max-basecamp-messages-publisher/1"}


BasecampMessagesPublisher = BasecampMessagePublisher


def _content(fields: dict[str, str], unit: dict[str, Any]) -> str:
    evidence = unit.get("evidence") if isinstance(unit.get("evidence"), dict) else {}
    links = evidence.get("links") if isinstance(evidence.get("links"), list) else []
    link_text = "\n".join(f"- {link}" for link in links) if links else "None"
    return "\n".join(["<h1>" + fields["title"] + "</h1>", f"<p>{fields['category']} / {fields['status']} / score {fields['score']}</p>", f"<h2>Problem</h2><p>{fields['problem']}</p>", f"<h2>Solution</h2><p>{fields['solution']}</p>", f"<h2>Evidence links</h2><pre>{link_text}</pre>"])
