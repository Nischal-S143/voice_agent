# Whapi WhatsApp Integration Design

## Scope

Build only the WhatsApp integration required by the existing Sarvam voice agent. Whapi replaces Twilio. This slice does not create or modify a Sarvam agent and does not add database persistence, callback scheduling, containers, or unrelated backend features.

## Application Structure

Create a minimal asynchronous FastAPI application with:

- a health endpoint for local verification;
- `POST /tools/send-high-intent-whatsapp` for Sarvam's existing high-intent tool;
- request and response schemas;
- a Whapi provider service;
- Indian phone-number normalization;
- an isolated in-memory idempotency store;
- message-composition helpers;
- unit and endpoint tests using mocked HTTP responses.

The HTTP route handles validation and response shaping. Provider-specific payloads and response parsing remain inside `WhapiService`. FastAPI lifespan owns one reusable `httpx.AsyncClient` so requests do not create a new connection pool during a live call.

## Configuration

Configuration is loaded from environment variables:

```env
WHAPI_BASE_URL=https://gate.whapi.cloud
WHAPI_TOKEN=
```

The token is mandatory at runtime and is never hardcoded, returned to callers, or written to logs. `.env` remains ignored; `.env.example` documents configuration without credentials.

## Phone Numbers

The normalizer accepts these equivalent Indian formats:

- `+91 86886 64337`
- `8688664337`
- `918688664337`

It removes conventional separators, validates the Indian country code and ten-digit subscriber number, and returns `918688664337`. Malformed or unsupported numbers fail validation before any provider request.

## Whapi Provider Service

`app/services/whapi_service.py` exposes asynchronous operations equivalent to:

- `send_text(phone, text)` using `POST /messages/text`;
- `send_image(phone, image, caption=None)` using `POST /messages/image`;
- `send_document(phone, document, filename=None, caption=None)` using `POST /messages/document`;
- `send_resume(phone, document)` with filename `Parv_Agarwal_Resume.pdf`;
- `send_architecture_image(phone, image)` with the approved architecture caption;
- `send_final_followup(phone, message, resume, architecture_image)`.

Every provider request sends JSON, `Authorization: Bearer <token>`, and `Content-Type: application/json`. Payload construction and message-ID extraction are centralized. Explicit connection and response timeouts prevent a provider stall from blocking a live Sarvam conversation indefinitely.

The final follow-up sends text, resume, and architecture image sequentially. It records each result and continues after an individual failure. Its top-level `success` is true only when all three operations succeed; per-item booleans identify partial delivery.

## Mid-Call Endpoint

`POST /tools/send-high-intent-whatsapp` accepts the contract supplied by the user. It builds a concise message exclusively from fields that are present. It does not expose classifications, internal reasoning, scores, or metadata. Because the request has no customer-name field, the greeting is generic and does not invent a name.

Successful delivery returns a structured response with the Whapi message ID. Provider failures return HTTP 200 with `success: false` and `error: "whapi_send_failed"`, allowing the voice agent to handle tool failure without receiving a stack trace. Invalid request data remains an ordinary FastAPI validation error because no provider action occurred.

## Idempotency and Concurrency

An isolated in-memory component tracks successful `call_id` values. Concurrent requests for the same call share one in-flight send, preventing two provider calls. A call ID is permanently marked only after Whapi accepts the message. Failed sends remain retryable.

This prototype state resets on process restart and is not shared across multiple workers. The component boundary permits later replacement with Redis or Postgres without changing the endpoint contract.

## Errors and Logging

Whapi non-success responses, timeouts, network failures, and malformed success responses become sanitized provider errors. Logs include operation, call ID where available, normalized phone number, status, provider message ID, and a safe error category. Logs exclude tokens, authorization headers, credentials, and raw exception representations that might contain sensitive request data.

## Testing

Tests make no real Whapi requests. Mocked HTTP transport verifies:

1. text endpoint and JSON payload;
2. bearer authorization and content type;
3. accepted and rejected phone formats;
4. repeated and concurrent call IDs send once;
5. provider failure becomes a structured endpoint response and remains retryable;
6. resume uses `/messages/document` and the readable filename;
7. architecture uses `/messages/image` and its caption;
8. final follow-up attempts text, document, and image in order, including after an attachment failure;
9. human-readable message generation omits absent fields and internal classifications.

Manual acceptance requires configuring a real `.env`, starting FastAPI, invoking the endpoint, and confirming text, PDF, and image delivery through the already-authorized Whapi channel.
