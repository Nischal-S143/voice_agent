# ElevateBox Sales Voice-Agent Backend

FastAPI backend for the existing Sarvam voice agent. It persists leads, calls, callbacks, and audit events in Supabase Postgres; sends WhatsApp messages and attachments through Whapi; and schedules durable callback attempts.

This project does not create or modify the Sarvam agent and does not use Twilio. Real outbound callback calling remains behind an unconfigured adapter until Sarvam or a dialer provides a supported invocation contract.

## Requirements

- Python 3.11 or newer
- An authorized Whapi channel
- A Whapi API token
- A Supabase pooled PostgreSQL connection string
- A Supabase project URL and server-only service-role key
- Publicly reachable URLs or Whapi media references for attachments

## Setup (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
Copy-Item .env.example .env
```

Set the real token in `.env`:

```env
WHAPI_BASE_URL=https://gate.whapi.cloud
WHAPI_TOKEN=your-token-here
DATABASE_URL=postgresql://user:password@pooler-host:6543/postgres
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-server-only-key
SARVAM_TOOL_SECRET=generate-a-long-random-secret
```

Never commit `.env`.

Apply the database schema:

```powershell
alembic upgrade head
```

Create a private Supabase Storage bucket named `sales-agent-assets`, then upload:

```text
resume/Parv_Agarwal_Resume.pdf
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

Repeating a successful `call_id` returns `already_sent: true` without contacting Whapi again. Provider failures return:

```json
{
  "success": false,
  "error": "whapi_send_failed"
}
```

## Attachment helpers

`WhapiService` exposes:

```python
await service.send_resume(phone, resume_url_or_media_reference)
await service.send_architecture_image(phone, image_url_or_media_reference)
await service.send_final_followup(phone, message, resume, architecture_image)
```

The final follow-up attempts text, resume, and architecture image in that order. A failed attachment does not prevent the next operation from being attempted.

## Tests

```powershell
python -m pytest -v
```

Tests use HTTPX mock transports and do not contact Whapi.

## Prototype limitation

Idempotency is stored in process memory. It resets whenever the app restarts and is not shared between workers. Run one Uvicorn worker for this prototype. Replace `InMemoryIdempotencyStore` with Redis or database-backed persistence before scaling to multiple processes.

## Manual acceptance

With the authorized Whapi channel and real token configured:

1. Call `/tools/send-high-intent-whatsapp` and confirm the text arrives.
2. Call `send_resume` with a reachable PDF reference and confirm the document arrives.
3. Call `send_architecture_image` with a reachable image reference and confirm the image arrives.

Real media delivery cannot be verified by the automated suite because it requires your token, authorized channel, and media references.

## Sarvam tool endpoints

Configure the three existing Sarvam tools with the same `X-Tool-Secret` value used by the backend:

```text
POST /tools/send-high-intent-whatsapp
POST /tools/schedule-callback
POST /tools/complete-call
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

Complete a call using the original specification contract. The backend commits the lead and call first, then attempts contextual text, resume, and architecture delivery independently.

## Callback behavior

APScheduler polls durable `PENDING` callback rows every 15 seconds by default. Workers claim due rows with PostgreSQL `FOR UPDATE SKIP LOCKED`, so multiple processes do not claim the same callback.

The included `UnconfiguredSarvamOutboundCaller` intentionally performs no HTTP request. Due callbacks are marked `FAILED` with `sarvam_outbound_not_configured` and are not retried automatically. When a real Sarvam Campaign or dialer contract is available, implement:

```python
class SarvamOutboundCaller(Protocol):
    async def place_call(self, request: OutboundCallRequest) -> OutboundCallResult: ...
```

Replace only that adapter; callback persistence and scheduling do not change.

## Supabase security

Business tables are created in the private `sales_agent` schema. The migration revokes access from `anon` and `authenticated`. The service-role key is used only on the server to create short-lived signed URLs for private attachments.
