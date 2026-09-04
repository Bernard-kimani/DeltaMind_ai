# DeltaMind AI — Slide Deck Content (8–10 slides)

Copy each slide's content directly into Google Slides. Suggested visual is noted under each — screenshot the live dashboard where indicated.

## Brand & style guide (match the app exactly)

All three fonts below are real Google Fonts — searchable directly in Google Slides' font picker, no upload needed.

**Colors** (the app's dark theme — matches every screenshot you'll be pulling in):

| Role | Hex | Use |
|---|---|---|
| Background | `#121212` | Slide background |
| Surface / card | `#1A1A1A` | Boxes, tables, code blocks |
| Accent (brand color) | `#FF4F00` | Titles, highlights, the "Mind" in the wordmark, key numbers — International Orange, the *one* accent color, used sparingly and deliberately |
| Text — primary | `#F2EDE6` | Body copy on dark background |
| Text — secondary | `#B3AEA6` | Captions, muted labels |
| Success (if showing a fill/profit) | `#59B37D` | — |
| Error (if showing a rejection) | `#E2584A` | — |

**Fonts:**

| Role | Font | Where |
|---|---|---|
| Logo / wordmark only | **Wallpoet** | Just the word "DeltaMind AI" on the title/closing slides — this is the exact font the app's header logo uses. Don't use it for body text, it's a display-only mark. |
| Headings / display moments | **Fraunces** | Slide titles |
| Body text / labels / data | **IBM Plex Sans** | Everything else — bullets, table text |
| Code / numbers / tables | **IBM Plex Mono** | Code snippets, the risk-gate table, any monospaced figures |

**Logo treatment:** render "Delta" in `#F2EDE6` (or black on a light slide) and "Mind AI" in `#FF4F00`, both in Wallpoet, no space fussing — matches the app header exactly (`Delta` in text color, `Mind` + `AI` in accent orange).

---

## Slide 1 — Title

**DeltaMind AI**
Autonomous options-trading agent, built on Alpaca

- Alpaca AI Trading Agents Hackathon — lablab.ai × Alpaca
- Team: [your name/team]
- Paper account: `PA3MQ0ON72CL`

*Visual: your landing page screenshot (the skyline photo hero).*

---

## Slide 2 — The Problem / Approach

**Most trading bots either trade too much, or can't explain why they didn't.**

- Two failure modes we designed against:
  1. Forcing a trade into a bad setup just to have activity
  2. A black-box model deciding everything, with no auditable reasoning
- Our answer: a **deterministic gate first, AI judgment second** — the model only ever gets a say once a setup has already cleared hard, numeric thresholds
- Every decision — trade *or rejection* — is logged with its exact reason

*Visual: none needed, or a simple two-box "before/after" diagram.*

---

## Slide 3 — Architecture

**One decision cycle, top to bottom:**

```
news_blackout_gate → market_ingestion → quant_engine
                                            ↓ (qualified?)
                                    LLM validator → risk_gate → execution
```

- **quant_engine**: hand-written technical screener — zero LLM cost until a setup genuinely qualifies
- **LLM validator**: Featherless AI (Kimi K2 Instruct) — a contradiction check, not a rubber stamp
- **risk_gate**: deterministic circuit breaker, zero LLM calls, hard-coded guardrails
- **execution**: real order placement via Alpaca's MCP Server

