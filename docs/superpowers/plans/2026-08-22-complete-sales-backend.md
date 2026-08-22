# Complete Sales Voice-Agent Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the Whapi FastAPI service with Supabase-backed leads, calls, events, durable message idempotency, final follow-ups, authenticated tools, and scheduled callback processing behind a replaceable outbound-caller interface.

**Architecture:** SQLAlchemy repositories transact against a private `sales_agent` PostgreSQL schema managed by Alembic. FastAPI routes delegate to orchestration services; APScheduler polls durable callback rows; Whapi and Supabase Storage remain external adapters; the initial Sarvam outbound adapter is explicitly unconfigured.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.x async, asyncpg, Alembic, APScheduler, Supabase Python client, HTTPX, Pydantic Settings, pytest, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-08-22-complete-sales-backend-design.md`

## Global Constraints

- Preserve the existing Sarvam voice agent and prompt; do not create or modify an agent.
- Do not implement or guess a Sarvam outbound REST request.
- Whapi remains the only WhatsApp provider.
- Business tables live in private PostgreSQL schema `sales_agent` with no `anon` or `authenticated` grants.
- All `/tools/*` routes require `X-Tool-Secret` using constant-time comparison.
- External calls occur outside database transactions and row locks.
- Never log tokens, credentials, authorization headers, database URLs, service-role keys, or raw provider exceptions.
- Callback time must be timezone-aware; unresolved expressions without a resolved timestamp are rejected.
- No frontend, CRM, containers, analytics, authentication accounts, or vector database.
- The directory is not a Git repository, so verification checkpoints replace commit steps.

---

### Task 1: Dependencies, configuration, database session, and authentication

**Files:**
- Modify: `pyproject.toml`
- Modify: `.env.example`
- Modify: `app/config.py`
- Create: `app/database.py`
- Create: `app/api/dependencies.py`
- Modify: `app/main.py`
- Create: `tests/test_config.py`
- Create: `tests/test_tool_auth.py`

**Interfaces:**
- Produces: `Settings.database_url`, Supabase/Storage/scheduler settings, `create_engine_and_session_factory(settings)`, `get_session(request)`, and `verify_tool_secret(request)`.

- [ ] **Step 1: Add tests that construct `Settings` from explicit environment values, verify secret values are represented as `SecretStr`, and verify `/health` boots without integration credentials**
- [ ] **Step 2: Add API tests proving missing, wrong, and unconfigured `X-Tool-Secret` return the same `401 {"detail":"unauthorized"}`, while the correct secret reaches a tool handler**
- [ ] **Step 3: Run `python -m pytest tests/test_config.py tests/test_tool_auth.py -v`; confirm failures identify missing settings and authentication dependency**
- [ ] **Step 4: Pin `SQLAlchemy`, `asyncpg`, `Alembic`, `APScheduler`, and `supabase` dependencies; expand `.env.example` exactly from the approved design**
- [ ] **Step 5: Implement lazy async engine/session creation so health remains available without `DATABASE_URL`; normalize `postgresql://` and Supabase pooler URLs to the asyncpg driver only inside database setup**
- [ ] **Step 6: Implement constant-time `X-Tool-Secret` verification with `secrets.compare_digest`, attach it to the tools router, and keep dependency overrides available for tests**
- [ ] **Step 7: Run the focused tests and then `python -m pytest -v`; require a clean pass before continuing**

### Task 2: PostgreSQL models and Alembic migration

**Files:**
- Create: `app/models/__init__.py`
- Create: `app/models/base.py`
- Create: `app/models/lead.py`
- Create: `app/models/call.py`
- Create: `app/models/callback.py`
- Create: `app/models/event.py`
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `alembic/versions/20260822_0001_sales_backend.py`
- Create: `tests/test_models.py`
- Create: `tests/test_migration_contract.py`

**Interfaces:**
- Produces: `Lead`, `Call`, `Callback`, `Event`, `CallDirection`, `CallbackStatus`, and `EventType` SQLAlchemy mappings.

- [ ] **Step 1: Add model tests for lead phone uniqueness, call provider-ID uniqueness, indexed foreign keys, enum/check values, timezone-aware columns, and JSONB fields**
- [ ] **Step 2: Add a migration-contract test that imports the migration and inspects emitted SQL for `sales_agent` schema creation, identity keys, FK indexes, pending-callback partial index, uniqueness constraints, and revoked `anon`/`authenticated` privileges**
- [ ] **Step 3: Run the two focused files; confirm they fail because models and migration do not exist**
- [ ] **Step 4: Implement focused SQLAlchemy models using `bigint identity`, `text`, `timestamptz`, and PostgreSQL JSONB; use named constraints and explicit indexes**
- [ ] **Step 5: Implement an imperative Alembic migration whose `upgrade()` creates the private schema, four tables, constraints and indexes, and revokes public Supabase roles; `downgrade()` drops only these objects in dependency order**
- [ ] **Step 6: Run focused tests and `python -m compileall -q app alembic tests`; require success**

### Task 3: Repositories and durable event idempotency

**Files:**
- Create: `app/repositories/__init__.py`
- Create: `app/repositories/leads.py`
- Create: `app/repositories/calls.py`
- Create: `app/repositories/events.py`
- Create: `app/repositories/callbacks.py`
- Create: `tests/test_repositories.py`

**Interfaces:**
- Produces: `LeadRepository.upsert_by_phone`, `CallRepository.upsert_by_sarvam_call_id`, `EventRepository.append`, `EventRepository.reserve_delivery`, `EventRepository.complete_delivery`, `EventRepository.release_delivery`, `CallbackRepository.schedule`, `claim_due`, `mark_triggered`, and `mark_failed`.

- [ ] **Step 1: Write repository tests against an async test session/fake boundary covering lead and call upserts, append-only events, duplicate callback prevention, and successful-delivery reservation semantics**
- [ ] **Step 2: Add a concurrency contract test proving two reservations for `(call_id, HIGH_INTENT_WHATSAPP_SENT)` yield one owner and one duplicate result**
- [ ] **Step 3: Run `python -m pytest tests/test_repositories.py -v`; confirm missing repository failures**
- [ ] **Step 4: Implement repositories with short transaction-friendly methods and PostgreSQL `INSERT ... ON CONFLICT`; never commit from a repository method**
- [ ] **Step 5: Implement callback claim SQL with `SELECT ... FOR UPDATE SKIP LOCKED`, ordered by `coalesce(next_attempt_at, scheduled_at)`, and update claim/attempt metadata before returning**
- [ ] **Step 6: Run repository and migration tests; require success**

### Task 4: Supabase Storage and final follow-up orchestration

**Files:**
- Create: `app/services/storage_service.py`
- Create: `app/services/followup_service.py`
- Modify: `app/services/message_builder.py`
- Create: `tests/test_storage_service.py`
- Create: `tests/test_followup_service.py`

**Interfaces:**
- Produces: `StorageService.create_signed_url(object_path: str) -> str`, `build_final_followup(request, settings) -> str`, and `FollowupService.send_for_call(call_id, phone, message) -> FollowupResult`.

- [ ] **Step 1: Write Storage tests for signed URL extraction, missing-object failure, malformed response failure, and secret-safe errors using a fake Supabase client**
- [ ] **Step 2: Write follow-up tests proving text/document/image order, continuation after failure, and retry sends only components without a recorded successful event**
- [ ] **Step 3: Write copy tests proving absent values are omitted and internal classification data is never rendered**
- [ ] **Step 4: Run focused tests; confirm missing services/builders fail**
- [ ] **Step 5: Implement private-bucket signed URL generation using configured bucket, object paths, and TTL**
- [ ] **Step 6: Implement follow-up orchestration that queries component events, sends each missing component, records sanitized success/failure events, and returns per-component booleans**
- [ ] **Step 7: Run focused tests and existing Whapi tests; require success**

### Task 5: Persisted high-intent and complete-call endpoints

**Files:**
- Modify: `app/schemas/whatsapp.py`
- Create: `app/schemas/complete_call.py`
- Modify: `app/api/tools.py`
- Create: `app/services/call_service.py`
- Modify: `app/main.py`
- Modify: `tests/test_high_intent_endpoint.py`
- Create: `tests/test_complete_call.py`

**Interfaces:**
- Produces: database-backed `POST /tools/send-high-intent-whatsapp`, `CompleteCallRequest`, `CompleteCallResponse`, and `CallService.complete_call`.

- [ ] **Step 1: Replace endpoint tests' in-memory expectation with a fake durable reservation repository; retain first-send, duplicate, concurrent, failed-and-retry behaviors**
- [ ] **Step 2: Add complete-call tests for lead/call upsert, `CALL_COMPLETED`, contextual follow-up, duplicate call completion, and independent attachment results**
- [ ] **Step 3: Run focused endpoint tests; confirm failures identify absent orchestration**
- [ ] **Step 4: Implement `CompleteCallRequest` with every original-spec field, timezone-aware optional call timestamps, and defaults for list fields**
- [ ] **Step 5: Implement `CallService.complete_call`: normalize, transact lead/call/event persistence, commit, then invoke `FollowupService` outside the transaction**
- [ ] **Step 6: Refactor high-intent route to durable reservation semantics, leaving a test-injectable in-memory fallback only when no database dependency is configured for unit tests**
- [ ] **Step 7: Run complete-call, high-intent, message-builder, and Whapi suites; require success**

### Task 6: Callback endpoint, worker, and outbound interface

**Files:**
- Create: `app/schemas/callback.py`
- Create: `app/services/outbound_caller.py`
- Create: `app/services/callback_service.py`
- Modify: `app/api/tools.py`
- Create: `tests/test_callback_endpoint.py`
- Create: `tests/test_callback_worker.py`

**Interfaces:**
- Produces: `ScheduleCallbackRequest`, `SarvamOutboundCaller` protocol, `OutboundCallRequest`, `OutboundCallResult`, `UnconfiguredSarvamOutboundCaller`, `CallbackService.schedule`, and `CallbackService.process_due`.

- [ ] **Step 1: Write endpoint tests proving persistence-before-success, duplicate scheduling, offset-required timestamps, and `callback_time_required` when unresolved**
- [ ] **Step 2: Write worker tests proving compact previous context is loaded, the adapter receives the normalized phone and context, successful adapters create a callback call and mark `TRIGGERED`, and the unconfigured adapter marks `FAILED` without retry**
- [ ] **Step 3: Run callback tests; confirm missing schema/service failures**
- [ ] **Step 4: Implement callback schemas with timezone-aware validation and stable structured response/error models**
- [ ] **Step 5: Implement the outbound protocol and safe unconfigured adapter with no network code**
- [ ] **Step 6: Implement scheduling transaction and worker state transitions; ensure all adapter calls occur after the claim transaction commits**
- [ ] **Step 7: Run all callback tests and repository tests; require success**

### Task 7: APScheduler lifecycle and application wiring

**Files:**
- Create: `app/scheduler/__init__.py`
- Create: `app/scheduler/scheduler.py`
- Modify: `app/main.py`
- Create: `tests/test_scheduler.py`

**Interfaces:**
- Produces: `create_scheduler(callback_service, poll_seconds) -> AsyncIOScheduler`, `start_scheduler`, and `shutdown_scheduler`.

- [ ] **Step 1: Write tests using a fake scheduler/clock proving one interval job is registered with stable ID `process-due-callbacks`, duplicate startup replaces rather than duplicates it, and shutdown is graceful**
- [ ] **Step 2: Run `python -m pytest tests/test_scheduler.py -v`; confirm missing scheduler failures**
- [ ] **Step 3: Implement APScheduler wiring with `max_instances=1`, `coalesce=True`, and a configurable interval; the job delegates only to `CallbackService.process_due`**
- [ ] **Step 4: Extend FastAPI lifespan to create database, Storage, repositories, services, outbound stub, and scheduler only when configured; close HTTP/database resources on shutdown**
- [ ] **Step 5: Run scheduler tests, lifespan tests, and the full suite; require success without wall-clock sleeps or external HTTP**

### Task 8: Documentation, migrations, and end-to-end verification

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Modify: `docs/superpowers/plans/2026-08-22-complete-sales-backend.md`

**Interfaces:**
- Produces: reproducible local setup, Supabase migration, Storage upload, Sarvam tool configuration, scheduler behavior, and manual acceptance instructions.

- [ ] **Step 1: Document dependency installation, required Supabase pooled database URL, `alembic upgrade head`, private bucket/object paths, server startup, and all three authenticated tool requests**
- [ ] **Step 2: Document the callback limitation and exact adapter interface needed when a Sarvam Campaign/dialer contract becomes available**
- [ ] **Step 3: Run `python -m pytest -v`; require zero failures and warnings**
- [ ] **Step 4: Run `python -m compileall -q app alembic tests`; require exit code zero**
- [ ] **Step 5: Start Uvicorn without credentials, call `/health`, and verify it remains healthy; verify protected tool routes return generic `401`**
- [ ] **Step 6: Search application/config/test files for accidental real secrets and forbidden integrations (`Twilio`, guessed Sarvam URLs, containers); remove any violations**
- [ ] **Step 7: If Supabase credentials are available, run Alembic against the `sales_agent` project and execute a read/write smoke transaction; otherwise report this as the only database acceptance step not locally verifiable**
- [ ] **Step 8: Report real Whapi/Storage delivery and real outbound callback calling separately: the former requires user credentials/assets, while the latter remains intentionally unavailable until an adapter contract exists**
