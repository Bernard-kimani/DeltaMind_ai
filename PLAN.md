# DeltaMind AI — Plan & Context

**This is the living source of truth for the project.** Update it as decisions change — don't let it drift from reality. Everything else (code, memory) can be re-derived; this file carries the *why*.

Last updated: 2026-08-19 (session 2)

---

## 1. What this is

An autonomous multi-agent options-trading system built for the **Alpaca AI Trading Agents Hackathon** (lablab.ai × Alpaca).

- **Event window:** Aug 28 – Sep 4, 2026 (7 days, online)
- **Prize pool:** $5,000 total ($2,500 / $1,500 / $1,000 top 3), funded by AlpacaDB
- **What's judged:** paper-trading P&L, technology implementation (Alpaca Trading API / MCP Server v2 / CLI depth), creativity, presentation, and build-in-public social engagement
- **Core constraint:** the agent must run *live* on a **brand-new** Alpaca paper account created on Day 1 (Aug 28) — no pre-existing trade history, no trades before the account exists. Everything else (scaffolding, math libraries, backtesting, UI) can be built now.

Full hackathon rules and strategy detail are in the brief the user provided at project kickoff (not duplicated here — see chat history / lablab.ai listing for the source).

---

## 2. Timeline

| Phase | Dates | What happens |
|---|---|---|
| **Pre-hackathon (now)** | 2026-08-19 → 2026-08-27 | Build everything in this repo: backend scaffolding, quant math, agent graph, UI, backtester. Test against a *throwaway* dev paper account — never the submission account. |
| **Day 1** | 2026-08-28 | Register the fresh submission paper account. Swap `.env` credentials. Deploy a Minimum Viable Agent immediately — don't wait for a "perfect" system. |
| **Days 2–6** | 2026-08-29 → 2026-09-02 | Keep the live loop running continuously (accumulating real trade history for judging) while refining prompts/signals/reasoning in the background. Post build-in-public updates on X/LinkedIn (up to 5, tagging @lablabai and @AlpacaHQ). |
| **Day 6 wrap** | 2026-09-03 | Freeze trading code. Record the 5-minute demo video. Export slide deck to PDF. Clean up the GitHub repo. |
| **Day 7** | 2026-09-04 | Submit via lablab.ai dashboard before deadline. |

**Why deploy Day 1, not Day 7:** judges evaluate trade *history*, not just a final number — a system with one lucky trade on the last day scores poorly on both P&L consistency and Technology Implementation.

---

## 3. Architecture

Multi-agent pipeline, orchestrated as a LangGraph state graph, one cycle per watched symbol:

```
market_ingestion → quant_engine → news_analyst → lead_architect → risk_gate
                                                                       │
                                                        risk_approved? │
                                                    yes ┌──────────────┴──────────────┐ no
                                                        ▼                             ▼
                                                    execution                    END (logged,
                                                        │                        no trade)
                                                        ▼
                                                       END
```

| Node | File | LLM? | Responsibility |
|---|---|---|---|
| Market Ingestion | `backend/app/agents/market_ingestion.py` | No | Pull bars + option chain via Alpaca REST |
| Quant Engine | `backend/app/agents/quant_engine.py` | **No — deterministic** | Greeks, IV percentile, portfolio risk. Pure math, auditable, reproducible. |
| News Analyst | `backend/app/agents/news_analyst.py` | Yes | Sentiment score from headlines (via MCP `get_news`) |
| Lead Architect | `backend/app/agents/lead_architect.py` | Yes | Synthesizes quant + sentiment into a thesis, delegates to the active track's strategy module for an order proposal |
| Risk Gate | `backend/app/agents/risk_gate.py` | **No — deterministic circuit breaker** | Hard guardrails: max position size, margin utilization, mandatory stop-loss, order structure validation |
| Execution | `backend/app/agents/execution.py` | No | Dispatches the approved order via the Alpaca MCP client, persists the result |

**Why quant + risk gate are LLM-free:** judges need to be able to read those two files and verify the guardrails hold — no prompt-injection or hallucination surface on the parts of the system that touch capital directly.

---

## 4. Tech stack decisions

