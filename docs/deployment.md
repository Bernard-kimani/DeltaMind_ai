# Deployment (Render) — cutover checklist

Status: **prep only, not yet deployed.** `backend/Dockerfile` and
`render.yaml` exist so the team can cut over from local Windows dev to
Render quickly, but nothing has been deployed or end-to-end tested yet. See
item (f) below before treating this as deploy-ready.

**2026-08-27 fixes (found while actually walking through the cutover):**

- `backend/Dockerfile` was missing `COPY scripts ./scripts` — the image only
  ever copied `app/`, but `agent_loop_manager.py` launches the live engine as
  a subprocess of `backend/scripts/run_agent_stream_track1.py` /
  `run_agent_loop.py`. Without this, every "Start engine" click on Render
  would have failed immediately (file not found) with no prior warning.
  Fixed.
- `render.yaml`'s backend service was on the free plan, which spins the
  container down after 15 minutes with no inbound HTTP request. This app's
  actual workload (the live Alpaca websocket stream + trading subprocess)
  generates no inbound HTTP traffic of its own — a free-tier sleep would
  silently kill live trading mid-session with nothing to wake it back up
  except a judge/user happening to hit the frontend. Changed to `starter`.
- Added `ALPACA_API_KEY_TRACK4`/`ALPACA_SECRET_KEY_TRACK4` as `sync: false`
  placeholders in `render.yaml`, matching `.env.example` — leave unset until
  the second paper account exists (falls back to the shared pair, same as
  local dev).

## (a) Environment variables

Source of truth today is `backend/.env` (a copy of the repo-root
`.env.example` with real values filled in, per `backend/app/config.py`'s
`Settings(BaseSettings)` — `env_file=".env"`). When cutting over, copy each
value from `backend/.env` into the Render dashboard for the
`deltamind-backend` service (or fill them in when Render prompts you during
Blueprint creation, for the `sync: false` entries in `render.yaml`).

| Variable | Source today | Notes |
|---|---|---|
| `ALPACA_API_KEY` | `backend/.env` | Track 1's account. Create a **new** paper account key on Day 1 (Aug 28) per the comment in `.env.example` — don't reuse the pre-hackathon dev key. |
| `ALPACA_SECRET_KEY` | `backend/.env` | Track 1's account, same as above. |
| `ALPACA_API_KEY_TRACK4` | `backend/.env` | Track 4's **separate** account. Submissions score each track independently, so Track 1 and Track 4 can't share one account's fills/P&L at submission time — create a second new paper account for this. Leave unset during dev/testing (both tracks fall back to the shared pair above — see `app/config.py`'s `get_alpaca_credentials`). |
| `ALPACA_SECRET_KEY_TRACK4` | `backend/.env` | Track 4's account, same as above. |
| `ALPACA_PAPER` | `backend/.env` | `true` for paper trading. |
| `ALPACA_TRADE_API_URL` | `backend/.env` | `https://paper-api.alpaca.markets` |
| `ALPACA_DATA_API_URL` | `backend/.env` | `https://data.alpaca.markets` |
| `LLM_PROVIDER` | `backend/.env` | `featherless` \| `fireworks` \| `anthropic` |
| `LLM_MODEL` | `backend/.env` | e.g. `moonshotai/Kimi-K2-Instruct` |
| `LLM_FALLBACK_MODEL` | `backend/.env` | e.g. `deepseek-ai/DeepSeek-V3` |
| `FEATHERLESS_API_KEY` | `backend/.env` | Preferred provider — avoid direct Anthropic spend. |
| `FEATHERLESS_BASE_URL` | `backend/.env` | `https://api.featherless.ai/v1` |
| `FIREWORKS_API_KEY` | `backend/.env` | Fallback provider. |
| `FIREWORKS_BASE_URL` | `backend/.env` | `https://api.fireworks.ai/inference/v1` |
| `ANTHROPIC_API_KEY` | `backend/.env` | Optional — only needed if `LLM_PROVIDER=anthropic`; incurs direct API cost, avoid unless required. |
| `DATABASE_URL` | Render-provisioned | See (b) — do **not** copy the local sqlite value. |
| `APP_ENV` | new | Set to `production` on Render (local dev uses `development`). |
| `LOG_LEVEL` | `backend/.env` | `INFO` |
| `BACKEND_CORS_ORIGINS` | new | Set to the deployed frontend's origin (see (e)), not `http://localhost:5173`. |

Frontend (`frontend/.env.example`), set at build time on whatever platform
builds the static site:

