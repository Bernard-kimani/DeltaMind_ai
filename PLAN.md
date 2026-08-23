# DeltaMind AI — Plan & Context

**This is the living source of truth for the project.** Update it as decisions change — don't let it drift from reality. Everything else (code, memory) can be re-derived; this file carries the *why*.

Last updated: 2026-08-24 (session 4)

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

**Decided: Track 1 (Options Alpha) is primary, Track 4 (Income/Wheel) is the committed secondary**, to be perfected in that order — both fully tested (not just demoed) before the hackathon, with a third (Track 2) only if time remains and the earnings/macro calendar for Aug 28–Sep 4 actually cooperates. Reasoning for the pairing, not just deferring to a suggestion:

- **Regime-complementary, not redundant.** Track 1 needs a trend (breakout + sentiment agreeing) — in a quiet week it could go days without a qualifying setup, which hurts the "trade frequency/consistency" judging criteria on its own. Track 4 needs no trend at all, just an underlying worth selling premium on, which exists every day. Running both means real trade history accumulates regardless of which regime the week turns out to be.
- **Track 2 is calendar-dependent in a way the other three aren't** — its whole thesis is "IV expansion/crush around a scheduled event," so it only fires if something real (earnings, a macro print) actually lands during Aug 28–Sep 4. Worth checking that calendar before promoting it above Track 4, not assuming it'll have opportunities to trade.
- **Track 3 is the weakest fit for a one-week demo**, not deprioritized arbitrarily: its trigger is portfolio drawdown on an *existing* equity position — without one already established and losing >3.5%, it may simply never fire, which is worse for judging than any of the other three even trading occasionally.

**All four modules share the same `propose_order(state, thesis) -> order` interface**, so switching — or running multiple tracks on different symbols simultaneously — is a config change (the Controls tab's Track dropdown, or `run_agent_loop.py --track`), not a rewrite. Per-track explainer docs (mechanics, options math, the LLM-vs-deterministic-code split, known gaps) live in `docs/tracks/` — see [00_options_basics.md](docs/tracks/00_options_basics.md), [track1_alpha_spreads.md](docs/tracks/track1_alpha_spreads.md), [track4_income_wheel.md](docs/tracks/track4_income_wheel.md) — written for both the user's own understanding and reuse in the judge-facing submission writeup. A Track 2 doc is deferred until it's actually committed as the third track.

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
├── docs/tracks/             ← per-track explainer docs (section 5): options basics, mechanics, LLM-vs-code split, gaps
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
│   │   ├── agents/          LangGraph nodes + graph.py wiring (section 3); position_monitor.py — plain-function exit/assignment sweep (session 4)
│   │   ├── llm/             provider-agnostic LLM client (section 4)
│   │   ├── alpaca/          mcp_client.py, rest_client.py (get_option_chain joins two Alpaca APIs — session 4), cli_wrapper.py
│   │   ├── quant/           black_scholes.py, greeks.py, iv_percentile.py, risk_metrics.py, technical_signals.py — pure math, unit-tested
│   │   ├── strategies/      one module per track (section 5); _common.py's closest_by_delta/net_debit_credit shared by all
│   │   ├── watchlist.py     curated 15-symbol universe + sector map + liquidity filter (session 4)
│   │   ├── db/              SQLAlchemy models + repository.py (data-access layer)
│   │   └── backtest/        data_loader.py, engine.py (stub — see TODOs), runner.py
│   ├── scripts/
│   │   └── run_agent_loop.py   ← live-loop entrypoint, launched by agent_loop_manager.py
│   └── tests/
│       ├── test_black_scholes.py
│       └── test_strategies_common.py   DTE/sign-fix logic, net_debit_credit (session 4)
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

Track 1 and Track 4's documented gaps from session 3 are now closed (bear put spread, exit-management monitor, IV screening, DTE targeting, assignment detection — see section 12's session 4 entry for what changed and how each was verified). Remaining:

