# ElevateBox Sales Voice-Agent Backend

FastAPI backend for the Sarvam voice agent. It captures leads during a call,
sends WhatsApp mid-call and after the call through Whapi, schedules durable
callbacks, and places those callbacks back through Sarvam Instant Outbound.

This project does not create or modify the Sarvam agent and does not use Twilio.

## Architecture

```text
Voice Call -> Lead Capture -> Mid-call WhatsApp -> Callback Scheduling
           -> Outbound Callback -> Post-call Follow-up
```

The Sarvam agent (Saaras v3 STT, Sarvam 105B, Bulbul v3 TTS) reaches this
backend through three tool endpoints, all behind the `X-Tool-Secret` header:

```text
POST /tools/send-high-intent-whatsapp
POST /tools/schedule-callback
POST /tools/complete-call
```

### Services

| Service | Responsibility |
| --- | --- |
| `LeadService` | Turns any tool payload into the lead row: one phone format, one product-count rule |
| `CallService` | Persists a finished call, closes its callback, triggers the follow-up |
| `CallbackService` | Schedules callbacks and dials the due ones on the worker tick |
| `MessageService` | Sends one WhatsApp per (call, kind), exactly once |
| `FollowupService` | Post-call summary text, resume, architecture image |
| `WhapiService` | The Whapi HTTP client |
| `InMemoryIdempotencyStore` | Fallback de-duplication when no database is configured |

### Data layer (Supabase Postgres, schema `sales_agent`)

| Table | Holds |
| --- | --- |
| `leads` | One row per normalized phone number, with the qualification captured so far |
| `calls` | One row per Sarvam call, its direction, and the callback that placed it |
| `callbacks` | Scheduled callbacks and their lifecycle state |
| `callback_attempts` | One row per outbound dial, with the provider result |
| `messages` | One row per (call, kind) WhatsApp delivery |
| `audit_events` | Append-only history of everything done for a lead |

### Callback flow

1. The lead asks for a callback; the agent calls `/tools/schedule-callback`.
2. The callback is stored `PENDING`.
3. APScheduler polls every 15 seconds (`CALLBACK_POLL_SECONDS`).
4. A worker claims one due row with `FOR UPDATE SKIP LOCKED` and moves it to
   `IN_PROGRESS`. The claim is committed before dialling, so a crash leaves the
   callback owned rather than dialled twice.
5. Sarvam Instant Outbound places the call over the configured telephony
   connection, carrying a recap of the first conversation in `agent_variables`.
6. The same voice agent talks to the lead.
7. The call ends, the agent calls `/tools/complete-call`, and the callback moves
   to `COMPLETED`.

A failed dial records a `callback_attempts` row. Transient failures requeue the
callback as `PENDING` with a five-minute `next_attempt_at`; permanent ones end
at `FAILED`.

### Reliability

- Every tool endpoint requires `X-Tool-Secret`.
- `uq_messages_call_id_kind` is the WhatsApp idempotency boundary. The row is
  reserved and committed before Whapi is called, so a repeated tool call for the
  same `call_id` finds it taken and never sends a second message. Only a
  `FAILED` row can be re-claimed by a retry.
- Callbacks live in Postgres, so they survive a restart.
- `SKIP LOCKED` makes multiple workers safe.

## Requirements

- Python 3.11 or newer
- An authorized Whapi channel and API token
- A Supabase pooled PostgreSQL connection string
- A Supabase project URL and server-only service-role key
- Sarvam Instant Outbound credentials for real callback dialling

## Setup (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
Copy-Item .env.example .env
```

Set the real values in `.env`:

```env
WHAPI_BASE_URL=https://gate.whapi.cloud
WHAPI_TOKEN=your-token-here
DATABASE_URL=postgresql://user:password@pooler-host:6543/postgres
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-server-only-key
SARVAM_TOOL_SECRET=generate-a-long-random-secret
```

Outbound callback dialling additionally needs `SARVAM_API_KEY`,
`SARVAM_ORG_ID`, `SARVAM_WORKSPACE_ID`, `SARVAM_APP_ID`,
`SARVAM_CONNECTION_ID`, and `SARVAM_AGENT_PHONE_NUMBER`. Without all six the
backend falls back to `UnconfiguredSarvamOutboundCaller`, which records due
callbacks as `FAILED` with `sarvam_outbound_not_configured` rather than dialling.

Never commit `.env`.

Apply the database schema:

```powershell
alembic upgrade head
```

Create a private Supabase Storage bucket named `sales-agent-assets`, then upload:

```text
resume/Nischal_Saxena_Resume.pdf
architecture/voice-agent.png
```

## Run

```powershell
uvicorn app.main:app --reload
```

Check health:

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8000/health
```

Send a mid-call message:

```powershell
$body = @{
    call_id = "sarvam-call-123"
    phone = "+91 86886 64337"
    business_type = "fashion"
    product_count = "200"
    required_features = @("payments", "inventory", "WhatsApp integration")
    budget_range = "₹80,000"
    timeline = "two weeks"
    summary = "Customer wants an e-commerce website."
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri http://127.0.0.1:8000/tools/send-high-intent-whatsapp `
    -ContentType "application/json" `
    -Headers @{ "X-Tool-Secret" = "your-tool-secret" } `
    -Body $body
```

A successful first request returns:

```json
{
  "success": true,
  "message_id": "provider-message-id",
  "already_sent": false
}
```

Repeating a successful `call_id` returns `already_sent: true` without contacting
Whapi again. Provider failures return:

```json
{
  "success": false,
  "error": "whapi_send_failed"
}
```

Schedule a callback with an offset-aware timestamp:

```json
{
  "call_id": "sarvam-call-123",
  "phone": "8688664337",
  "requested_expression": "kal 11 baje",
  "callback_time": "2026-08-23T11:00:00+05:30",
  "timezone": "Asia/Kolkata",
  "lead_classification": "WARM",
  "reason": "Discuss budget",
  "summary": "Interested and asked for a callback."
}
```

`/tools/complete-call` commits the lead and call first, then attempts the
contextual text, resume, and architecture image independently, so one failing
attachment does not cost the lead the other two.

## Tests

```powershell
python -m pytest -v
```

Tests use HTTPX mock transports and in-memory boundaries; they do not contact
Whapi, Sarvam, or Supabase.

## Manual acceptance

With the authorized Whapi channel and real token configured:

1. Call `/tools/send-high-intent-whatsapp` and confirm the text arrives.
2. Call it again with the same `call_id` and confirm no second message arrives.
3. Call `/tools/complete-call` and confirm the summary, resume, and architecture
   image all arrive.
4. Schedule a callback a minute out and confirm the outbound call is placed and
   the callback row reaches `COMPLETED`.

Real media delivery and outbound dialling cannot be verified by the automated
suite; they need your tokens, authorized channel, and telephony connection.

## Supabase security

Business tables live in the private `sales_agent` schema. The migrations revoke
access from `anon` and `authenticated` and enable row-level security on every
table. The service-role key is used only on the server, to mint short-lived
signed URLs for the private attachments.
