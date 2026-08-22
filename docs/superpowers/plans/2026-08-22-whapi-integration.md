# Whapi WhatsApp Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a minimal FastAPI service that sends contextual mid-call WhatsApp messages and reusable follow-up attachments through Whapi.

**Architecture:** FastAPI owns request validation and dependency wiring, while a focused asynchronous `WhapiService` owns provider payloads, authentication, response parsing, and sanitized errors. Pure helpers normalize Indian numbers and compose messages; an isolated concurrency-safe in-memory store prevents duplicate successful sends per Sarvam call ID.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic Settings, HTTPX, Uvicorn, pytest, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-08-22-whapi-integration-design.md`

## Global Constraints

- Use Whapi only; do not add Twilio.
- Use `WHAPI_BASE_URL=https://gate.whapi.cloud` and `WHAPI_TOKEN` from environment variables.
- Never hardcode or log the Whapi token or Authorization header.
- Do not add database models, callback scheduling, Sarvam agent changes, containers, or unrelated features.
- Tests must mock HTTP and must never call Whapi.
- Provider failures must return `{ "success": false, "error": "whapi_send_failed" }` without raw exceptions.

---

### Task 1: Project foundation, configuration, and phone normalization

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `app/utils/__init__.py`
- Create: `app/utils/phone.py`
- Create: `tests/test_phone.py`

**Interfaces:**
- Produces: `Settings(whapi_base_url: str, whapi_token: SecretStr)` and `normalize_indian_phone(phone: str) -> str`.

- [ ] **Step 1: Add failing phone normalization tests**

```python
import pytest
from app.utils.phone import PhoneNumberError, normalize_indian_phone

@pytest.mark.parametrize("raw", ["+91 86886 64337", "8688664337", "918688664337"])
def test_normalizes_supported_indian_formats(raw: str) -> None:
    assert normalize_indian_phone(raw) == "918688664337"

@pytest.mark.parametrize("raw", ["", "12345", "108688664337", "+1 8688664337"])
def test_rejects_malformed_or_non_indian_numbers(raw: str) -> None:
    with pytest.raises(PhoneNumberError):
        normalize_indian_phone(raw)
```

- [ ] **Step 2: Run `pytest tests/test_phone.py -v` and confirm import failure**
- [ ] **Step 3: Add pinned runtime/test dependencies, environment configuration, `.env` ignore rule, and a strict normalizer that strips spaces, parentheses, and hyphens, accepts only ten Indian subscriber digits or `91` plus ten digits, and returns the twelve-digit form**
- [ ] **Step 4: Run `pytest tests/test_phone.py -v` and confirm all cases pass**

### Task 2: Whapi provider and attachment helpers

**Files:**
- Create: `app/services/__init__.py`
- Create: `app/services/whapi_service.py`
- Create: `tests/test_whapi_service.py`

**Interfaces:**
- Consumes: `normalize_indian_phone(phone: str) -> str`.
- Produces: `WhapiResult(success: bool, message_id: str | None, error: str | None)`, `WhapiService.send_text`, `send_image`, `send_document`, `send_resume`, `send_architecture_image`, and `send_final_followup`.

- [ ] **Step 1: Write mocked HTTPX tests asserting bearer headers and these exact payload shapes**

```python
{"to": "918688664337", "body": "Hello"}
{"to": "918688664337", "media": "https://files.test/architecture.png", "caption": "Architecture overview of the voice sales agent."}
{"to": "918688664337", "media": "https://files.test/resume.pdf", "filename": "Parv_Agarwal_Resume.pdf"}
```

- [ ] **Step 2: Run `pytest tests/test_whapi_service.py -v` and confirm the missing service failure**
- [ ] **Step 3: Implement one reusable `httpx.AsyncClient`, JSON headers, explicit timeouts, endpoint-specific payload builders, defensive message-ID extraction from `message.id`, top-level `id`, or `messages[0].id`, and a sanitized `WhapiProviderError`**
- [ ] **Step 4: Add tests proving HTTP 4xx/5xx, timeout, and missing message ID return a sanitized failure without leaking response bodies or credentials**
- [ ] **Step 5: Implement `send_final_followup` to call text, resume, and architecture methods sequentially, catch each provider error separately, continue, and return `success`, `text_sent`, `resume_sent`, and `architecture_sent`**
- [ ] **Step 6: Run `pytest tests/test_whapi_service.py -v` and confirm all service tests pass**

### Task 3: Message composition and idempotent FastAPI endpoint

**Files:**
- Create: `app/schemas/__init__.py`
- Create: `app/schemas/whatsapp.py`
- Create: `app/services/message_builder.py`
- Create: `app/services/idempotency.py`
- Create: `app/api/__init__.py`
- Create: `app/api/tools.py`
- Create: `app/main.py`
- Create: `tests/test_message_builder.py`
- Create: `tests/test_high_intent_endpoint.py`

**Interfaces:**
- Consumes: `WhapiService.send_text(phone: str, text: str)`.
- Produces: `build_high_intent_message(request) -> str`, `InMemoryIdempotencyStore.run_once(call_id, operation)`, and `POST /tools/send-high-intent-whatsapp`.

- [ ] **Step 1: Write message-builder tests showing that only present fields appear and that HOT/WARM/COLD, scores, metadata, and invented names never appear**
- [ ] **Step 2: Write endpoint tests for successful delivery, exact structured provider failure, sequential duplicate calls, concurrent duplicate calls, and retry after failure**
- [ ] **Step 3: Run the focused tests and confirm they fail because the modules are absent**
- [ ] **Step 4: Implement Pydantic request fields exactly as specified, with non-empty `call_id` and `phone`, optional context fields, and a default empty `required_features` list**
- [ ] **Step 5: Implement concise paragraph-based copy using only supplied values and a generic `Hi,` greeting**
- [ ] **Step 6: Implement a per-call in-flight task/future registry plus a successful-ID set protected by `asyncio.Lock`; successful sends become cached, failures are removed so callers can retry**
- [ ] **Step 7: Implement FastAPI lifespan wiring for settings, HTTPX, Whapi service, and idempotency store; add `/health`; return HTTP 200 structured tool results for provider outcomes**
- [ ] **Step 8: Run `pytest tests/test_message_builder.py tests/test_high_intent_endpoint.py -v` and confirm all endpoint tests pass**

### Task 4: Full verification and operator documentation

**Files:**
- Create: `README.md`
- Modify: `.env.example`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: the complete FastAPI application.
- Produces: reproducible setup, test, run, and manual Whapi verification instructions.

- [ ] **Step 1: Add README commands for virtual-environment setup, dependency installation, copying `.env.example` to `.env`, `uvicorn app.main:app --reload`, pytest, and sample `Invoke-RestMethod` calls**
- [ ] **Step 2: Document that in-memory idempotency resets on restart and requires a single worker for this prototype**
- [ ] **Step 3: Run `pytest -v` and confirm the complete suite passes without external HTTP**
- [ ] **Step 4: Run `python -m compileall app tests` and confirm all modules compile**
- [ ] **Step 5: Start the app without a real token only for health verification, call `GET /health`, and confirm `{ "status": "ok" }`**
- [ ] **Step 6: Review `.env.example`, logs, test fixtures, and repository search results to confirm no credentials were committed**
- [ ] **Step 7: Report that real text/PDF/image delivery remains a manual acceptance step requiring the user's `WHAPI_TOKEN` and reachable media references**
