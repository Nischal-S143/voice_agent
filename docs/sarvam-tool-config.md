# Sarvam Tool Configuration

Three tools to create on the agent. Every field name below matches
`app/schemas/` exactly — a renamed field returns HTTP 422.

**Base URL** (Cloudflare quick tunnel — changes on every restart):

```
https://<your-deployed-domain>
```

**Header required on all three tools:**

| Header | Value |
|---|---|
| `Content-Type` | `application/json` |
| `X-Tool-Secret` | `<SARVAM_TOOL_SECRET from your .env>` |

Method is `POST` for all three.

---

## Tool 1 — `send_high_intent_whatsapp`

**URL:** `{BASE}/tools/send-high-intent-whatsapp`

**Description (give this to the agent):**

> Send the customer a WhatsApp message immediately, while the call is still in
> progress, as soon as they show high buying intent — asking for pricing, asking
> how soon work can start, requesting details, or naming a real budget. Call this
> during the conversation, never after the call has ended. Call it at most once
> per call.

**Parameters:**

```json
{
  "type": "object",
  "properties": {
    "call_id": {
      "type": "string",
      "description": "The Sarvam call id for this conversation."
    },
    "phone": {
      "type": "string",
      "description": "Customer phone in E.164 format, e.g. +918688664337."
    },
    "business_type": {
      "type": "string",
      "description": "What kind of business they run, e.g. fashion, grocery, electronics."
    },
    "product_count": {
      "type": "string",
      "description": "Roughly how many products they sell, as a string, e.g. \"150\"."
    },
    "required_features": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Features they asked for, e.g. [\"payment gateway\", \"COD\"]."
    },
    "budget_range": {
      "type": "string",
      "description": "Budget exactly as they expressed it, e.g. \"80k-1L\"."
    },
    "timeline": {
      "type": "string",
      "description": "When they want to launch, e.g. \"six weeks\"."
    },
    "summary": {
      "type": "string",
      "description": "One or two lines on what they want. No internal scores or labels."
    }
  },
  "required": ["call_id", "phone"]
}
```

---

## Tool 2 — `schedule_callback`

**URL:** `{BASE}/tools/schedule-callback`

**Description (give this to the agent):**

> Book a callback when the customer names a time, however vague. Convert their
> words into an exact timestamp yourself, in Asia/Kolkata, and always include the
> +05:30 offset. Confirm the time back to them in words after calling this.

**Parameters:**

```json
{
  "type": "object",
  "properties": {
    "call_id": {
      "type": "string",
      "description": "The Sarvam call id for this conversation."
    },
    "phone": {
      "type": "string",
      "description": "Customer phone in E.164 format."
    },
    "requested_expression": {
      "type": "string",
      "description": "Their literal words, in their language, e.g. \"kal shaam paanch baje\"."
    },
    "callback_time": {
      "type": "string",
      "description": "ISO 8601 timestamp WITH the +05:30 offset, e.g. 2026-08-24T17:00:00+05:30. Required — the request fails without it."
    },
    "timezone": {
      "type": "string",
      "description": "Always Asia/Kolkata."
    },
    "lead_classification": {
      "type": "string",
      "enum": ["hot", "warm", "cold"],
      "description": "How you read this lead."
    },
    "reason": {
      "type": "string",
      "description": "Why they want the callback, e.g. \"partner approves budget\"."
    },
    "summary": {
      "type": "string",
      "description": "One or two lines on the conversation so far."
    }
  },
  "required": ["call_id", "phone", "requested_expression", "callback_time"]
}
```

> `callback_time` is optional in the schema but the endpoint returns
> `callback_time_required` without it, so mark it required on the tool.
> A timestamp with no offset is rejected as `callback_time_must_include_offset`.

---

## Tool 3 — `complete_call`

**URL:** `{BASE}/tools/complete-call`

**Description (give this to the agent):**

> Call exactly once at the end of every call, however it went — including a hangup
> or a hard no. This saves the lead and sends the follow-up WhatsApp with the
> resume and the architecture image. Quote the customer's real words in
> important_statements; those are used verbatim in the follow-up message.

**Parameters:**

```json
{
  "type": "object",
  "properties": {
    "call_id": { "type": "string", "description": "The Sarvam call id." },
    "phone": { "type": "string", "description": "Customer phone in E.164 format." },
    "language": {
      "type": "string",
      "description": "Language the call was actually held in: telugu, hindi or english."
    },
    "business_type": { "type": "string", "description": "Kind of business they run." },
    "products_sold": {
      "type": "string",
      "description": "What they sell, e.g. \"sarees and kurtis\"."
    },
    "product_count": {
      "type": "string",
      "description": "Roughly how many products, as a string."
    },
    "required_features": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Features they asked for."
    },
    "budget_range": { "type": "string", "description": "Budget as they expressed it." },
    "timeline": { "type": "string", "description": "Their launch timeline." },
    "urgency": { "type": "string", "description": "How urgent it felt: high, medium or low." },
    "decision_maker": {
      "type": "string",
      "description": "Who decides, e.g. \"self\", \"partner\", \"brother\"."
    },
    "objections": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Concerns they raised, e.g. [\"maintenance cost\"]."
    },
    "lead_classification": {
      "type": "string",
      "enum": ["hot", "warm", "cold"],
      "description": "Final read on the lead."
    },
    "classification_reason": {
      "type": "string",
      "description": "Why you classified them that way, from what they said."
    },
    "callback_time": {
      "type": "string",
      "description": "ISO 8601 with +05:30 offset, only if a callback was booked."
    },
    "important_statements": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Two to four of the customer's actual quoted words, in their own language. Used verbatim in the follow-up WhatsApp, so quote them exactly."
    },
    "summary": {
      "type": "string",
      "description": "Two or three lines on the whole conversation."
    },
    "transcript": { "type": "string", "description": "Full call transcript if available." },
    "started_at": { "type": "string", "description": "ISO 8601 with offset." },
    "ended_at": { "type": "string", "description": "ISO 8601 with offset." }
  },
  "required": ["call_id", "phone"]
}
```

---

## Gotchas

- `product_count` is a **string**, not a number. `"150"`, not `150`.
- `required_features` and `objections` are **arrays**, even with one item.
- Every response is HTTP **200**, even on failure — check `"success"` in the
  body, not the status code.
- A repeated `send_high_intent_whatsapp` for the same `call_id` returns
  `{"success": true, "already_sent": true}` and sends nothing. Safe, but the
  agent still should not call it twice.
- Map `call_id` to Sarvam's real call id variable. Idempotency depends on it.

## Verify before a live call

```bash
curl -X POST {BASE}/tools/send-high-intent-whatsapp \
  -H "Content-Type: application/json" \
  -H "X-Tool-Secret: <SARVAM_TOOL_SECRET from your .env>" \
  -d '{"call_id":"test-1","phone":"+91XXXXXXXXXX","business_type":"fashion"}'
```

Expect `{"success": true, "message_id": "..."}` and a real WhatsApp.
`401` means the header is missing or wrong. `422` means a field name or type is off.