| Variable | Notes |
|---|---|
| `VITE_API_BASE_URL` | Set to the Render backend's public URL, e.g. `https://deltamind-backend.onrender.com`. |
| `VITE_WS_URL` | Set to the backend's WS URL, e.g. `wss://deltamind-backend.onrender.com/ws/live`. |

## (b) Database

`backend/app/config.py`'s `database_url` defaults to
`sqlite:///./deltamind.db`, but `DATABASE_URL` is read straight from the
environment via `pydantic-settings` — no code changes needed to point at
Postgres. `backend/pyproject.toml` already declares a `postgres` extra
(`psycopg2-binary`), installed in `backend/Dockerfile`.

`render.yaml` provisions a managed Postgres database (`deltamind-db`) and
wires its connection string into the backend service automatically via
`fromDatabase: { name: deltamind-db, property: connectionString }` — no
manual copy-paste needed for this one var. Confirm at cutover time that the
resulting `postgresql://...` URL is accepted as-is by SQLAlchemy + psycopg2
(may need a `postgresql+psycopg2://` scheme rewrite if SQLAlchemy's dialect
resolution doesn't infer it automatically — check on first real deploy).

Note: the free Postgres plan in `render.yaml` expires ~30 days after
creation. Fine for prep, but switch to a paid plan before/at the point this
needs to stay up through the actual hackathon window (Aug 28–Sep 4).

## (c) `config_store.py` plaintext-on-Linux gap

`backend/app/config_store.py` encrypts API keys written via the Controls
UI ("Save Changes") using Windows DPAPI (`win32crypt`). On Linux (i.e. the
Render container), `win32crypt` isn't available, so the `except ImportError`
fallback kicks in: keys get written to `backend/.runtime_config.json` in
**plaintext**, with a logged warning
(`"win32crypt unavailable — API keys in .runtime_config.json will NOT be
encrypted at rest."`). This doesn't crash the app, but it's a real gap on
Linux.

Confirmed: `backend/app/config.py`'s `Settings` class (pydantic
`BaseSettings`) reads all config from environment variables / `.env` — this
is the actual source of truth read at process startup and by
`config_store.py`'s `_defaults()`. The runtime config store only holds
*overrides* set live through the Controls UI.

**Mitigation for this prep pass:** on Render, don't use the Controls tab's
"Save Changes" button in production. Rely on the platform's env-var store
(Render dashboard / `render.yaml` `sync: false` entries) only, and leave the
LLM provider/model/API-key fields in Controls untouched so they keep
falling back to the env-sourced defaults instead of writing a plaintext
`.runtime_config.json`.

## (d) Out of scope for this pass

A code-level production guard — e.g. `config_store.save()` refusing to
write API keys to `.runtime_config.json` when `APP_ENV=production`, forcing
env-vars-only in that mode — would be more robust than the manual
"just don't click Save Changes" mitigation above. This is a good candidate
to implement before the actual cutover, but is explicitly out of scope for
this prep pass.

## (e) Frontend deploy

The frontend is a standard Vite SPA (`tsc -b && vite build` → `frontend/dist/`,
no SSR) and is deployed **separately** from the backend — as a Render
Static Site or on Vercel, not mounted under FastAPI (`backend/app/main.py`
serves API routes only, no static-file mounting was added).

1. `cd frontend && npm run build` → produces `frontend/dist/`.
2. Deploy `frontend/dist` as a Render Static Site (or Vercel project) with:
   - `VITE_API_BASE_URL` = the deployed backend's URL (e.g.
     `https://deltamind-backend.onrender.com`)
   - `VITE_WS_URL` = the deployed backend's WS URL (e.g.
     `wss://deltamind-backend.onrender.com/ws/live`)
   Both are build-time Vite env vars — set them on whichever platform builds
   the static site, then rebuild.
3. Once the frontend's real origin is known, set `BACKEND_CORS_ORIGINS` on
   the backend service to that origin (comma-separated if there's more than
   one, e.g. a preview URL and a production URL).

## (f) Not yet tested end-to-end

This whole deployment path — Docker build, Render web service + managed
Postgres, frontend static site pointed at it — has **not** been tested
end-to-end yet. `backend/Dockerfile` has not even been build-tested locally:
Docker isn't installed in the dev environment this was prepped in, so the
build itself is unverified, not just the deploy. Confirming `docker build -t
deltamind-backend backend/` succeeds should be the very first step once
Docker is available, well before relying on any of this.
The first real deploy should happen with time to spare before Aug 28, not
as a last-minute scramble — leave a buffer to debug things like the
`DATABASE_URL` scheme question in (b), CORS origin mismatches, and the MCP
server (`uvx alpaca-mcp-server`) actually launching correctly inside the
container.
