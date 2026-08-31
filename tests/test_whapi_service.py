import json

import httpx
import pytest

from app.services.whapi_service import WhapiProviderError, WhapiService


def make_client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler, base_url="https://gate.whapi.cloud")


@pytest.mark.asyncio
async def test_send_text_uses_whapi_contract_and_authorization() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["headers"] = request.headers
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json={"sent": True, "message": {"id": "msg-1"}})

    async with make_client(httpx.MockTransport(handler)) as client:
        result = await WhapiService(client, "https://gate.whapi.cloud", "secret").send_text(
            "+91 86886 64337", "Hello"
        )

    assert result.message_id == "msg-1"
    assert captured["path"] == "/messages/text"
    assert captured["json"] == {"to": "918688664337", "body": "Hello"}
    headers = captured["headers"]
    assert isinstance(headers, httpx.Headers)
    assert headers["authorization"] == "Bearer secret"
    assert headers["content-type"] == "application/json"


@pytest.mark.asyncio
async def test_image_send_uses_image_endpoint_and_caption() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"messages": [{"id": "image-1"}]})

    async with make_client(httpx.MockTransport(handler)) as client:
        result = await WhapiService(
            client, "https://gate.whapi.cloud", "secret"
        ).send_image(
            "918688664337",
            "https://files.test/architecture.png",
            caption="Architecture overview of the voice sales agent.",
        )

    assert result.message_id == "image-1"
    assert requests[0].url.path == "/messages/image"
    assert json.loads(requests[0].content) == {
        "to": "918688664337",
        "media": "https://files.test/architecture.png",
        "caption": "Architecture overview of the voice sales agent.",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 500])
async def test_provider_http_failure_is_sanitized(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="provider detail containing secret")

    async with make_client(httpx.MockTransport(handler)) as client:
        with pytest.raises(WhapiProviderError) as error:
            await WhapiService(client, "https://gate.whapi.cloud", "secret").send_text(
                "8688664337", "Hello"
            )

    assert str(error.value) == "whapi_request_failed"
    assert "secret" not in str(error.value)


@pytest.mark.asyncio
async def test_missing_message_id_is_a_sanitized_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"sent": True})

    async with make_client(httpx.MockTransport(handler)) as client:
        with pytest.raises(WhapiProviderError, match="whapi_invalid_response"):
            await WhapiService(client, "https://gate.whapi.cloud", "secret").send_text(
                "8688664337", "Hello"
            )
