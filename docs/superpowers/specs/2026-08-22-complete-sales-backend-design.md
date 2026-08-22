# Complete Sales Voice-Agent Backend Design

## Scope

Extend the existing Whapi FastAPI application into the complete backend described by the original ElevateBox specification. Preserve the existing Sarvam voice agent and prompt. Do not create another agent or guess an undocumented outbound-call contract.

This implementation adds Supabase persistence and Storage, durable idempotency, call completion, final follow-ups, callback persistence and scheduling, tool authentication, structured events, migrations, and tests. It retains Whapi as the only WhatsApp provider.

## Architecture

FastAPI exposes three tool endpoints used by the existing Sarvam agent:

- `POST /tools/send-high-intent-whatsapp`
- `POST /tools/schedule-callback`
- `POST /tools/complete-call`

All tool endpoints require `X-Tool-Secret`. HTTP handlers validate contracts and return structured tool results. Focused services own lead/call persistence, Whapi delivery, Supabase Storage signed URLs, follow-up composition, callback scheduling, and outbound-call delegation.

SQLAlchemy connects to Supabase through its pooled PostgreSQL connection string. Alembic owns migrations. APScheduler runs a short interval polling job, but callback rows in PostgreSQL are the durable source of truth.

The callback worker calls a `SarvamOutboundCaller` protocol. The initial `UnconfiguredSarvamOutboundCaller` never performs an HTTP request and returns a typed `not_configured` result. When a supported Sarvam Campaign or dialer contract becomes available, a new adapter can replace it without changing callback persistence or scheduling logic.

## Configuration

The application reads:

```env
DATABASE_URL=
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_STORAGE_BUCKET=sales-agent-assets
SUPABASE_RESUME_OBJECT_PATH=resume/Parv_Agarwal_Resume.pdf
SUPABASE_ARCHITECTURE_OBJECT_PATH=architecture/voice-agent.png

WHAPI_BASE_URL=https://gate.whapi.cloud
WHAPI_TOKEN=

SARVAM_TOOL_SECRET=
DEFAULT_TIMEZONE=Asia/Kolkata
CALLBACK_POLL_SECONDS=15
CALLBACK_SIGNED_URL_TTL_SECONDS=900

DEVELOPER_NAME=Parv Agarwal
DEVELOPER_PHONE=
```

Secrets are never hardcoded, returned, or logged. The application may boot without integration credentials so `/health` remains usable, but affected tool operations return sanitized configuration failures.

## Database

Business tables live in a private `sales_agent` schema. The schema is not exposed through the Supabase Data API and grants no access to `anon` or `authenticated` roles. Internal primary keys use `bigint generated always as identity`. All timestamps use `timestamptz`.

### Leads

One lead exists per normalized E.164 phone number. Fields include business type, products sold, product count, required features, budget, timeline, urgency, decision maker, objections, preferred language, lead classification, classification reason, and created/updated timestamps. Structured lists use JSONB.

### Calls

Calls reference leads and have a unique Sarvam call ID, direction (`INITIAL` or `CALLBACK`), status, language, summary, important statements, transcript, start/end times, and creation time. Repeated completion payloads for the same Sarvam call ID update the existing row rather than create duplicates.

### Callbacks

Callbacks reference a lead and source call and store the original expression, resolved execution time, IANA timezone, reason, status, attempt count, last error, next attempt time, claimed time, creation time, and completion time. A unique constraint on source call plus scheduled time prevents repeated tool invocations from duplicating a callback.

Statuses remain `PENDING`, `TRIGGERED`, `COMPLETED`, `FAILED`, and `CANCELLED`. The worker claims a row by updating its attempt metadata in a short transaction. An unconfigured outbound adapter produces `FAILED` with `last_error = 'sarvam_outbound_not_configured'` and is not automatically retried. A later operator can explicitly requeue it after installing a real adapter.

### Events

Events are append-only records linked to a lead and optionally a call. They store event type, sanitized JSONB payload, and creation time. Events record WhatsApp requests/results, call completion, callback scheduling/attempts, and final follow-up component results.

Foreign-key columns are indexed. A partial index over callback execution time covers only pending callbacks. A unique partial index or dedicated delivery record enforces one successful high-intent WhatsApp per call under concurrent requests.

## Supabase Storage