*Visual: recreate this diagram cleanly (or screenshot `graph.py`'s docstring diagram).*

---

## Slide 4 — The Strategy Page (AI Logic)

**Entry logic — deliberately thin, so the AI carries real weight:**

- 1-hour EMA(50) trend filter + 5-minute EMA(20) crossover in the same direction
- No RSI band, no volume filter, no breakout lookback — just two factors, so the LLM's judgment on catalyst/sentiment is what actually decides, not a heavily pre-filtered rubber stamp

**LLM validation — a contradiction check, not a confirmation requirement:**

- Blocks only on sentiment that actively *contradicts* the technical direction (±0.35 threshold)
- Requires ≥55% confidence
- Absence of news is treated as a green light, the way a real discretionary trader would — not as a reason to sit out

**Exits, once a position is open:**

- +50% → close half, move stop to breakeven
- +100%, or a 1-hour trend reversal → close the rest
- 20% stop-loss on every position
- Time-stop after several hours if the setup goes nowhere
- Unconditional end-of-day liquidation — never held overnight

*Visual: screenshot the Strategy page.*

---

## Slide 5 — Risk Gates

**A deterministic circuit breaker with zero LLM calls in it — every number is hard-coded and auditable:**

| Guardrail | Limit |
|---|---|
| Position size | ≤ 3% of equity per trade |
| Sector concentration | ≤ 15% of equity |
| Margin utilization | ≤ 50% |
| Open positions | ≤ 6 concurrent |
| Cash reserve floor | ≥ 55% after any trade |
| Stop-loss | Required on every order, capped at 20% |
| News blackout | Checked twice — before the LLM call, and again right before execution |

- A rejected trade is never silent — every rejection logs its exact reason
- This is the file we'd point a judge to first: read top-to-bottom, verify the guardrails hold

*Visual: screenshot `risk_gate.py`, or the Decision History showing a real rejection with its reason.*

---

## Slide 6 — Alpaca Integration

**All three required technologies, each used for what it's actually best at:**

- **Trading API** — account state, positions, real-time option chain pricing for every entry/exit decision
- **MCP Server v2** — every live order execution and news fetch goes through Alpaca's official MCP server (`alpaca-mcp-server`), so each trade carries an auditable, structured tool-call trail
- **CLI** — a lightweight wrapper for scheduled account/position reconciliation, where spinning up the full MCP stdio server would be unnecessary overhead
- **REST (direct)** — high-frequency market data polling only; routing routine per-second bar pulls through an LLM/MCP round-trip would be pure overhead with zero auditability benefit

*Visual: a short code snippet from `mcp_client.py`'s `place_option_order`, or the MCP tool-call trail from a log.*

---

## Slide 7 — Featherless AI Integration

- **Provider:** Featherless AI (serverless inference for open-source models)
- **Model:** Kimi K2 Instruct — agentic, tool-calling capable
- **Role:** the Lead Strategist call — structured JSON output (verdict, confidence, thesis) validating each technical setup against live sentiment/news context
- Chosen for: fast, cheap, open-model inference suited to a high-frequency screening loop where most cycles never even reach this call (the deterministic gate already filtered them out)

*Visual: screenshot a real Decision History thesis — the actual model reasoning text.*

---

## Slide 8 — Live Demo Results

**What actually happened in the paper account this week:**

- [Fill in: cycles run, qualifying setups reached, trades placed/rejected, P&L]
- If zero fills: frame honestly — *"the system correctly refused to force trades into illiquid contracts even when the AI liked the setup"* — then show 1–2 real rejected-decision examples with their thesis text and exact rejection reason, demonstrating the gate/AI/risk pipeline working end-to-end
- Show the debugging rigor: e.g. "found via live data that a $2.50 strike grid was excluding valid setups by ±0.05 delta — verified, fixed, redeployed" — this is Technology Implementation depth, not a weakness

*Visual: Performance page screenshot, Decision History with a couple of real theses expanded.*

---

## Slide 9 — Engineering & Infrastructure

- **Backend:** FastAPI + LangGraph, deployed on Render — the live loop runs as a supervised subprocess with crash auto-restart and auto-resume-after-redeploy, so a platform restart never silently ends trading
- **Frontend:** React + TypeScript dashboard, deployed on Netlify, real-time engine status/logs/decision history
- **Uptime:** external monitor keeps the backend alive continuously through the competition week, independent of anyone watching
- Built iteratively against *real* live data at every step — every threshold in this deck was verified against a live Alpaca option chain, not assumed

*Visual: Render dashboard or architecture diagram from Slide 3, reused.*

---

## Slide 10 — Closing / What's Next

- Recap: deterministic-gate-first architecture, real MCP-routed execution, auditable risk gates, live on Alpaca paper trading
- What we'd build next: [1–2 honest next steps — e.g. "loosen the entry gate further using this week's live qualification-rate data" or "add a second uncorrelated strategy once this one has a longer track record"]
- Thank you — links: GitHub repo, live app, paper account ID

*Visual: your landing page again, or a simple thank-you slide with links.*

---

### Notes for building in Google Slides

- Keep code/table slides (4–6) dense — that's fine, judges reading these want the real numbers, not a sales pitch
- Keep slides 1, 8, 10 lighter/visual — those are the ones a judge remembers
- Fill in every `[bracketed]` placeholder with your actual numbers before presenting