| Area | Choice | Why |
|---|---|---|
| Agent orchestration | **LangGraph** | Explicit state graph matches the strict linear pipeline above; keeps the deterministic risk gate cleanly separated from LLM nodes; good tracing for the demo/judges. |
| Backend API | **FastAPI** | Async-native, built-in WebSocket support for streaming live agent/trade events to the dashboard, Pydantic models pair naturally with MCP tool schemas. |
| LLM provider | **Featherless / Fireworks (OpenAI-compatible endpoints)**, selectable per-provider via the Controls tab, 4 models offered on each: **Kimi K2 Instruct (default), DeepSeek-V3, Qwen2.5 72B Instruct, Llama 3.3 70B Instruct** | Anthropic API billing is **separate from the Claude Code subscription** — direct API calls cost extra per token. User has free Featherless + Fireworks credits, so the reasoning nodes default there at $0 marginal cost. Client is provider-agnostic (`backend/app/llm/client.py`) — an Anthropic adapter is wired in and can be flipped on later if quality demands it and cost is acceptable. Model list in `frontend/src/features/controls/models.ts`, cross-checked against real slugs used in two of the user's other projects (Auditflow's `featherless.js`, Aero_claw's `server.cjs`) plus a live catalog fetch. **Always confirm with the Controls tab's "Test API" button before relying on a model live — provider catalogs drift.** |
| Database | **SQLite** now, **Supabase Postgres**-ready later | Zero setup, easy for judges to inspect (`deltamind.db` ships in the repo/demo), plenty for a week of trade volume. All access goes through `backend/app/db/repository.py`, and models are plain SQLAlchemy — pointing `DATABASE_URL` at the user's existing Supabase instance post-hackathon is a config change, not a rewrite. |
| Frontend | **React + TypeScript + Vite** | Per user requirement. Talks to FastAPI over REST (`/api/*`) and WebSocket (`/ws/live`) for the live reasoning feed. |
| Market/execution interface | **Alpaca MCP Server v2** for execution + news; **alpaca-py REST** for high-frequency data pulls and backtesting | MCP gives every live order an auditable tool-call trail (scores well on Technology Implementation); going through an LLM/MCP round-trip for routine bar polling would be pure overhead, so that stays on direct REST. CLI wrapper (`backend/app/alpaca/cli_wrapper.py`) is scaffolded for future low-overhead cron/health-check use. |

---

## 5. Open decision: which hackathon track?

The four tracks (see brief) each map to one strategy module, all already scaffolded in `backend/app/strategies/`:

| Track | Module | Structure | Best regime |
|---|---|---|---|
| 1. Options Alpha | `track1_alpha_spreads.py` | Vertical debit spreads (0.70Δ long / 0.30Δ long-side, 14 DTE) | Strong trend/momentum |
| 2. Volatility & Events | `track2_volatility_events.py` | Long strangle (IV%<25) / iron condor (IV%>85) around earnings | Pre-earnings / macro events |
| 3. Hedging & Protection | `track3_hedging.py` | Collar triggered at >3.5% portfolio drawdown | High volatility / drawdowns |
| 4. Income & Overlay | `track4_income_wheel.py` | The Wheel — 0.30Δ cash-secured puts → covered calls | Sideways/range-bound |