Resume and architecture assets live in the private `sales-agent-assets` bucket at configured object paths. A storage service uses the server-only service-role credential to generate short-lived signed URLs. Whapi receives those URLs through `/messages/document` and `/messages/image`.

The application does not expose the service-role key or make the bucket public. Missing objects produce per-attachment failures without preventing the remaining follow-up operations.

## High-Intent WhatsApp

The existing request contract remains supported. The endpoint reserves the delivery transactionally before contacting Whapi. Concurrent requests for the same call observe the same reservation. A successful provider response permanently completes the reservation; a provider failure releases it for retry.

The outbound message uses only structured customer-facing fields and never includes classification labels, scores, internal reasoning, raw JSON, or fabricated details.

## Call Completion

`POST /tools/complete-call` accepts the fields defined in the original product specification. Within a database transaction it normalizes the phone number, upserts the lead, upserts the call by Sarvam call ID, stores qualification data, and appends `CALL_COMPLETED`.

After persistence commits, the follow-up service generates human-readable text from fields that are present. It then attempts, in order:

1. contextual text through Whapi;
2. resume document using a signed Storage URL;
3. architecture image using a signed Storage URL.

Each component is independently idempotent for the call. A failure is logged and recorded and does not stop subsequent components. The response reports `text_sent`, `resume_sent`, and `architecture_sent`; overall success is true only when all requested components succeed.

## Callback Scheduling

`POST /tools/schedule-callback` requires a resolved timezone-aware callback timestamp. The default declared timezone is `Asia/Kolkata`, but the timestamp must still include an explicit UTC offset. An unresolved or ambiguous expression without a timestamp returns `callback_time_required`; the backend does not invent a time.

The callback is committed before the endpoint returns success. APScheduler periodically invokes a callback worker. The worker atomically claims a due row using `FOR UPDATE SKIP LOCKED`, commits the claim, loads compact lead and source-call context, and passes a typed request to `SarvamOutboundCaller`.

A successful future adapter result stores the returned Sarvam call ID, marks the callback `TRIGGERED`, creates a callback-direction call row, and records `CALLBACK_TRIGGERED`. Transient adapter failures may use bounded retry metadata. The initial unconfigured adapter fails once without a retry loop.

## Security and Logging

`X-Tool-Secret` is compared with the configured secret using constant-time comparison. Missing, invalid, or unconfigured secrets produce a generic `401` without revealing configuration state.

Structured logs include call ID, lead ID, normalized phone, operation, status, duration, provider message ID, and a safe error category when available. Logs exclude authorization headers, API tokens, service-role keys, database credentials, and raw exception values that may contain provider payloads.

## Failure Contracts

Provider, database, storage, and scheduler errors are converted into stable response error codes. Raw stack traces never reach Sarvam. A callback is never reported as scheduled until the database commit succeeds. A callback is never reported as triggered until an outbound adapter returns success.

Database operations use short transactions. External network calls occur after commits and outside row locks. Follow-up outcomes are recorded independently so retries do not resend successful components.

## Testing

Tests follow red-green TDD and make no real provider calls.

- Model and repository tests cover constraints, lead/call upserts, event creation, persistent high-intent idempotency, and duplicate callback prevention.
- Migration tests inspect PostgreSQL-specific schema SQL, indexes, privileges, and callback-claim semantics.
- API tests cover tool-secret authentication, structured failures, validation, and backward-compatible high-intent requests.
- Whapi tests continue covering text, document, image, and partial final-follow-up failure.
- Storage tests mock signed-URL creation and missing objects.
- Callback tests cover persistence, due-row claiming, compact previous context, the unconfigured adapter, no false `TRIGGERED` state, and later adapter replacement.
- Completion tests cover lead/call persistence, contextual copy, attachment ordering, component idempotency, and retry of only failed components.
- Scheduler lifespan tests verify startup and graceful shutdown without depending on wall-clock sleeps.

Manual acceptance requires applying migrations to the user's `sales_agent` Supabase project, uploading the two private assets, configuring secrets, updating the existing Sarvam tools to the public endpoints, and completing real Whapi text/document/image delivery tests. Real outbound callback calling remains deferred until an actual Sarvam Campaign or dialer adapter contract is provided.

## Explicit Non-Goals

Do not build or modify a Sarvam voice agent, a second callback agent, a frontend, authentication accounts, a CRM, analytics, a vector database, custom speech components, containers, or guessed Sarvam outbound HTTP calls.
