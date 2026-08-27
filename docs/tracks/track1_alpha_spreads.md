# Track 1 — Options Alpha (Single-Leg 1-2 DTE, Confluence-Gated)

**Status: primary submission track.** Read [00_options_basics.md](00_options_basics.md) first if you haven't.

**2026-08-26 redesign**: this track was fully rebuilt from a user-supplied engineering
spec — the prior vertical-debit-spread strategy (section history preserved
below in §7) never had a real multi-factor entry gate; this version does.
Everything below describes the *current* strategy.

## 1. The structure, in plain English

Track 1 buys a single call or put outright — near-the-money (~0.50 delta),
1-2 days to expiration — when a multi-timeframe technical confluence
screener AND an LLM news-catalyst check both agree on direction. This is
simpler than the old vertical spread (one leg, not two — no "legs land on
different expirations" failure mode, no combined-liquidity requirement) and
still defined-risk: max loss is the premium paid, scaled by quantity, same
category of risk as the spread it replaces.

The real difference from "just buy a call" isn't the instrument — it's
*when* the agent is allowed to buy it. See §3.

## 2. Worked example (matches what the code actually produces)

Stock XYZ at $100, technical confluence just qualified bullish, LLM
catalyst validator approves:

| Field | Value |
|---|---|
| Contract | XYZ 2-DTE $100 call |
| Delta | 0.50 (accepted band: 0.45–0.55) |
| Ask | $1.20 |
| Equity | $100,000 |
| Sizing | `$100,000 × 3% = $3,000` budget ÷ `$120/contract` → **qty = 25** |
| Capital at risk | `$1.20 × 100 × 25 =` **$3,000** (the entire max loss) |
| Stop-loss | `min(LLM-suggested SL, 20% platform ceiling)` |
| TP1 (tier 1) | +50% → close 12 contracts, move stop to breakeven on the rest |
| TP2 (tier 2 / runner) | +100%, or a 15m EMA(50) reversal against the trade |
| Time-stop | 90 minutes if still flat (P&L between -10% and +10%) |
| EOD liquidation | unconditional close at 3:45pm ET |

## 3. Entry rule — exactly what the code checks

**Gate 0 — red-folder news blackout** (`app/agents/news_blackout_gate.py`, checked before
anything else, for every symbol, every cycle): no new entry within 5 minutes before/after a
scheduled high-impact macro release (FOMC, NFP, CPI, etc.) per `app/quant/news_calendar.py`'s
calendar. This is deterministic, not an LLM judgment — price action in the minutes around a
red-folder release is often violent and mechanical, unrelated to anything this screener is
actually measuring. Zero REST/LLM calls on a blocked cycle; `risk_gate.py` re-checks the same
condition as a backstop in case a slow cycle drifts across the boundary. See
`docs/tracks/technical_pipeline.md` §0 for the full mechanics and the calendar's honest
limitations (it's a manually curated list for one specific week, not a live feed).

Two further independent gates must both pass, in this order, so the (only) LLM call
never fires on a cycle that wouldn't qualify anyway:

**Gate 1 — technical confluence** (`app/quant/technical_signals.check_track1_confluence`,
called by `quant_engine.py` before any LLM node runs — see `graph.py`'s
conditional edge). All of the following must agree on the same direction:

| Signal | Bullish | Bearish |
|---|---|---|
| 15m trend | price > 50-EMA (native 15-minute bars) | price < 50-EMA |
| 1m trend | price > 20-EMA (1-minute bars — must agree with the 15m trend, not just the higher timeframe) | price < 20-EMA |
| 1m VWAP | price > VWAP | price < VWAP |
| 1m RSI(14) | 45–65 | 35–55 |
| 1m range | close > prior 20-bar high | close < prior 20-bar low |
| Relative volume | RVOL ≥ 1.5x (latest bar vs. prior 20-bar average) | RVOL ≥ 1.5x |

If this doesn't qualify, the cycle ends here — **zero LLM calls**. This is
the efficiency win the redesign was built around: the old strategy called
the LLM unconditionally on every cycle regardless of whether anything
qualified.

**Gate 2 — LLM catalyst validator** (`app/agents/track1_validator.py`,
reached only when gate 1 passes): one merged LLM call — not the old
sentiment-call-then-thesis-call split — returning a verdict, sentiment
score, confidence, and TP/SL/hold-time guidance in one schema (see
[technical_pipeline.md](technical_pipeline.md) for the exact prompt). The
hardcoded gate: `verdict == "APPROVE" AND |sentiment_score| >= 0.50 AND
confidence_pct >= 70`. Not runtime-tunable via Controls (unlike the old
sentiment_threshold/volume_ratio_min fields) — a deliberate simplification
confirmed with the user when this replaced the prior strategy.

If gate 2 fails, `propose_order()` is never called — the cycle logs a WAIT
with the LLM's own reasoning as the thesis, same as any other rejected cycle.

## 4. Who decides what — the LLM vs. the code

- **`track1_validator.py` (LLM)** validates whether real news supports the
  technical direction gate 1 already confirmed, and writes the thesis. It
  also proposes take_profit_pct/stop_loss_pct/max_hold_minutes as
  *guidance* — the deterministic layer below still clamps every one of
  these to platform limits before they become real numbers on an order.
- **`track1_alpha_spreads.py`'s `propose_order()` (pure Python)** decides
  everything that actually matters — contract selection (delta/DTE/OI/spread
  filters), quantity, capital-at-risk, and the final clamped SL/TP/hold-time
  — from `state["technical_signal"]` and the validator's schema fields.
  **The LLM's thesis text is never parsed or acted on for this decision.**
- **`risk_gate.py` (pure Python, zero LLM calls)** — unchanged by this
  redesign: rejects if position size > 3% of equity, margin utilization >
  50%, 6+ positions already open, cash reserves would drop below 55%,
  sector exposure would exceed 15%, or stop-loss exceeds the 20% ceiling.
  Confirmed leg-count-agnostic — none of its checks assume a 2-leg spread,
  so a single-leg order clears it with zero code changes.

## 5. Exit management (`app/agents/position_monitor.py`)

A tiered exit, checked on a fixed ~15s cadence (independent of the
bar-close-triggered entries — see §6) against each open trade's live
Alpaca position:

1. **End-of-day liquidation** — at/after 3:45pm ET, close unconditionally,
   before any other check, to eliminate overnight gap risk.
2. **Stop-loss** — close fully if P&L ≤ -20% (or ≤ 0%/breakeven, once tier 1
   has already fired).
3. **Tier 2 / runner exit** — close the remainder fully at +100%, or if the
   fresh 15m EMA(50) trend reverses against the trade's original direction.
4. **Tier 1 / partial** — at +50%, close half the position and mark the
   trade (`Trade.tp1_triggered`) so the next sweep treats the stop as
   breakeven for the rest.
5. **Time-stop** — if the position has been open ≥ 90 minutes and is still
   flat (-10% to +10%), close fully — a stalled setup, not a working one.

## 6. Data pipeline — bar-close triggered, not interval-polled

`scripts/run_agent_stream_track1.py` (not `run_agent_loop.py`, which Track 4
still uses unchanged) subscribes to a real Alpaca websocket stream
(`StockDataStream.subscribe_bars`) for 1-minute bar closes on the watched
symbols. Every bar close immediately triggers one LangGraph cycle for that
symbol — no `--interval` flag, no fixed sleep between passes, no Controls UI
field for it. The 15-minute bars gate 1 needs for its 50-EMA trend check are
fetched natively via REST (`rest_client.get_15m_bars`), not resampled from
1-minute data — 500 1-minute bars only resample to ~33 complete 15-minute
candles, not enough to seed a stable 50-period EMA.

**Immediate warmup pass on connect**: the script doesn't wait for the first
natural bar close (which could be up to ~60s away) before doing anything —
right after the stream connects, every symbol is screened once immediately
using the full historical window already available via REST. From that
point on, each bar-close event naturally slides the same window forward one
bar at a time. There is no persistent buffer of our own being appended to
(every cycle, warmup or bar-close-triggered, re-fetches its own window fresh
via REST) — and Alpaca's `bars` websocket channel only fires once a minute
has fully elapsed (unlike `quotes`/`trades`, it doesn't push a "still
forming, will be corrected" message for the in-progress candle), so a
bar-close trigger is always screening an already-closed candle, never a
partial one.

## 7. History (superseded by this redesign)

The original v1 (bull/bear vertical debit spread, single-timeframe SMA
breakout + tunable sentiment threshold, interval-polled) shipped
2026-08-23/24 and is fully superseded above. Its DTE-matching bug fix
(`closest_by_delta`'s `target_dte` narrowing) and the general "LLM writes
the thesis, code decides the trade" split both carry forward unchanged into
this redesign.
