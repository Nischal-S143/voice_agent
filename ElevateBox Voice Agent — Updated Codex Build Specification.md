# ElevateBox Voice Agent — Updated Codex Build Specification

## 1. Project Goal

Complete the backend and integration layer for an already-created Sarvam Voice Agent.

The Sarvam agent is already configured and should be treated as an existing dependency.

Codex must NOT recreate the voice agent.

Codex must NOT create a second callback agent.

Codex must NOT rewrite the entire Sarvam prompt unless a small change is required to connect a real tool.

The job is to replace the current mock tool actions with real backend functionality and connect the existing Sarvam agent to those real systems.

---

# 2. Existing System

## Sarvam Voice Agent

Already completed:

- Sarvam Voice Agent created
- outbound sales prompt configured
- prompt checkpointed as version 3
- Hindi support
- English support
- Telugu support
- code-switching support
- e-commerce website sales flow
- natural discovery
- Hot/Warm/Cold classification logic
- busy-user handling
- wrong-number handling
- hostile-user handling
- vague-answer handling
- human handoff
- callback conversation logic
- tool-failure handling
- interruption handling
- zero-loop policy
- close behavior

Do not rebuild any of this.

---

# 3. Existing Sarvam Tools

The following tools already exist in the Sarvam agent:

```text
send_high_intent_whatsapp
schedule_callback
complete_call
```

These currently point to mock Postman Echo endpoints.

Their purpose is already defined in the Sarvam prompt.

Codex must replace the mock URLs with real backend endpoints.

---

# 4. Existing Output Variables

Already configured in Sarvam:

```text
lead_classification
business_type
budget_range
timeline
callback_time
```

These must continue to be used.

Additional backend fields may be stored as needed.

---

# 5. What Codex Must Build

Only build the missing backend infrastructure.

The required pieces are:

1. FastAPI backend
2. real WhatsApp integration
3. lead/call persistence
4. callback persistence
5. callback scheduler
6. Sarvam outbound callback trigger using the SAME existing agent
7. previous-conversation context injection
8. final WhatsApp follow-up
9. resume attachment support
10. architecture image attachment support
11. tests
12. deployment-ready configuration

---

# 6. Target System Flow

```text
Existing Sarvam Voice Agent
        |
        | HTTPS tool calls
        v
FastAPI Backend
        |
        +--> Database
        |
        +--> WhatsApp Provider
        |
        +--> Callback Scheduler
                    |
                    v
          Trigger SAME Sarvam Agent
          with previous context
```

The voice layer remains entirely in Sarvam.

Codex only builds the systems around it.

---

# 7. FastAPI Backend

Create a minimal FastAPI service.

Required endpoints:

```text
POST /tools/send-high-intent-whatsapp
POST /tools/schedule-callback
POST /tools/complete-call
GET  /health
```

Optional internal endpoints are allowed if useful.

Do not build a frontend.

---

# 8. Recommended Project Structure

```text
app/
├── main.py
├── config.py
├── database.py
│
├── api/
│   ├── tools.py
│   └── health.py
│
├── models/
│   ├── lead.py
│   ├── call.py
│   ├── callback.py
│   └── event.py
│
├── schemas/
│   ├── whatsapp.py
│   ├── callback.py
│   └── complete_call.py
│
├── services/
│   ├── whatsapp_service.py
│   ├── sarvam_service.py
│   ├── callback_service.py
│   └── followup_service.py
│
├── scheduler/
│   └── scheduler.py
│
└── utils/
    ├── datetime_utils.py
    └── logging.py

tests/
├── test_whatsapp.py
├── test_callbacks.py
├── test_complete_call.py
└── test_idempotency.py

.env.example
requirements.txt
README.md
```

Keep it small.

---

# 9. Database

SQLite is acceptable initially.

Design models so PostgreSQL can replace it later.

## Lead

Store:

```text
id
phone
business_type
products_sold
product_count
required_features
budget_range
timeline
urgency
decision_maker
objections
preferred_language
lead_classification
classification_reason
created_at
updated_at
```

---

## Call

Store:

```text
id
lead_id
sarvam_call_id
direction
status
language
summary
important_statements
transcript
started_at
ended_at
created_at
```

Direction:

```text
INITIAL
CALLBACK
```

---

## Callback

Store:

```text
id
lead_id
source_call_id
requested_expression
scheduled_at
timezone
reason
status
created_at
completed_at
```

Statuses:

```text
PENDING
TRIGGERED
COMPLETED
FAILED
CANCELLED
```

---

## Event

Store important actions:

```text
id
lead_id
call_id
event_type
payload
created_at
```

Possible event types:

```text
HIGH_INTENT_WHATSAPP_REQUESTED
HIGH_INTENT_WHATSAPP_SENT
HIGH_INTENT_WHATSAPP_FAILED
CALLBACK_SCHEDULED
CALLBACK_TRIGGERED
CALLBACK_FAILED
CALL_COMPLETED
FINAL_FOLLOWUP_SENT
FINAL_FOLLOWUP_FAILED
```

---

# 10. Tool 1 — send_high_intent_whatsapp

Sarvam already calls:

```text
send_high_intent_whatsapp
```

Map it to:

```text
POST /tools/send-high-intent-whatsapp
```

Purpose:

Send a real WhatsApp during the active voice call when buying intent becomes high.

Request example:

```json
{
  "call_id": "string",
  "phone": "8688664337",
  "business_type": "fashion",
  "products_sold": "clothing",
  "product_count": "200",
  "required_features": [
    "payments",
    "inventory",
    "WhatsApp integration"
  ],
  "budget_range": "80000",
  "timeline": "2 weeks",
  "lead_classification": "HOT",
  "buying_signals": [
    "asked about pricing",
    "wants to start this month"
  ],
  "summary": "Customer wants a 200-product fashion e-commerce site."
}
```

Response:

```json
{
  "success": true,
  "message_id": "provider-message-id",
  "already_sent": false
}
```

---

# 11. WhatsApp Provider

Implement provider abstraction.

Preferred order:

```text
Meta WhatsApp Cloud API
Twilio WhatsApp
```

Use whichever can be made to work fastest.

Service interface should look conceptually like:

```python
send_text(...)
send_document(...)
send_image(...)
```

Do not hardcode provider-specific logic inside API endpoints.

---

# 12. Mid-Call WhatsApp Requirement

This endpoint must return quickly.

The assignment requires the WhatsApp to reach the prospect before the voice call ends.

Do not wait for post-call processing.

Do not queue it for later unless the provider itself handles delivery asynchronously after accepting the request.

---

# 13. Idempotency

The voice agent may call the tool more than once.

Only one successful high-intent WhatsApp should be sent per call.

Before sending:

Check whether:

```text
HIGH_INTENT_WHATSAPP_SENT
```

already exists for the current call ID.

If yes:

Return:

```json
{
  "success": true,
  "already_sent": true
}
```

without sending another WhatsApp.

---

# 14. Tool 2 — schedule_callback

Sarvam already calls:

```text
schedule_callback
```

Map it to:

```text
POST /tools/schedule-callback
```

Request example:

```json
{
  "call_id": "string",
  "phone": "8688664337",
  "requested_expression": "kal subah",
  "callback_time": "2026-08-23T10:00:00+05:30",
  "timezone": "Asia/Kolkata",
  "lead_classification": "WARM",
  "reason": "Customer wants to discuss with business partner",
  "summary": "Interested but wants to discuss budget first."
}
```

Response:

```json
{
  "success": true,
  "callback_id": "string",
  "scheduled_for": "2026-08-23T10:00:00+05:30"
}
```

Persist the callback before returning success.

---

# 15. Callback Time Handling

The Sarvam agent should already clarify vague times conversationally.

Backend should generally receive a resolved timestamp.

Examples:

```text
tomorrow morning
kal 11 baje
Monday afternoon
after two hours
```

If a resolved datetime is provided:

Use it.

If only a natural-language expression is provided:

Backend may attempt resolution.

Default timezone:

```text
Asia/Kolkata
```

Do not silently invent a highly ambiguous time if clarification is required.

---

# 16. Callback Scheduler

Initial implementation:

```text
APScheduler
```

Good enough for the assignment.

Requirements:

- callback stored in database
- scheduler job created
- callback survives normal application execution
- status updated when triggered
- failures logged

Future migration to Celery/Redis is not required for this task.

---

# 17. Callback Uses the SAME Sarvam Agent

This is critical.

Do NOT create another agent.