- **No real order has been submitted end-to-end yet.** Every live test so far correctly rejected on "no breakout confirmed" / "sentiment insufficient" — the entry AND-gate is strict by design, and no live SPY setup has cleared it during testing. `place_option_order`'s MCP argument shape, `execution.py`'s leg-translation, and `position_monitor.py`'s closing-order path are all built and unit/integration-tested against real chain data, but **none have been exercised by an actual accepted order yet** — confirm on the first real fill.
- **`backend/app/backtest/engine.py`** is still a stub — needs wiring to `data_loader.py` + the strategy modules once real historical option-chain-with-Greeks access is confirmed against the user's Alpaca data plan/entitlements.
- **`get_iv_52wk_range()`** in `db/repository.py` returns a placeholder range — needs a real historical-IV table populated from backtest data before `iv_percentile.py` output is trustworthy.
- **Track 2's IV-percentile trigger has no earnings/macro-calendar check** (found during session 3's track review, same shape as Track 1's original breakout gap) — out of scope while Track 2 stays uncommitted, but relevant if it gets promoted to a third track around the Sep 4 jobs report (see section 5).
- **Hosting** for the demo (frontend + backend) — not yet chosen; decide in the final 48 hours per the submission checklist.
- **LLM model slugs** — the Controls tab dropdown lists 4 candidates per provider (section 6); **Kimi K2 Instruct is now confirmed live** on Featherless (`moonshotai/Kimi-K2-Instruct`) — the other 3 (DeepSeek-V3, Qwen2.5 72B, Llama 3.3 70B) and the Fireworks-side slugs are still unverified. Confirm with **Test API** before switching to one.
- **`open_interest` availability on live paper data turned out better than initially feared** — real, non-null values were returned in testing (see session 4), but this was flagged as potentially unreliable per Alpaca's own docs; don't assume it's always populated for every contract/symbol.
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

