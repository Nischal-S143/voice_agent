# Deploying the backend

The Cloudflare quick tunnel changes URL every restart, which means re-editing
all three Sarvam tool URLs each time. Deploying gives one permanent URL.

Railway is the shortest path; `render.yaml` is included if you prefer Render.

---

## What the deploy files do

| File | Purpose |
|---|---|
| `Procfile` | `release` runs migrations, `web` starts uvicorn on `$PORT` |
| `railway.json` | Railway build/start config plus `/health` healthcheck |
| `render.yaml` | Equivalent Render blueprint with the env var list |
| `runtime.txt` | Pins Python 3.11.7 |
| `scripts/migrate.py` | Runs Alembic against `DIRECT_URL` (session-mode pooler) |

**Why a separate migrate step:** the app runs against Supabase's transaction
pooler on port 6543, which is fine for queries but not for DDL. `scripts/migrate.py`
swaps in `DIRECT_URL` (port 5432, session mode) for the upgrade only.

---

## Railway

1. Push this repo to GitHub.
2. On [railway.app](https://railway.app): **New Project → Deploy from GitHub repo**.
3. Open **Variables** and paste every var from the table below.
   Railway reads `railway.json`, so no start command needs typing.
4. Deploy. Watch the logs for `migrate: done`, then `Uvicorn running`.
5. **Settings → Networking → Generate Domain** for a permanent HTTPS URL.
6. Check `https://<your-domain>/health` returns `{"status":"ok"}`.
7. Update the three Sarvam tool URLs to the new domain.

## Render

Same idea: **New → Blueprint**, point at the repo, fill the `sync: false` vars
when prompted. `render.yaml` already sets the build, pre-deploy and start commands.

---

## Environment variables

Copy the values from your local `.env`. Everything marked **secret** should
never be committed.

| Variable | Notes |
|---|---|
| `DATABASE_URL` | Supabase pooler on **6543**. Do not append `?pgbouncer=true` — asyncpg rejects it as an unknown connect kwarg. |
| `DIRECT_URL` | Same credentials on **5432**. Used only by `scripts/migrate.py`. |
| `SUPABASE_URL` | `https://<project-ref>.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | **secret** — the `sb_secret_...` key, not the publishable one |
| `SUPABASE_STORAGE_BUCKET` | `sales-agent-assets` |
| `SUPABASE_RESUME_OBJECT_PATH` | Path of the resume object in the bucket |
| `SUPABASE_ARCHITECTURE_OBJECT_PATH` | Path of the architecture image |
| `WHAPI_BASE_URL` | `https://gate.whapi.cloud` |
| `WHAPI_TOKEN` | **secret** |
| `SARVAM_TOOL_SECRET` | **secret** — must match the `X-Tool-Secret` header on all three tools |
| `SARVAM_API_BASE` | `https://apps.sarvam.ai` (the API host, not the `indus.sarvam.ai` dashboard) |
| `SARVAM_API_KEY` | **secret** |
| `SARVAM_ORG_ID` | |
| `SARVAM_WORKSPACE_ID` | |
| `SARVAM_APP_ID` | |
| `SARVAM_APP_VERSION` | Leave blank to call the latest published version |
| `SARVAM_VERSION_FILTER` | Leave blank; the adapter picks `latest` or `specific` |
| `SARVAM_CONNECTION_ID` | |
| `SARVAM_AGENT_PHONE_NUMBER` | The from-number, E.164 |
| `DEFAULT_TIMEZONE` | `Asia/Kolkata` |
| `CALLBACK_POLL_SECONDS` | `15` |
| `CALLBACK_SIGNED_URL_TTL_SECONDS` | `900` |
| `DEVELOPER_NAME` | Signed at the end of the follow-up WhatsApp |
| `DEVELOPER_PHONE` | Included in the follow-up WhatsApp |

> Do **not** upload the `.env` file itself. `Settings` forbids unknown keys in a
> dotenv **file**, so a stray line breaks startup. Extra OS environment
> variables are ignored safely, which is why `DIRECT_URL` works as a platform
> variable but not as an `.env` line.

---

## After deploying

1. Update all three Sarvam tool URLs to `https://<your-domain>/tools/...`.
2. Re-check auth end to end:

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  https://<your-domain>/tools/complete-call \
  -H "Content-Type: application/json" -d '{}'          # expect 401

curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  https://<your-domain>/tools/complete-call \
  -H "Content-Type: application/json" \
  -H "X-Tool-Secret: <your secret>" -d '{}'            # expect 422
```

`401` then `422` means the deploy is wired correctly: the secret is enforced and
the endpoint is reachable.

## Notes

- **Keep one instance.** Callbacks are claimed with `SELECT ... FOR UPDATE
  SKIP LOCKED`, so extra replicas would not double-dial, but a single instance
  keeps scheduler polling minimal.
- **Free tiers sleep.** A sleeping instance means the agent's tool calls fail
  mid-call. Use a paid tier, or keep it warm, before any live demo.
- The scheduler starts with the app; there is no separate worker to deploy.
