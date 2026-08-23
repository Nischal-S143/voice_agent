from __future__ import annotations

import pytest
from pydantic import SecretStr

from app.config import Settings
from app.services.outbound_caller import (
    OutboundCallRequest,
    SarvamHttpOutboundCaller,
    _app_version,
    _extract_call_id,
)


class FakeResponse:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> object:
        return self._payload


class FakeClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[dict] = []

    async def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.response


def _settings() -> Settings:
    return Settings(
        sarvam_api_key=SecretStr("key"),
        sarvam_org_id="ORG",
        sarvam_workspace_id="WS",
        sarvam_app_id="Conversatio-31edc5ba-a73e",
        sarvam_app_version="v1",
        sarvam_connection_id="CONN",
        sarvam_agent_phone_number="+917971442803",
    )


def _request() -> OutboundCallRequest:
    return OutboundCallRequest(
        callback_id=7,
        phone="919999999999",
        context={"is_callback": True, "previous_features": ["COD", "UPI"], "empty": None},
    )


@pytest.mark.parametrize(
    ("raw", "expected"), [("v1", 1), ("1", 1), ("v12", 12), ("", None)]
)
def test_app_version_coerces_label_to_integer(raw: str, expected: int | None) -> None:
    assert _app_version(raw) == expected


def test_extract_call_id_prefers_attempt_id() -> None:
    assert _extract_call_id({"attempt_id": "att_1"}) == "att_1"
    assert _extract_call_id({"data": {"attempt_id": "att_2"}}) == "att_2"
    assert _extract_call_id({"nothing": "here"}) is None


async def test_place_call_sends_integer_version_and_flattened_variables() -> None:
    client = FakeClient(FakeResponse(200, {"attempt_id": "att_9"}))
    caller = SarvamHttpOutboundCaller(client, _settings())

    result = await caller.place_call(_request())

    assert result.success is True
    assert result.call_id == "att_9"
    body = client.calls[0]["json"]
    assert body["app_config"]["app_version"] == 1
    assert body["user_config"]["user_phone_number"] == "+919999999999"
    variables = body["app_config"]["agent_variables"]
    assert variables["is_callback"] == "true"
    assert variables["previous_features"] == "COD, UPI"
    assert variables["callback_id"] == "7"
    assert "empty" not in variables


async def test_place_call_marks_server_errors_retryable() -> None:
    caller = SarvamHttpOutboundCaller(FakeClient(FakeResponse(503, {})), _settings())
    result = await caller.place_call(_request())
    assert (result.success, result.retryable) == (False, True)


async def test_place_call_marks_rejections_permanent() -> None:
    caller = SarvamHttpOutboundCaller(FakeClient(FakeResponse(422, {})), _settings())
    result = await caller.place_call(_request())
    assert (result.success, result.retryable) == (False, False)
    assert result.error == "sarvam_outbound_rejected"


async def test_place_call_keeps_insufficient_balance_retryable() -> None:
    caller = SarvamHttpOutboundCaller(FakeClient(FakeResponse(402, {})), _settings())
    result = await caller.place_call(_request())
    assert (result.success, result.retryable) == (False, True)
    assert result.error == "sarvam_outbound_insufficient_balance"


async def test_place_call_requests_latest_when_no_version_is_pinned() -> None:
    settings = _settings()
    settings.sarvam_app_version = ""
    client = FakeClient(FakeResponse(200, {"attempt_id": "att_1"}))

    await SarvamHttpOutboundCaller(client, settings).place_call(_request())

    app_config = client.calls[0]["json"]["app_config"]
    assert app_config["version_filter"] == "latest"
    assert "app_version" not in app_config


async def test_place_call_pins_a_specific_version_when_one_is_configured() -> None:
    client = FakeClient(FakeResponse(200, {"attempt_id": "att_1"}))

    await SarvamHttpOutboundCaller(client, _settings()).place_call(_request())

    app_config = client.calls[0]["json"]["app_config"]
    assert app_config["version_filter"] == "specific"
    assert app_config["app_version"] == 1