- **2026-08-23 (session 3)** — Real credentials in hand: Alpaca paper account (key `PKNTVFWK2643TPPQXA375G2EA2`, dev/test account — **still needs a brand-new one on Day 1** per section 1) and a Featherless API key. Written to `backend/.env` (confirmed gitignored via `git check-ignore`, not staged).
  - Registered Alpaca's Trading MCP Server v2 for Claude Code itself: `claude mcp add alpaca` at **local scope** (deliberately not the doc's suggested `--scope user` global scope, and not `project` scope either — local keeps the API keys out of any file git could ever pick up, stored in the user's own `~/.claude.json` instead). Launched via `uvx alpaca-mcp-server` (the officially documented PyPI-package approach) — confirmed connected via `claude mcp list` after warming the `uvx` package cache (first run downloads ~74 packages, which made the first couple of health-checks time out before the cache was warm). Its tools aren't callable by *me* mid-conversation since it was added after this session started — available to Claude Code from the next fresh session on this project.
  - Rewrote `mcp_client.py`'s launch mechanism to match: `uvx alpaca-mcp-server` instead of a local git-clone path (`ALPACA_MCP_SERVER_PATH` config removed as dead weight). Confirmed the real multi-leg option order shape against alpaca-py's own `OptionLegRequest`/`OrderRequest` models (found in the installed SDK, since the MCP server is generated from these) rather than guessing from the hackathon brief.
  - **Verified real credentials end-to-end, not just "saved":** `/api/config/test-alpaca` connected to the real paper account (`PA31AXNLB6OS`, $100,000 equity); `/api/config/test-llm` got a real reply from Featherless/Kimi K2 (took ~60-90s — Featherless's serverless cold-start for spinning up a model, not a bug). Then ran one full live agent cycle (SPY, Track 1) against both real credentials together — **caught and fixed a real bug in the process**: `mcp_client._call_tool()` assumed the MCP SDK's `CallToolResult` was dict-like; it's actually `.content` (a list of content blocks) plus `.structured_content`/`.is_error` (both confirmed snake_case by reading the installed SDK's actual source after the live call crashed on it). Fixed to prefer `structured_content`, falling back to parsing the first text block as JSON. Re-ran after the fix: the full pipeline completed clean — real Alpaca market data → real MCP `get_news` call → two real Featherless/Kimi K2 LLM calls (sentiment + thesis) → risk gate correctly rejected (no order proposed) → decision persisted to SQLite, all confirmed via `/api/trades/decisions` and `/api/engine/stats`.
  - **Found (not yet fixed):** the LLM's thesis text reasoned about IV percentile/vega/a long straddle while running under Track 1 — that's Track 2's structure. See section 11 — needs a prompt fix before trusting live thesis output to stay on-track.

  - **Fixed the track-drift bug**, and two more found in the process of writing it up properly:
    - `lead_architect.py`'s prompt now names the active track explicitly (`TRACK_ENTRY_RULES`) and instructs the model to say "no trade this cycle" rather than describe a different track's structure when the numbers don't fit its own. **Confirmed live, before/after**: same market conditions, old thesis was *"...initiate a 30-day long straddle to capture vega gains..."* (Track 2's structure, wrong), new thesis is *"No breakout confirmed; sentiment score of 0.0 lacks directional conviction beyond ±0.75 threshold — no trade this cycle."* (correct).
    - **Track 1's entry condition was only half-implemented**: the docstring and hackathon brief both describe "technical breakout AND sentiment," but no breakout signal existed anywhere in the pipeline — `propose_order()` only ever checked sentiment. Added `app/quant/technical_signals.py` (deterministic SMA-breakout + volume-confirmation, matching the "quant is LLM-free" design principle) and wired it through `quant_engine.py` → `state["technical_signal"]` → Track 1's entry check, now a real AND-gate.
    - **Track 1's stop-loss would have rejected every order**: strategy set `STOP_LOSS_PCT = 0.30`, but `risk_gate.py` rejects anything above the global ceiling (`settings.stop_loss_pct`, default 0.20) — a live blocker, found while writing the track doc's exit-management section, not from a test run. Fixed by tightening the strategy to 0.20 rather than loosening the platform-wide ceiling.
    - **Track 3 had the same `market_data` shape bug already fixed in `mcp_client.py`**: `state.get("market_data", {}).get("close")` assumed a dict; `market_data` is actually a list of bar records (fixed the `AgentState` type hint too, it was wrong). Never triggered live since Track 3 hasn't run yet, but would have crashed identically to the MCP bug the moment it did.
    - All re-verified: fresh Python import check across every edited module, then one more full live cycle end-to-end (real Alpaca + real Featherless/Kimi K2) confirming the corrected thesis and no crashes.
  - Wrote `docs/tracks/00_options_basics.md`, `track1_alpha_spreads.md`, `track4_income_wheel.md` — options mechanics grounded correctly (intrinsic vs. extrinsic value, Delta ≠ 1:1 immediate price sensitivity — the pasted external explainer's math was a valid *at-expiration* example but read as instantaneous, which isn't right pre-expiration), the actual entry/exit rules matching the real code exactly, the LLM-explains/code-decides architecture split, and an honest tone (advised against "revolutionary"/"bound to be profitable" framing — no options structure is bound to be profitable; the real, defensible claim is the bounded risk + deterministic risk gate, which is demonstrable in code).

