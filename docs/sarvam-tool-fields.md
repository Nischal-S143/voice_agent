# Tool body fields — descriptions to paste into Sarvam

> **Read this first — set the mode before you type anything.**
>
> Every Body field has a ⚙️ **Configure value** menu with three modes. The
> default, **Fixed value**, sends whatever is in the box verbatim on every call.
> A live call proved what that costs: the lead was stored with
> `business_type = "The business type from the conversation, e.g. fashion..."`
> and the customer received a WhatsApp reading *"you're looking to build a The
> business type from the conversation... e-commerce website"*.
>
> | Mode | Use it for |
> |---|---|
> | ✨ **Let the agent decide** | Everything drawn from the conversation. The description below is the model's guidance. |
> | 𝑓ₘ **Agent variable** | `call_id` and `phone` only — bind each to the input variable of the same name. |
> | ✏️ **Fixed value** | `timezone` only: `Asia/Kolkata`. |
>
> Never bind a body field to a `previous_*` variable. Those carry the *earlier*
> call's data, injected by the backend so a callback does not re-qualify the
> lead. They are empty on a first call and stale on a callback.
>
> `call_id` and `phone` must be **Agent variable**, never "Let the agent
> decide": the customer never says their own number aloud, so the model has
> nothing to infer from and the request is rejected as `invalid_phone`.
> `call_id` also carries the idempotency key, so a guessed one means duplicate
> WhatsApps.

Each row is one row in the tool's **Body** tab: the field name, what the value
should resolve to, and the type dropdown.

Every description below says when to omit a field, because an empty string
still gets stored and makes the follow-up message read half-finished.

---

## Tool 1 — Send High Intent Whatsapp

`POST /tools/send-high-intent-whatsapp`

| Field | Type | Description |
|---|---|---|
| `call_id` | Text | The call_id input variable for this call. Copy its exact value. |
| `phone` | Text | The phone input variable — the customer's number in E.164 format. |
| `business_type` | Text | The customer's business type from the conversation, e.g. fashion, grocery, electronics. Omit if they did not say. |
| `product_count` | Text | Roughly how many products they sell, as a string like "150". Omit if not mentioned. |
| `required_features` | **JSON** | Array of features the customer asked for, e.g. ["payment gateway", "COD"]. Empty array if none. |
| `budget_range` | Text | The budget exactly as the customer expressed it, e.g. "80k-1L". Never invent one. |
| `timeline` | Text | When they want to launch, in their words, e.g. "six weeks". Never invent one. |
| `summary` | Text | One or two lines on what the customer wants. No internal labels or scores. |

---

## Tool 2 — Complete Call

`POST /tools/complete-call`

| Field | Type | Description |
|---|---|---|
| `call_id` | Text | The call_id input variable for this call. Copy its exact value. |
| `phone` | Text | The phone input variable — the customer's number in E.164 format. |
| `language` | Text | The language the call was actually held in: telugu, hindi or english. |
| `business_type` | Text | The customer's business type from the conversation. Omit if they did not say. |
| `products_sold` | Text | What they sell, in their words, e.g. "sarees and kurtis". Omit if not mentioned. |
| `product_count` | Text | Roughly how many products, as a string like "150". Omit if not mentioned. |
| `required_features` | **JSON** | Array of features they asked for. Empty array if none. |
| `budget_range` | Text | The budget exactly as they expressed it. Never invent one. |
| `timeline` | Text | When they want to launch, in their words. Never invent one. |
| `urgency` | Text | How urgent this felt: high, medium or low. |
| `decision_maker` | Text | Who decides, e.g. "self", "partner", "brother". Omit if unclear. |
| `objections` | **JSON** | Array of concerns they raised, e.g. ["maintenance cost"]. Empty array if none. |
| `lead_classification` | Text | Exactly one of: hot, warm, cold. |
| `classification_reason` | Text | Why you classified them that way, based on what they actually said. |
| `important_statements` | **JSON** | Array of two to four things the customer actually said, quoted word for word in their own language. These are sent to them verbatim in the follow-up message, so never paraphrase, translate, or invent them. Empty array if nothing memorable was said. |
| `summary` | Text | Two or three lines covering the whole conversation. |
| `transcript` | Text | The full call transcript if available, otherwise omit. |

Hold off on `callback_time`, `started_at` and `ended_at` until the rest works —
they are timestamps and a wrong format returns 422.

---

## Tool 3 — Schedule Callback

`POST /tools/schedule-callback`

| Field | Type | Description |
|---|---|---|
| `call_id` | Text | The call_id input variable for this call. Copy its exact value. |
| `phone` | Text | The phone input variable — the customer's number in E.164 format. |
| `requested_expression` | Text | The customer's literal words about when to call back, in their own language, e.g. "kal shaam paanch baje". |
| `callback_time` | Text | That time as an ISO 8601 timestamp in Asia/Kolkata, always with the +05:30 offset, e.g. 2026-08-24T17:00:00+05:30. Required — the call fails without it, and a timestamp with no offset is rejected. |
| `timezone` | Text | **Literal value, not a description:** `Asia/Kolkata` |
| `lead_classification` | Text | Exactly one of: hot, warm, cold. |
| `reason` | Text | Why they want the callback, e.g. "partner approves budget". |
| `summary` | Text | One or two lines on the conversation so far. |

---

## Before saving each tool

- Check the ⚙️ mode on **every** field. A field left on **Fixed value** sends
  its own description text as the value.
- `call_id` and `phone`: **Agent variable**. `timezone`: **Fixed value**.
  Everything else: **Let the agent decide**.
- No body field should point at a `previous_*` variable.
- Delete the leftover `payload` field from the Postman Echo mock.
- `Headers` should show **2**: `Content-Type` and `X-Tool-Secret`.
- Arrays (`required_features`, `objections`, `important_statements`) must have
  type **JSON**, not Text — Text returns 422 with a `list_type` error.

## Reading a failure

Every rejected call now names the offending fields in the Railway logs:

```
request_validation_failed path=/tools/complete-call
problems=[{'field': 'product_count', 'error': 'string_type'}]
```

`missing` means the field never arrived. `string_type` / `list_type` mean it
arrived as the wrong type.