**Decided: Track 1 (Options Alpha) is the primary submission track.** Clearest, most demo-able thesis ("technical breakout + bullish sentiment → debit spread"), the most straightforward P&L story for judges. Track 4 (Wheel) is the agreed-on fallback if the week turns out range-bound instead of trending. **All four modules exist and share the same `propose_order(state, thesis) -> order` interface**, so switching — or running multiple tracks on different symbols simultaneously — is a config change (the Controls tab's Track dropdown, or `run_agent_loop.py --track`), not a rewrite. The Strategies tab documents all four side by side for exactly this reason: the fallback is one click away, not a rebuild.

---

## 6. UI design system

The dashboard's visual identity is deliberately ported from a sibling project's proven design system (same component architecture, same Tailwind-v4-tokens-as-CSS-variables approach, same font pairing) — re-themed, not re-designed from scratch, and re-skinned with DeltaMind's own colors and copy.

| Aspect | This project | Ported from | Why |
|---|---|---|---|
| Palette | Charcoal black `#121212` (dark, default) / premium off-white `#faf9f7` (light), single accent **International Orange (Aerospace) `#FF4F00`** in both themes | Sibling project's charcoal-black / cream palette with a gold accent | User explicitly requested this swap — same structure, different identity. Hex confirmed via web search, not guessed. |
| Token file | `frontend/src/styles/theme.css` — the single editable source for every color and font; a `:root` block (light) and a `.dark` block (dark) feed a Tailwind v4 `@theme` block, so editing a hex here propagates everywhere with no component changes | Same `:root`/`.dark`/`@theme` structure | This is the "themes file" the user asked for — swap the accent or the whole palette in one file. |
| Fonts | Fraunces (display/headline), IBM Plex Sans (UI), IBM Plex Mono (data/tabular), Wallpoet (logo mark only) | Identical pairing | Kept as-is — it's part of what made the reference project's style read as "premium instrument panel," not something specific to that project's brand. |
| Components | `frontend/src/components/primitives.tsx` — Section, Card, Button, TextField, Select, StatTile, StatusDot, DecisionRow, PositionRow, Spinner | Same primitives, same Tailwind utility patterns; `SignalRow`→`DecisionRow`, `PositionRow` re-mapped to Alpaca's Account/Position shape | Structural pattern reused; field names and data are 100% DeltaMind's own — nothing about options trading was copied, only "how a card/button/status-dot looks." |
| Pages | Landing (Console gate) → 4-tab app shell (Controls / Strategies / Backtest / Logs) | Same shell shape | Controls = AI Configuration + Telemetry + **Agent Engine** (renamed from "Server Engine" — controls `scripts/run_agent_loop.py` as a subprocess, not a second web server) + Live Trading Activity. Strategies = read-only reference cards for the 4 tracks (not the original's image-template editor — different domain entirely). Backtest = form + stat tiles. Logs = byte-offset-tailed log viewer parsing the same `%(asctime)s - %(name)s - %(levelname)s - %(message)s` format. |
| Landing page | CSS/SVG grid-plus-price-line backdrop with an accent glow (no photo asset) | Same layout shell (logo, tagline, headline, CTA, footer), photo backdrop swapped for a generated one since there's no cover image for this project | "Copy the style, not the assets." |

**LLM model catalog** (`frontend/src/features/controls/models.ts`): 4 models offered identically on both Featherless and Fireworks — **Kimi K2 Instruct** (default, strongest agentic/tool-calling fit), **DeepSeek-V3**, **Qwen2.5 72B Instruct**, **Llama 3.3 70B Instruct**. Cross-checked against real slugs already working in two of the user's other projects (Auditflow's `src/services/featherless.js`, Aero_claw's `app/server.cjs`) plus a live catalog fetch from both providers. Exact slugs drift — the Controls tab's **Test API** button is the actual verification step before trusting one live, same as `Test Alpaca Connection` for brokerage credentials.

**Config persistence** (`backend/app/config_store.py`): the Controls tab's "Save Changes" writes to `backend/.runtime_config.json` (gitignored), **not** `.env` — `.env` stays the source of truth for Alpaca credentials and initial defaults for a headless Day-1 deploy that never touches the UI. API keys are encrypted at rest with **Windows DPAPI** (bound to this Windows user account, same approach as a sibling project's `config_manager.py`), with a plaintext fallback + warning off Windows so the app doesn't crash in that case. Verified end-to-end: a saved key round-trips correctly through the API and is genuinely encrypted on disk (confirmed by inspecting the raw JSON file).

**Agent Engine lifecycle** (`backend/app/agent_loop_manager.py`): Start/Stop/Restart launch `scripts/run_agent_loop.py` as a real subprocess (`subprocess.Popen`, not a thread), tracked by PID; Stop sends SIGTERM with a 5s grace period before SIGKILL. Verified live: started a real subprocess, confirmed PID tracking, watched it correctly fail-and-continue through repeated cycles against fake credentials (proves the try/except-and-keep-looping design in `run_agent_loop.py` actually holds up), and cleanly stopped it. Logging is configured *before* the ~10s cold import of LangGraph/alpaca-py/LLM SDKs so the Logs tab shows activity immediately instead of looking dead during that window.

---

## 7. Repo structure

```
DeltaMind_ai/
├── PLAN.md                  ← you are here
├── README.md
├── .env.example
├── backend/                 Python 3.11+, managed with uv
│   ├── pyproject.toml
│   ├── .runtime_config.json     (gitignored — Controls tab's saved config, DPAPI-encrypted keys)
│   ├── logs/agent_loop.log      (gitignored — tailed by the Logs tab)
│   ├── app/
│   │   ├── main.py          FastAPI app + router wiring
│   │   ├── config.py        pydantic-settings (.env — defaults/fallback)
│   │   ├── config_store.py  Controls-tab runtime config, DPAPI-encrypted at rest (section 6)
│   │   ├── agent_loop_manager.py  subprocess lifecycle for the live loop (section 6)
│   │   ├── api/             REST routes: account/positions/trades/backtest/config/engine/logs + /ws/live
│   │   ├── agents/          LangGraph nodes + graph.py wiring (section 3)
│   │   ├── llm/             provider-agnostic LLM client (section 4)
│   │   ├── alpaca/          mcp_client.py, rest_client.py, cli_wrapper.py
│   │   ├── quant/           black_scholes.py, greeks.py, iv_percentile.py, risk_metrics.py — pure math, unit-tested
│   │   ├── strategies/      one module per track (section 5)
│   │   ├── db/              SQLAlchemy models + repository.py (data-access layer)
│   │   └── backtest/        data_loader.py, engine.py (stub — see TODOs), runner.py
│   ├── scripts/
│   │   └── run_agent_loop.py   ← live-loop entrypoint, launched by agent_loop_manager.py
│   └── tests/
│       └── test_black_scholes.py
└── frontend/                 React + TypeScript + Vite + Tailwind v4
    └── src/
        ├── api/               client.ts (typed REST client), types.ts
        ├── styles/theme.css   ← THE editable design-tokens file (section 6)
        ├── components/primitives.tsx   Section, Card, Button, TextField, Select, StatTile, StatusDot, DecisionRow, PositionRow
        ├── features/
        │   ├── landing/LandingPage.tsx
        │   ├── controls/      ControlsPage.tsx, models.ts (LLM provider/model catalog)
        │   ├── strategies/StrategiesPage.tsx
        │   ├── backtest/BacktestPage.tsx
        │   └── logs/LogsPage.tsx
        └── App.tsx            landing/app shell, 4-tab nav, theme toggle
```

---

## 8. Setup

### Backend
```bash
cd backend
uv venv
uv pip install -e ".[dev]"
cp ../.env.example ../.env   # fill in keys — see below
uv run uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

### Alpaca MCP Server v2 (required for live execution + news)
```bash
git clone https://github.com/alpacahq/alpaca-mcp-server ../alpaca-mcp-server
cd ../alpaca-mcp-server
uv sync
```
Point `ALPACA_MCP_SERVER_PATH` in `.env` at that checkout. `backend/app/alpaca/mcp_client.py` spawns it as a subprocess over stdio.

### LLM credentials
Either fill in `FEATHERLESS_API_KEY` / `FIREWORKS_API_KEY` in `.env` (used for a headless start), **or** open the dashboard's Controls tab, pick a provider/model from the dropdown, paste the key, hit **Test API**, then **Save Changes** — this writes to `backend/.runtime_config.json` (DPAPI-encrypted) and takes effect on the agent's next cycle without a restart.

### Day 1 checklist (do NOT do this early — see rules in section 1)
1. Register a **brand-new** Alpaca paper trading account.
2. Update `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` in the production `.env` to that account.
3. Record the account ID — required in the final submission form.
4. Set Symbols/Track/Interval on the Controls tab (or via `.env`/CLI) and hit **Start** — or run `scripts/run_agent_loop.py` directly for a fully headless deploy.

---

## 9. Risk guardrails (enforced in `risk_gate.py`, configurable in `config.py`)

- Max single position: **10%** of portfolio equity
- Max margin utilization: **50%**
- Every proposed order must carry a stop-loss ≤ **20%** (track modules set their own, tighter, defaults)
- Order structure validated (symbol + legs present) before anything reaches Alpaca

---

## 10. Submission checklist (fill in as completed)

- [ ] Project title + short description (≤255 chars) + long description (≥100 words)
- [ ] Public GitHub repo, MIT-licensed, cleaned up
- [ ] Hosted dashboard URL (frontend deploy target TBD — Vercel is the likely default for a Vite app; backend needs a host too, e.g. Railway/Render/Fly — **decide closer to Day 6**)
- [ ] Fresh Alpaca paper account ID
- [ ] 5-minute video (MP4 or YouTube link)
- [ ] Slide deck (PDF)
- [ ] Up to 5 social posts (X/LinkedIn, tagging @lablabai and @AlpacaHQ)

---

## 11. Open questions / TODOs

- **LLM model slugs** — the Controls tab dropdown lists 4 candidates per provider (section 6); always confirm with **Test API** before a live run, since exact catalog slugs drift.
- **`backend/app/backtest/engine.py`** is a stub — needs wiring to `data_loader.py` + the strategy modules once real historical option-chain-with-Greeks access is confirmed against the user's Alpaca data plan/entitlements. The Backtest tab already calls it and displays results; it just returns zeros today.
- **`get_iv_52wk_range()`** in `db/repository.py` returns a placeholder range — needs a real historical-IV table populated from backtest data before `iv_percentile.py` output is trustworthy.
- **Hosting** for the demo (frontend + backend) — not yet chosen; decide in the final 48 hours per the submission checklist.
- **MCP tool schemas** (`place_option_order`, `get_news`, etc.) in `mcp_client.py` are written from the hackathon brief's description — **verify field names against the actual `alpacahq/alpaca-mcp-server` tool definitions** (now cloned at `../alpaca-mcp-server`) since exact argument shapes weren't independently confirmed against the real source.
- **No real Alpaca or LLM credentials configured anywhere yet** — every endpoint that touches them has been verified to fail *gracefully* (clear error messages, no crashes, the agent loop keeps retrying), but nothing has actually placed a trade or gotten a real LLM response. That's the next real milestone once credentials are in hand.
- No additional Claude Code skills needed beyond what's already installed (`dataviz` flagged inline in `BacktestPage.tsx`/`ControlsPage.tsx` comments for whenever a real equity-curve chart gets built).

---

## 12. Status log

- **2026-08-19 (session 1)** — Repo scaffolded from scratch: backend (FastAPI + LangGraph agent pipeline + quant math + SQLite persistence), frontend (React/TS/Vite dashboard skeleton), full architecture and tech-stack decisions recorded above.
  - `git init` done at repo root (not yet committed — nothing has been committed anywhere in this project).
  - Cloned `alpacahq/alpaca-mcp-server` to `../alpaca-mcp-server` (sibling of this repo), matching the default `ALPACA_MCP_SERVER_PATH`.
  - Verified end-to-end: fixed a hatchling build-config gap (`pyproject.toml` needed `[tool.hatch.build.targets.wheel] packages = ["app"]` since the package dir is named `app`, not `deltamind_backend`), then `uv venv` (auto-fetched Python 3.11.5), `uv pip install -e ".[dev]"`, `pytest` (3/3 pass on the Black-Scholes/Greeks module), `app.main` imports cleanly with all routes registered, the LangGraph pipeline compiles with the exact intended edge structure, and `uvicorn` boots and serves `/api/health` successfully (confirms SQLite `init_db()` startup hook works — `deltamind.db` created).
  - Frontend: `npm install` (68 packages) and `tsc -b` both clean, no type errors.

- **2026-08-19 (session 2)** — Confirmed **Track 1** as the primary submission track (section 5). Rebuilt the frontend as a full dashboard styled after a sibling project's design system (section 6): Tailwind v4 + `theme.css` design tokens (charcoal black / premium white, International Orange `#FF4F00` accent), ported component primitives, and a 4-tab app shell (Controls / Strategies / Backtest / Logs) behind a landing page.
  - Added the LLM model catalog (`models.ts`): Kimi K2 Instruct, DeepSeek-V3, Qwen2.5 72B, Llama 3.3 70B — available on both Featherless and Fireworks, cross-checked against real slugs from the user's Auditflow/Aero_claw projects plus a live catalog fetch.
  - Added backend support for the new Controls tab: `config_store.py` (DPAPI-encrypted runtime config, separate from `.env`), `agent_loop_manager.py` (subprocess lifecycle for the live loop), and `routes_config.py` / `routes_engine.py` / `routes_logs.py`. `llm/providers.py` and `alpaca/rest_client.py` gained `test_provider()` / `test_connection()` helpers backing the Test API / Test Alpaca Connection buttons. `run_agent_loop.py` now logs to `logs/agent_loop.log` in the format the Logs tab parses, with logging configured *before* the ~10s cold import of LangGraph/alpaca-py/LLM SDKs so the tab doesn't look dead during startup.
  - Verified thoroughly, not just compiled: `tsc -b` clean, all new API routes registered (checked via the OpenAPI schema), config save/load round-trips correctly with the API key genuinely DPAPI-encrypted on disk (inspected the raw file), a real agent-loop subprocess was started/tracked-by-PID/stopped, and — with fake credentials — correctly logged graceful per-cycle errors and kept retrying at the configured interval rather than crashing. Screenshotted all 4 tabs plus the landing page in a headless Chrome instance (driven via raw Chrome DevTools Protocol over the already-installed `websockets` package, since neither `chromium-cli` nor Playwright were available in this environment) — zero browser console errors, layout matches the reference screenshots' structure while using DeltaMind's own colors/copy/fields.
  - **Not yet done:** no real Alpaca or LLM credentials configured anywhere (see section 11); `npm audit` flagged 2 vulnerabilities (1 moderate, 1 high) in dev-only deps, not yet reviewed; nothing committed to git yet.
