from __future__ import annotations

import httpx
import pytest

from max.publisher.salesforce_cases import SalesforceCasePublishError, SalesforceCasePublisher
from tests.test_zoom_team_chat_messages_publisher import _spec


def test_subject_and_description_are_required_and_normalized() -> None:
    payload = SalesforceCasePublisher().build_case_payload(_spec()).to_dict()
    assert payload["Subject"].endswith("Zoom Chat Publisher")
    assert "Publish Max ideas" in payload["Description"]
    payload = SalesforceCasePublisher().build_case_payload(_spec(), custom_fields={"Priority": "High", "External_Id__c": "ext"}).to_dict()
    assert payload["Priority"] == "Medium"
    assert payload["External_Id__c"] == "ext"


def test_success_dry_run_and_api_failure_paths() -> None:
    assert SalesforceCasePublisher().publish(_spec()).dry_run is True
    publisher = SalesforceCasePublisher(instance_url="https://sf.example", access_token="tok", client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(201, json={"id": "case"}))))
    assert publisher.publish(_spec(), dry_run=False).case_id == "case"
    failing = SalesforceCasePublisher(instance_url="https://sf.example", access_token="tok", client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(400, text="bad tok"))))
    with pytest.raises(SalesforceCasePublishError) as exc:
        failing.publish(_spec(), dry_run=False)
    assert "tok" not in str(exc.value)