When callback time arrives:

1. Load callback record.
2. Load lead record.
3. Load previous call context.
4. Build compact previous-context variables.
5. Trigger outbound call using the SAME existing Sarvam agent.
6. Pass dynamic context into that agent.
7. Store returned Sarvam call ID.
8. Mark callback as triggered.

---

# 18. Callback Context

Pass something like:

```json
{
  "is_callback": true,
  "previous_business_type": "Jewellery",
  "previous_product_count": "120",
  "previous_budget": "₹80,000",
  "previous_timeline": "Before festive season",
  "previous_features": [
    "payments",
    "inventory",
    "WhatsApp ordering"
  ],
  "previous_objection": "Needs to discuss with brother",
  "previous_summary": "Customer wants a jewellery e-commerce site and asked for a follow-up after discussing budget."
}
```

The existing Sarvam agent should use this context naturally.

Do not dump this data mechanically into the conversation.

---

# 19. Sarvam Service

Create:

```text
services/sarvam_service.py
```

Responsibilities:

- trigger outbound call
- use existing agent ID
- pass phone number
- pass dynamic variables/context
- return Sarvam call ID
- handle errors
- log provider response

Environment variables:

```text
SARVAM_API_KEY=
SARVAM_AGENT_ID=
```

No second agent ID is needed.

---

# 20. Tool 3 — complete_call

Sarvam already calls:

```text
complete_call
```

Map it to:

```text
POST /tools/complete-call
```

Request example:

```json
{
  "call_id": "string",
  "phone": "8688664337",
  "language": "Hindi",
  "business_type": "fashion",
  "products_sold": "clothes",
  "product_count": "200",
  "required_features": [
    "payments",
    "inventory"
  ],
  "budget_range": "₹80,000",
  "timeline": "2 weeks",
  "urgency": "high",
  "decision_maker": "self",
  "objections": [],
  "lead_classification": "HOT",
  "classification_reason": "Clear budget and near-term timeline",
  "callback_time": null,
  "important_statements": [
    "I want to launch within two weeks."
  ],
  "summary": "Customer wants a 200-product fashion e-commerce website."
}
```

Responsibilities:

1. upsert lead
2. persist call
3. persist classification
4. persist important statements
5. persist summary
6. generate final human-readable follow-up
7. send final WhatsApp
8. send resume
9. send architecture image
10. log success/failure

---

# 21. Final WhatsApp

The final WhatsApp should contain actual conversation context.

Example:

```text
Hi Sai,

Great speaking with you.

From our conversation, you're looking to build an e-commerce website for around 200 fashion products with online payments and inventory management.

You mentioned a budget of around ₹80,000 and are targeting launch within two weeks.

I've also shared my resume and the architecture overview of the system that just called you.

Parv Agarwal
<DEVELOPER_PHONE>
```

Do not include raw JSON.

Do not expose internal classification.

Do not fabricate missing information.

---

# 22. Attachments

Final WhatsApp must support:

```text
resume
architecture image
```

Config:

```text
DEVELOPER_NAME=Parv Agarwal
DEVELOPER_PHONE=
RESUME_PATH=
ARCHITECTURE_IMAGE_PATH=
```

If provider needs URLs instead of local file paths, handle this through the provider service.

---

# 23. Failure Handling

## WhatsApp Failure

If provider fails:

- log error
- save failed event
- return structured failure
- do not crash the backend

Example:

```json
{
  "success": false,
  "error": "whatsapp_send_failed"
}
```

---

## Callback Persistence Failure

Do not claim a callback is scheduled unless the database write succeeds.

---

## Sarvam Callback Failure

If callback cannot be triggered:

- mark callback FAILED
- log provider response
- preserve existing context
- allow retry

---

## Tool Failure

Tool endpoints should always return structured responses.

Do not throw raw stack traces to Sarvam.

---

# 24. Environment Variables

Create `.env.example`.

```text
APP_ENV=development

DATABASE_URL=

SARVAM_API_KEY=
SARVAM_AGENT_ID=

WHATSAPP_PROVIDER=
WHATSAPP_API_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_FROM_NUMBER=

DEVELOPER_NAME=Parv Agarwal
DEVELOPER_PHONE=
RESUME_PATH=
ARCHITECTURE_IMAGE_PATH=

DEFAULT_TIMEZONE=Asia/Kolkata
```

