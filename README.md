# DeltaMind AI

**An autonomous options-trading agent built on Alpaca's Trading API, MCP Server, and CLI — submitted to the Alpaca AI Trading Agents Hackathon (lablab.ai × Alpaca, 28 Aug–4 Sep 2026).**

DeltaMind AI watches a curated basket of liquid, options-active symbols in real time, screens every one of them through a deterministic technical gate before it ever costs a single API call to an LLM, and only asks its AI validator to make the final call once a setup has already cleared hard, auditable thresholds. Every trade it *would* place is a real options order — single-leg calls or puts sized against real portfolio risk — routed through Alpaca's own MCP Server so the tool-call trail is inspectable end to end.

- **Live app:** _add your Netlify URL here_
- **Alpaca paper account (submitted):** `PA3MQ0ON72CL`
- **Backend:** FastAPI + LangGraph, deployed on Render
- **Frontend:** React + TypeScript, deployed on Netlify

---

## One-page write-up

*(AI logic, risk gates, and Alpaca infrastructure — per the hackathon's submission requirement. This section is written to stand alone as that page.)*

### AI logic

The agent runs one decision cycle per symbol, per bar-close, through a LangGraph state machine:

```
news_blackout_gate --(blocked)--> END (zero REST/LLM calls spent)
                   --(clear)--> market_ingestion -> quant_engine
                                                        |
                                          qualified? --no--> END (zero LLM calls)
                                                     --yes-> LLM validator -> risk_gate
                                                                                |
                                                              risk_approved? --yes--> execution -> END
                                                                             --no---> END (logged, no trade)
```

The core design principle is **gate cheaply before spending anything**: a deterministic, hand-written technical screener (`quant_engine.py`) has to qualify a setup — real momentum confluence, not a vibe — *before* a single LLM token is spent evaluating it. Only qualifying setups reach the AI layer, which exists to catch what pure technicals can't: does the news/sentiment context actually support this trade right now?

**Entry logic:** a 1-hour EMA(50) trend filter combined with a 5-minute EMA(20) crossover in the same direction — deliberately a thin, two-factor gate rather than a heavier multi-indicator stack, so the LLM validator carries real decision weight instead of rubber-stamping an already-overdetermined signal.

**LLM validation:** every qualifying setup is checked by an LLM (Featherless AI, see below) acting as lead strategist. It's a *contradiction* check, not a confirmation requirement — a setup isn't blocked by an absence of supporting news, only by sentiment that actively contradicts the technical direction (gated at ±0.35) or by confidence below 55%. This mirrors how a real discretionary trader treats "no news" — as a green light, not a red flag.

**Exits (once a position is open):** a tiered take-profit (+50% closes half the position and moves the stop to breakeven; +100% or a 1-hour trend reversal closes the rest), a 20% stop-loss, a time-stop if the setup goes nowhere for hours, and unconditional end-of-day liquidation — no options position is ever held overnight.

### Risk gates

`risk_gate.py` is a **deterministic circuit breaker with zero LLM calls in it** — every threshold below is a hard-coded number a judge can read top-to-bottom and verify, not a model's judgment call:

| Guardrail | Limit |
|---|---|
| Position size (premium at risk) | ≤ 3% of account equity per trade |
| Sector concentration | ≤ 15% of equity in any one sector, aggregated across open positions |
| Margin utilization | ≤ 50% |
| Open positions | ≤ 6 concurrent |
| Minimum cash reserve | ≥ 55% of equity after any new trade |
| Stop-loss | Every order must carry one, capped at 20% |
| News blackout | No new entries inside a red-folder macro release's blackout window (checked twice — once before the LLM call, once again as a backstop right before execution, in case a slow cycle drifts across the boundary) |

A rejected trade is never silent — every rejection is logged with its specific reason (`risk_rejection_reason`), visible in the dashboard's Decision History, so "why didn't it trade" is always answerable from the data, not a guess.

### Alpaca infrastructure

- **Trading API** — the brokerage interface itself: account state, positions, and the option chain data every entry/exit decision is priced against.
- **MCP Server v2** (`alpaca-mcp-server`, launched via `uvx`) — every live order execution and news fetch goes through Alpaca's official MCP server rather than raw REST, so each trade carries an auditable, structured tool-call trail. Market-data polling (bars, option chains) stays on direct REST — routing routine per-second data pulls through an LLM/MCP round-trip would be pure overhead with no benefit to auditability.
- **Alpaca CLI** — a thin wrapper (`cli_wrapper.py`) for low-overhead scheduled tasks (account/position reconciliation) where spinning up the MCP stdio server would be unnecessary weight.
- **Paper trading, $100k, fresh account** — account `PA3MQ0ON72CL`, created specifically for this submission.

---

## Architecture

```
frontend/   React + TypeScript dashboard (Netlify)
  ├─ Controls     start/stop the live engine, configure symbols/model
  ├─ Performance  P&L, closed trades, full decision history (incl. rejections)
  ├─ Strategy     the gate/exit parameters this agent actually runs
  ├─ Backtest     historical qualification-rate testing against real bars
  └─ Logs         live-tailed engine log, filterable by level

backend/    FastAPI + LangGraph (Render)
  ├─ app/agents/          the state graph: gates, validator, risk_gate, execution
  ├─ app/strategies/      the strategy module — entry rules, position sizing, exits
  ├─ app/quant/           technical signal computation (EMA, RSI, RVOL, IV percentile)
  ├─ app/alpaca/          MCP client (execution/news), REST client (market data), CLI wrapper
  ├─ app/backtest/        historical qualification-rate engine
  └─ scripts/             the live, always-on process — a real Alpaca WebSocket
                           bar stream triggers one decision cycle per bar-close
```

The live engine runs as its own supervised OS subprocess (not a background thread), with a watchdog that auto-restarts it on an unexpected crash and auto-resumes it — with the same symbols and settings — if the whole backend process itself restarts, so a Render redeploy or restart doesn't silently end trading until someone notices.

## Tech stack

| Layer | Technology |
|---|---|
| Trading & data | Alpaca Trading API, MCP Server v2, CLI, Market Data API |
| Agent reasoning | Featherless AI (serverless open-model inference — Kimi K2 Instruct by default) |
| Orchestration | LangGraph |
| Backend | FastAPI, Python 3.11+, SQLite |
| Frontend | React, TypeScript, Vite, Tailwind CSS, TanStack Query |
| Hosting | Render (backend, free tier), Netlify (frontend) |

## Running locally

**Backend**
```bash
cd backend
uv venv && uv pip install -e .          # or: pip install -e .
cp .env.example .env                     # fill in Alpaca + Featherless keys (see below)
uvicorn app.main:app --reload --port 8000
```

Required `.env` values:
```
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
ALPACA_PAPER=true
ALPACA_TRADE_API_URL=https://paper-api.alpaca.markets
ALPACA_DATA_API_URL=https://data.alpaca.markets
LLM_PROVIDER=featherless
LLM_MODEL=moonshotai/Kimi-K2-Instruct
FEATHERLESS_API_KEY=...
```

**Frontend**
```bash
cd frontend
npm install
npm run dev
```

Open the app, go to **Controls**, paste in a Featherless API key (or set `FEATHERLESS_API_KEY` in the backend's `.env`), load the curated watchlist, and hit **Start**. The engine begins streaming real Alpaca bar data immediately in the paper environment.

## Deployment

- **Backend → Render.** A single free-tier web service running `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, with Alpaca and Featherless credentials set as environment variables (never committed). The live trading loop is a supervised subprocess of this same service — starting/stopping it is a Controls-tab action, not a separate deploy.
- **Frontend → Netlify.** Static build (`npm run build`) pointed at the Render backend's URL via `VITE_API_BASE_URL`. Netlify auto-deploys on every push to `main`.
- **Uptime.** Render's free tier spins a service down after inactivity; an external uptime monitor keeps the backend's health endpoint warm so the live trading loop stays continuously alive through the full competition week, independent of anyone having a browser tab open.

## Repo structure

```
backend/    FastAPI + LangGraph agent, quant engine, Alpaca MCP/REST/CLI integration, tests
frontend/   React + TypeScript dashboard
PLAN.md     Full build history, architecture decisions, and running status log
```

See [PLAN.md](PLAN.md) for the complete build history and every architectural decision behind this project.
