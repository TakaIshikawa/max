"""Basecamp todo publisher for Max buildable units."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, optional_text, redact_text, required_text, required_url, response_json, response_preview
from max.publisher.stripe_customer_notes import _RETRYABLE_STATUS_CODES, _unit_fields

DEFAULT_API_URL = "https://3.basecampapi.com"


class BasecampTodoPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class BasecampTodoPayload:
    account_id: str
    project_id: str
    todolist_id: str
    title: str
    description: str
    metadata: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {"account_id": self.account_id, "project_id": self.project_id, "todolist_id": self.todolist_id, "title": self.title, "description": self.description, "metadata": self.metadata}

    def to_request_json(self) -> dict[str, str]:
        return {"content": self.title, "description": self.description}


@dataclass(frozen=True)
class BasecampTodoPublishResult:
    status_code: int | None
    todo_id: str | None
    todo_url: str | None
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]


class BasecampTodoPublisher:
    def __init__(
        self,
        *,
        account_id: str | None = None,
        project_id: str | None = None,
        todolist_id: str | None = None,
        token: str | None = None,
        api_url: str = DEFAULT_API_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = 2,
        client: httpx.Client | None = None,
    ) -> None:
        self.account_id = optional_text(account_id)
        self.project_id = optional_text(project_id)
        self.todolist_id = optional_text(todolist_id)
        self.token = optional_text(token)
        self.api_url = required_url(api_url, "Basecamp api_url must be an absolute http(s) URL")
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> BasecampTodoPublisher:
        return cls(
            account_id=kwargs.pop("account_id", None) or os.getenv("BASECAMP_ACCOUNT_ID"),
            project_id=kwargs.pop("project_id", None) or os.getenv("BASECAMP_PROJECT_ID"),
            todolist_id=kwargs.pop("todolist_id", None) or os.getenv("BASECAMP_TODOLIST_ID"),
            token=kwargs.pop("token", None) or os.getenv("BASECAMP_ACCESS_TOKEN"),
            api_url=kwargs.pop("api_url", None) or os.getenv("BASECAMP_API_URL", DEFAULT_API_URL),
            **kwargs,
        )

    @property
    def todos_endpoint(self) -> str:
        account_id = required_text(self.account_id, "BASECAMP_ACCOUNT_ID is required for Basecamp todo publishing")
        project_id = required_text(self.project_id, "BASECAMP_PROJECT_ID is required for Basecamp todo publishing")
        todolist_id = required_text(self.todolist_id, "BASECAMP_TODOLIST_ID is required for Basecamp todo publishing")
        return f"{self.api_url}/{quote(account_id, safe='')}/buckets/{quote(project_id, safe='')}/todolists/{quote(todolist_id, safe='')}/todos.json"

    def build_todo_payload(self, unit: dict[str, Any]) -> BasecampTodoPayload:
        fields = _unit_fields(unit)
        account_id = required_text(self.account_id, "BASECAMP_ACCOUNT_ID is required for Basecamp todo publishing")
        project_id = required_text(self.project_id, "BASECAMP_PROJECT_ID is required for Basecamp todo publishing")
        todolist_id = required_text(self.todolist_id, "BASECAMP_TODOLIST_ID is required for Basecamp todo publishing")
        metadata = {"publisher": "max.basecamp_todos", "idea_id": fields["idea_id"], "status": fields["status"], "category": fields["category"], "score": fields["score"]}
        return BasecampTodoPayload(account_id, project_id, todolist_id, f"Validate Max idea: {fields['title']}", _description(fields, unit), metadata)

    def publish(self, unit: dict[str, Any], *, dry_run: bool = True) -> BasecampTodoPublishResult:
        payload = self.build_todo_payload(unit)
        payload_dict = payload.to_dict()
        endpoint = self.todos_endpoint
        if dry_run:
            return BasecampTodoPublishResult(None, None, None, True, endpoint, payload_dict)
        if not self.token:
            raise BasecampTodoPublishError("BASECAMP_ACCESS_TOKEN is required for live Basecamp todo publishing; use dry_run to preview")
        response = self._post_with_retries(endpoint, payload.to_request_json())
        body = response_json(response, BasecampTodoPublishError, "Basecamp todo publish failed: response was not valid JSON")
        todo_id = optional_text(body.get("id"))
        todo_url = optional_text(body.get("app_url")) or optional_text(body.get("url"))
        return BasecampTodoPublishResult(response.status_code, todo_id, todo_url, False, endpoint, payload_dict)

    def _post_with_retries(self, endpoint: str, request_json: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response: httpx.Response | None = None
            for attempt in range(self.max_retries + 1):
                response = client.post(endpoint, json=request_json, headers=self._headers(), timeout=self.timeout)
                if response.status_code not in _RETRYABLE_STATUS_CODES or attempt >= self.max_retries:
                    break
            assert response is not None
            if not 200 <= response.status_code < 300:
                raise BasecampTodoPublishError(
                    f"Basecamp todo publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.token])}",
                    status_code=response.status_code,
                    token=self.token,
                )
            return response
        finally:
            if close_client:
                client.close()

    def _headers(self) -> dict[str, str]:
        assert self.token is not None
        return {"Accept": "application/json", "Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "User-Agent": "max-basecamp-todos-publisher/1"}


BasecampTodosPublisher = BasecampTodoPublisher


def _description(fields: dict[str, str], unit: dict[str, Any]) -> str:
    execution = unit.get("execution") if isinstance(unit.get("execution"), dict) else {}
    validation_plan = optional_text(execution.get("validation_plan")) or optional_text(unit.get("validation_plan")) or "Not specified"
    return "\n".join(
        [
            f"Idea ID: {fields['idea_id']}",
            f"Status: {fields['status']}",
            f"Category: {fields['category']}",
            f"Score: {fields['score']}",
            "",
            f"Problem: {fields['problem']}",
            f"Solution: {fields['solution']}",
            f"Validation plan: {validation_plan}",
        ]
    )