- **2026-08-24 (session 4)** — Planned (via a formal Explore → Plan → user-approved plan cycle) and implemented multi-symbol scanning plus closing Track 1/4's remaining gaps. Track 4 (Income/Wheel) confirmed as the committed secondary track; Track 2 stays a conditional third, scoped to the Sep 4 jobs-report week if pursued (section 5).
  - **Research before writing any code found something more fundamental than the documented gaps: nothing in the pipeline could place a real order at all, regardless of track.** `_common.py`'s `closest_by_delta()` filtered on `c.get("type")`, but the old `get_option_chain()` returned raw `OptionsSnapshot`s which have no `type`/`strike_price`/`expiration_date`/flat `bid`/`ask` fields at all — the filter could never match, so it always returned `None`. Neither of session 3's live tests caught this because sentiment never cleared the entry threshold either time — the code never reached the broken path. `execution.py` had a second unreachable bug directly downstream: it called `place_option_order(order)` with one dict, but the real function takes separate `symbol`/`legs`/... args with `legs` required.
  - **Rebuilt `rest_client.py`'s `get_option_chain()`** to join two separate Alpaca APIs by OCC symbol: `TradingClient.get_option_contracts()` (type/strike/expiration/open_interest — a different endpoint than before) with the existing market-data snapshot (bid/ask/greeks/IV). **Verified against real live data, not just unit tests**: 5,652 real SPY contracts returned with correct fields; found and fixed a second latent bug this exposed (`c.get("greeks", {})` doesn't help when the real value is explicitly `None`, not absent — Alpaca's paper feed returns `None` greeks for a real fraction of contracts, especially 0 DTE ones).
  - **Extended `closest_by_delta()`** with DTE-awareness and confirmed a live correctness bug building a real Track 1 order for the first time ever: without `target_dte`, the two legs of a "vertical" spread could land on *different expirations* (got a real result buying an October call against selling a same-day August call) — not a valid spread at all. Fixed by passing `target_dte` through both legs' selection, with a same-expiration assertion as a second layer of defense. Also fixed Track 1's put-delta sign bug (unsigned deltas rank backwards against puts' negative range) while adding the bear put spread branch — confirmed live: both a bullish call spread and bearish put spread now build correctly with matched expirations and sensible strikes.
  - **Added `position_monitor.py`** (a plain function per the user's explicit choice over a LangGraph node — it's an account-wide sweep, not a per-symbol decision, and needs no LLM): closes Track 1 spreads at 50% profit-take / 20% stop-loss against the real net debit paid (added `PROFIT_TAKE_PCT` — referenced in prose since session 1 but never actually defined in code until now), and syncs Track 4's `holds_underlying_shares` from Alpaca's real position list each sweep (previously hardcoded unreachable-`False`). Wired into `run_agent_loop.py`, running once per full pass before new entries are proposed. `Trade` gained `status`/`closed_at`/`realized_pnl` columns; `WheelState` is a new tiny table.
  - **Closed Track 4's gaps**: an IV-percentile floor (50, a concrete reading of the brief's "elevated IV"), DTE targeting (21-day point estimate for the 14-30 range), and the `holds_underlying_shares` fix above.
  - **Found and fixed a capital-sizing bug** while wiring risk_gate.py to use net debit/credit instead of gross notional: a cash-secured put's true capital commitment is the strike price x 100 (cash secured against assignment), not the small premium collected — using premium alone would let the position-size cap pass almost any CSP regardless of strike. Added a `capital_at_risk` field each strategy sets explicitly (debit spread's net debit; CSP's strike x 100; covered call's $0, since the shares are already owned) rather than one formula trying to fit every trade shape.
  - **Added the three new risk-gate guardrails** (Balanced posture, chosen with the user over Conservative/Aggressive): max 3% of equity per trade (down from 10%), max 6 concurrent positions, 55% cash-reserve floor, 15% sector cap. All four rejection paths (position size, concurrent count, cash reserve, sector) directly unit-tested against `risk_gate.run()` with fabricated states — each fires with the correct, specific rejection message.
  - **Added `app/watchlist.py`** — the user's own researched 15-symbol curated universe (index ETFs, mega-cap tech, high-beta momentum, sector ETFs), doubling as the sector map for the concentration cap, plus a liquidity pre-filter (20-day avg daily volume > 1M, ATM bid-ask spread < 5%) using a new `get_daily_bars()` (the existing `get_recent_bars()` is minute-bars only). A "Load Curated Watchlist" button in the Controls tab populates the Symbols field from it via a new `/api/config/watchlist` endpoint. Deliberately NOT a full-market scan — the loop sleeps once per full pass over all symbols, not per symbol, so a much larger list would silently stretch the effective per-symbol interval.
  - **A real operational lesson mid-session**: a "no such column: trades.status" error on the first post-schema-change test turned out to be a stale `deltamind.db` whose deletion had silently failed (`-ErrorAction SilentlyContinue` masked a file-lock from an old backend process still holding it open) — `create_all()` only creates missing tables, never alters existing ones. Fixed by finding and killing the actual lock-holding process (a stray system-Python uvicorn instance from an earlier restart, not the venv one) before deleting, then verifying the fresh schema directly via `sqlite3` before re-testing.
  - **Re-verified the entire pipeline end-to-end after all changes**: full pytest suite (11/11, including new tests in `tests/test_strategies_common.py` for the DTE/sign-fix logic and `net_debit_credit`), clean `tsc -b`, and one more full live cycle (real Alpaca + real Featherless) — position monitor sweep ran with zero errors against the fresh schema, two real LLM calls succeeded, and the persisted decision showed a correct, track-consistent thesis.