Never commit `.env`.

---

# 25. Health Endpoint

Create:

```text
GET /health
```

Response:

```json
{
  "status": "ok"
}
```

Optional:

```json
{
  "status": "ok",
  "database": "connected",
  "scheduler": "running"
}
```

---

# 26. Logging

Use structured logging.

Log:

```text
call_id
lead_id
tool
status
duration
provider_response_id
error
```

Never log:

```text
API keys
auth tokens
credentials
```

---

# 27. Tests

Minimum tests:

## Hot Lead WhatsApp

Expected:

```text
provider called once
event recorded
success returned
```

---

## Duplicate WhatsApp

Call same endpoint twice with same call ID.

Expected:

```text
provider called once
second response has already_sent=true
```

---

## Callback Creation

Expected:

```text
callback persisted
scheduler job created
```

---

## Callback Trigger

Expected:

```text
previous context loaded
same Sarvam agent invoked
callback marked TRIGGERED
```

---

## Complete Call

Expected:

```text
lead stored
call stored
final follow-up generated
WhatsApp provider invoked
```

---

## Provider Failure

Expected:

```text
backend remains alive
error event persisted
structured error returned
```

---

# 28. Manual End-to-End Test

Before calling the evaluator, run this exact type of test.

## Step 1

Use existing Sarvam agent to call a test phone.

---

## Step 2

Respond in Hinglish:

```text
Main fashion products sell karta hoon.
Around 200 products hain.
Payments aur inventory chahiye.
Budget around 80 thousand hai.
Do weeks mein launch karna hai.
```

---

## Step 3

Express strong intent:

```text
How soon can you start?
Send me the details.
```

Expected:

```text
send_high_intent_whatsapp fires
real WhatsApp arrives before call ends
```

---

## Step 4

Request callback:

```text
Kal 11 baje call karna.
```

Expected:

```text
callback saved
scheduler job created
```

---

## Step 5

Initial call ends.

Expected:

```text
complete_call runs
lead data stored
final WhatsApp sent
resume sent
architecture image sent
```

---

## Step 6

At scheduled time:

```text
same existing Sarvam agent calls again
```

Expected:

```text
previous conversation context is available
agent references real details from previous call
```

---

# 29. What Codex Must NOT Build

Do not build:

```text
new Sarvam agent
second callback agent
new voice prompt from scratch
custom STT
custom TTS
frontend
admin dashboard
LangGraph
vector database
Kubernetes
microservices
CRM
analytics dashboard
authentication system
```

The existing Sarvam Voice Agent already handles the voice interaction.

---

# 30. Priority Order

## P0 — First

1. FastAPI boots.
2. `/health` works.
3. Database works.
4. Real `send_high_intent_whatsapp` endpoint works.
5. Existing Sarvam tool points to it.
6. A real WhatsApp arrives during an active Sarvam call.

STOP HERE AND VERIFY.

Do not continue until this works end-to-end.

---

## P1

7. `complete_call`
8. lead persistence
9. final follow-up WhatsApp
10. resume attachment
11. architecture image attachment

---

## P2

12. `schedule_callback`
13. callback persistence
14. APScheduler
15. same Sarvam agent outbound callback
16. previous context injection

---

## P3

17. tests
18. logging
19. deployment
20. README
21. architecture diagram

---

# 31. Definition of Done

The backend is complete only when this flow works:

```text
Existing Sarvam agent calls prospect
        ↓
Prospect speaks Hindi/English/Telugu
        ↓
Existing agent qualifies prospect
        ↓
HOT intent detected
        ↓
Real WhatsApp arrives mid-call
        ↓
Prospect asks for callback
        ↓
Callback stored
        ↓
Call ends
        ↓
Final follow-up + resume + architecture sent
        ↓
Scheduled time arrives
        ↓
SAME Sarvam agent calls again
        ↓
Previous conversation context is used naturally
```

---

# 32. Engineering Principle

Build around what already works.

Do not duplicate Sarvam functionality.

Optimize for:

```text
working > clever
real integrations > mocks
small > overengineered
reliable > fancy
reuse existing agent > rebuild
```

The goal is not to create another voice platform.

The goal is to make the already-created Sarvam agent perform real business actions end-to-end.