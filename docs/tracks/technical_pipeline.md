# Technical Pipeline — Exactly What Runs, Cycle by Cycle

This is the literal, code-accurate technical reference: exact API calls, exact prompts, exact
schemas, exact parameters. The `track1_alpha_spreads.md` / `track4_income_wheel.md` docs explain
the *strategy* (why the trade makes sense); this doc explains the *machinery* (what data moves
where, and what's actually sent to the LLM). Where the code has a surprising or non-obvious
behavior, it's called out explicitly rather than glossed over — including two things that
**don't** work the way they might look like they should (see §8).

One decision cycle = one pass through `app/agents/graph.py`'s LangGraph. **As of the 2026-08-26
Track 1 redesign, the same-day Track 4 streamlining, and the 2026-08-27 latency pass + red-folder
news blackout gate, the graph branches by track and starts with a universal safety gate** — it is
no longer one fixed shape for every track:

```
                                                    ┌─(Track 1, confluence qualified)──→ track1_validator[LLM] ──┐
                                                    ├─(Track 4, IV+regime qualified)───→ track4_validator[LLM] ───┤
news_blackout_gate ──(clear)──→ market_ingestion → quant_engine ──┤                                                            ├──→ risk_gate → execution
        │                                                        ├─(Track 1/4, not qualified)──────→ END (0 LLM calls)         │
        │                                                        └─(Track 2/3)──────────────────────→ news_analyst[LLM] → lead_architect[LLM] ─┘
        └─(blocked)──→ END (0 REST calls, 0 LLM calls)
```

`news_blackout_gate.py` (§0) is the entry point for **every track** — a cycle starting within 5
minutes before/after a scheduled high-impact macro release (FOMC, NFP, CPI, etc. — see
`app/quant/news_calendar.py`) ends immediately, before `market_ingestion.py` fetches anything at
all. `risk_gate.py` (§6) re-checks the same condition as a backstop for a cycle that started clear
but ran long enough (a slow LLM call) to drift across the boundary before reaching final approval.

Track 1 never reaches `news_analyst.py`/`lead_architect.py` — its technical confluence screener
(§2a) gates the LLM call *before* it's ever made, and its LLM validation + thesis are one merged
call (`track1_validator.py`, §3b) instead of the two-call split tracks 2/3 still use. Track 4
follows the same shape as of the 2026-08-26 streamlining: IV percentile (and, for a fresh
cash-secured put only, a daily-bar 200-EMA/RSI regime check — §2a) must qualify before its own
merged risk-officer call (`track4_validator.py`, §3c). Tracks 2/3 are unaffected — same shape,
same nodes, as before. `risk_gate.py` and `execution.py` (§6-7) are shared by every track
unchanged; they're leg-count- and track-agnostic (aside from the position-size cap itself now
branching by track — §6).

Every node is wrapped in a timing decorator (`graph.py`'s `_timed()`) that logs its own duration in
milliseconds to the same per-track log file the WAIT/TRADE line already goes to — added
specifically to chase Track 1's sub-2-second candle-close-to-decision target (§1 explains the
concurrent-fetch changes that came out of that work).

---

## 0. Red-Folder News Blackout Gate (`app/agents/news_blackout_gate.py`) — no LLM, graph entry point

Pure Python, ~0ms — a plain comparison against an in-memory list, no REST/LLM call of its own.
Reached first, for every track, before `market_ingestion.py` fetches anything.

Calls `app/quant/news_calendar.py`'s `check_news_blackout()`: `True` + a reason string if the
current UTC time falls within `BLACKOUT_MINUTES_BEFORE`/`AFTER` (5 minutes each side, inclusive)
of any entry in `RED_FOLDER_CALENDAR`. If blocked, the node returns `{"news_blackout_reason":
"<reason>"}`, `graph.py`'s conditional edge routes straight to `END`, and the calling script logs
`[SYMBOL] BLOCKED — <reason>` instead of a WAIT/TRADE/REJECTED line — zero REST calls, zero LLM
calls, same "gate cheaply before spending anything" principle as Track 1/4's own screens.

**This is a manually curated, week-specific calendar, not a live feed.** No free/already-integrated
economic calendar API exists in this project (same category of gap as Track 4's earnings-conflict
check, §3c/§8) — `RED_FOLDER_CALENDAR` was seeded via web search against federalreserve.gov,
ismworld.org, bls.gov-adjacent sources, and adp.com for the Aug 28 - Sep 4, 2026 hackathon week
specifically (FOMC confirmed absent that week; ISM Manufacturing PMI + JOLTS on Sep 1, ADP on
Sep 2, weekly jobless claims on Sep 3, Employment Situation/NFP on Sep 4 — each entry's `source`
field notes where it was verified). **Not guaranteed exhaustive** (lower-tier releases weren't all
individually checked) and **needs manual updating for any week beyond the one seeded** — re-verify
against a live economic calendar (ForexFactory, Investing.com, TradingEconomics) before relying on
this for real capital past the current hackathon week.

Times are stored and compared as explicit UTC-aware `datetime`s throughout (never the host
machine's local clock, so the check is correct regardless of what timezone the process runs in).
Logged reasons and `todays_calendar_summary()` (injected into `track1_validator.py`'s/
`track4_validator.py`'s LLM prompts — §3b/§3c — so the catalyst/risk-officer LLM has full-day
macro context, not just this symbol's own headlines) render both UTC and `Africa/Nairobi` (EAT,
UTC+3 year-round, no DST) side by side, e.g. `12:30 UTC / 15:30 EAT`.

`risk_gate.py` (§6) re-checks `check_news_blackout()` again as a backstop — this gate only
guarantees the cycle *started* clear; a slow LLM call could still let a cycle drift across a
blackout boundary before `risk_gate.py`'s final approval, and that check exists to catch exactly
that. Position management (`position_monitor.py`'s exit sweep) is deliberately **not** gated by
this at all — a stop-loss or EOD liquidation should still fire during a news spike; only *new*
entries are blocked.

---

## 1. Data ingestion (`app/agents/market_ingestion.py`) — no LLM

**The only node in the graph that does network I/O** — `quant_engine.py` (§2) is now pure
computation over whatever this node fetched, moved here specifically so independent REST calls
run concurrently instead of one after another (added 2026-08-27 chasing Track 1's sub-2-second
candle-close-to-decision target; confirmed via `graph.py`'s per-node timing that the old
sequential ordering was the dominant cost of a WAIT cycle — see `PLAN.md`'s session log for the
before/after numbers). All fetches for a given track run in one `concurrent.futures.ThreadPoolExecutor`:

**a) `get_recent_bars(symbol)`** → `app/alpaca/rest_client.py`, every track
- Alpaca SDK call: `StockHistoricalDataClient.get_stock_bars(StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Minute, limit=100))`
- **100 one-minute bars**, oldest-first. Each bar: `{timestamp, open, high, low, close, volume, trade_count, vwap}` (raw Alpaca bar fields via `.df.reset_index()`).
- This is a **short, noisy timeframe** — not daily bars, not a multi-timeframe scan. Worth knowing before reading a "breakout" signal as a multi-day trend call.

**b) `get_option_chain(symbol)`** → tracks 2/3/4 only, joins two separate Alpaca APIs by OCC contract symbol:
- `TradingClient.get_option_contracts(GetOptionContractsRequest(underlying_symbols=[symbol], status=ACTIVE, expiration_date_gte=today, expiration_date_lte=today+45d, limit=10000))` — contract metadata: `type` (call/put), `strike_price`, `expiration_date`, `open_interest`.
- `OptionHistoricalDataClient.get_option_chain(OptionChainRequest(underlying_symbol=symbol, expiration_date_gte=today, expiration_date_lte=today+45d))` — market-data snapshot: `latest_quote.bid_price`/`ask_price`, `implied_volatility`, `greeks` (Alpaca's own, see §3).
- Joined into one flat dict per contract: `{symbol, type, strike_price, expiration_date, open_interest, bid, ask, mid, spread_pct, implied_volatility, greeks}`. Contracts with no live quote (`bid`/`ask` both falsy) are dropped — a first liquidity screen.
- 45-day window: covers Track 1's 1-2 DTE and Track 4's 21 DTE with margin either side.
- **Skipped entirely for Track 1** (`option_chain: []`) — confirmed via timing logs to be the single most expensive call in the whole cycle (~12s for a liquid underlying, thousands of contracts). Track 1's gate (`technical_signal.qualified`) never reads it, so it's deferred to `track1_validator.py` (§3b), fetched only on a cycle that's already cleared both the technical gate and the LLM catalyst check.

**c) `get_15m_bars(symbol)`** → Track 1 only, concurrent with (a)
- Native 15-minute bars (not resampled from the 1-minute bars above; see §2a for why) — stored in `state["bars_15m"]`, used by `quant_engine.py`'s `check_track1_confluence()` for the 50-period EMA trend check. Moved here from `quant_engine.py` on 2026-08-27 specifically so it runs concurrently with (a) instead of after it.

**d) `get_daily_bars(symbol, limit=220)`** → Track 4 only, concurrent with (a)/(b)
- Native daily bars, enough to seed a 200-period EMA plus RSI(14) warmup — stored in `state["daily_bars"]`, used by `check_wheel_put_regime()` (§2a). Likewise moved here on 2026-08-27.

Neither (a) nor (b) fetches RSI, MACD, Bollinger Bands, or any other classic technical indicator — see §2 for exactly what *is* computed from these bars.

`app/quant/risk_metrics.py`'s `portfolio_risk_snapshot()` (called from `quant_engine.py`, §2)
makes two more independent Alpaca calls of its own (`get_account_info`, `get_all_positions`) — also
parallelized (its own small thread pool) on 2026-08-27 for the same reason, though it stayed in
`quant_engine.py` rather than moving here since it's account-level, not per-symbol market data.

---

## 2. Quant Engine (`app/agents/quant_engine.py`) — no LLM, pure Python

Computes four things from the raw data above, all deterministic:

### a) Technical signal — branches by track (`app/quant/technical_signals.py`, `quant_engine.py`)

`quant_engine.py` branches three ways: **Track 1** calls `check_track1_confluence()` (below);
**Track 4** calls `check_wheel_put_regime()` (below) on daily bars; **tracks 2/3** call
`detect_breakout()` (also below, byte-identical to before the 2026-08-26 redesigns).

**`detect_breakout()` — tracks 2/3's signal.** A single-timeframe SMA-breakout-with-volume-
confirmation, computed on the 100 one-minute bars from §1a:

```
sma_window = 20          # bars, i.e. last 20 one-minute closes
volume_lookback = 20     # bars
volume_ratio_min = <live value, Track 4's Controls field, default 1.2>
```

- `sma` = mean of the **last 20 closes**.
- `price_vs_sma_pct` = `(latest_close - sma) / sma`.
- `avg_volume` = mean of the **19 bars immediately before** the latest one.
- `volume_ratio` = `latest_bar_volume / avg_volume`; confirmed if `>= volume_ratio_min`.
- `prior_high`/`prior_low` = max/min close of those same prior 19 bars (excludes the latest).
- **Breakout up**: `latest_close > prior_high` AND `price_vs_sma_pct > 0` AND `volume_ratio >= volume_ratio_min`. Down is the exact mirror.
- Output: `{breakout: bool, direction: "up"|"down"|None, price_vs_sma_pct: float, volume_ratio: float}`.

Needs at least 21 bars or returns a flat "no breakout" — with `limit=100` bars fetched, this is essentially always satisfied once the market's been open ~21 minutes that session.

**`check_track1_confluence(bars_1m, bars_15m)` — Track 1's signal, and its early-exit gate.**
This is the only signal Track 1 uses; `graph.py`'s conditional edge routes straight to `END` (zero
LLM calls) when it doesn't qualify — see the graph diagram above. All of the following must
agree on the same direction:

| Check | Function | Bullish | Bearish |
|---|---|---|---|
| 15m trend | `compute_ema(closes_15m, 50)` | price > 15m 50-EMA | price < 15m 50-EMA |
| 1m trend | `compute_ema(closes_1m, 20)` | price > 1m 20-EMA | price < 1m 20-EMA |
| 1m VWAP | `compute_vwap(bars_1m)` | price > VWAP | price < VWAP |
| 1m RSI(14) | `compute_rsi(closes_1m, 14)` (Wilder's smoothing) | 45–65 | 35–55 |
| 1m range | (same 20-bar prior-range logic as `detect_breakout`) | close > prior 20-bar high | close < prior 20-bar low |
| Relative volume | `compute_rvol(volumes_1m, 20)` | ≥ 1.5x | ≥ 1.5x |

**Both EMA checks must agree independently** — added specifically because a 15m-only trend check
would let a symbol qualify while its 1-minute trend is actually pointing the other way (e.g. a
brief 1m pullback inside a larger 15m uptrend); requiring both closes the gap. `bars_15m` is
fetched natively via REST (`rest_client.get_15m_bars`, §1), not resampled from the 1-minute
buffer — 500 1-minute bars only resample to ~33 complete 15-minute candles, short of the 50
needed to seed a stable EMA. `compute_vwap()` is a rolling-window VWAP over whatever bars are
passed in, not a true session-open-anchored VWAP (this module never sees a guaranteed
session-start alignment) — an approximation, not exact. Needs ≥21 one-minute bars (the 1m
20-period EMA needs no more than the existing 20-bar breakout/RSI window already requires) and
≥50 fifteen-minute bars, or returns `{"qualified": False, "direction": None, ...}`.

Output: `{qualified: bool, direction: "up"|"down"|None, trend_regime: str, price_vs_15m_ema_pct: float, price_vs_1m_ema_pct: float, vwap: float, price_vs_vwap_pct: float, rvol: float, rsi: float}`.

**`check_wheel_put_regime(daily_bars)` — Track 4's signal, gates fresh cash-secured-put entries
only.** Computed on the 220 daily bars from §1's Track-4-only call, not the 1-minute bars — the
Wheel operates on a multi-week holding horizon, not intraday. Covered call entries (State 1) don't
use this signal at all — only the cost-basis floor in §5 gates those.

| Check | Function | Qualifies |
|---|---|---|
| 200-day trend | `compute_ema(closes, 200)` | price > 200-EMA (avoid selling puts into a structural downtrend — a "falling knife") |
| RSI(14) | `compute_rsi(closes, 14)` (Wilder's smoothing) | 35–55 (an oversold pullback within an uptrend, not a freefall) |

Needs ≥200 daily bars or returns `{"qualified": False, "price_vs_200ema_pct": 0.0, "rsi": 0.0}`.
Output: `{qualified: bool, price_vs_200ema_pct: float, rsi: float}`. Reused a second time by
`position_monitor.py`'s stop-loss defense check (`track4_income_wheel.md` §7) to detect a "broken
200-EMA support" condition, not just at entry.

### b) Greeks (`app/quant/greeks.py::compute_greeks`)

**Not derived from our own Black-Scholes model in the live pipeline.** `compute_greeks()` sums
whatever `greeks` dict Alpaca's own snapshot already returned per contract (§1b) — `{delta,
gamma, vega, theta, rho}` totaled across every contract in the chain. This is a portfolio-level
aggregate handed to the LLM for context, not a per-contract number used in a trading decision.

The system *does* have its own analytical Black-Scholes implementation
(`app/quant/black_scholes.py` + the individual `delta()`/`gamma()`/`vega()`/`theta()`/`rho()`
functions in `greeks.py`) — but nothing in the live decision path calls them. They're exercised
by `tests/test_black_scholes.py` only. Worth knowing if you're explaining "how are Greeks
computed" to a judge: the honest answer is "Alpaca computes them, we aggregate and read them,"
not "we run Black-Scholes live."

**Contract selection** (`closest_by_delta()` in `app/strategies/_common.py`, used by every
strategy's `propose_order()`) also reads Alpaca's own per-contract `delta`, not ours.

### c) IV Percentile (`app/quant/iv_percentile.py::compute_iv_percentile`)

```
IV_P = (IV_current - IV_min_52wk) / (IV_max_52wk - IV_min_52wk) * 100
```

- `IV_current` = mean `implied_volatility` across all quoted contracts in the chain (a crude
  "representative" ATM-ish IV, not strictly the ATM contract's own IV).
- `IV_min_52wk`/`IV_max_52wk` come from `db/repository.py::get_iv_52wk_range()` — **as of the
  2026-08-26 Track 4 streamlining, this is real, self-bootstrapping history**, not a permanent
  placeholder. Every call to `compute_iv_percentile()` (every track, every cycle, unconditionally)
  first calls `record_iv_observation(symbol, current_iv)`, inserting one row into a new
  `iv_observations` table. `get_iv_52wk_range()` then queries the last 365 days of observations
  for that symbol: if fewer than 20 exist yet, it falls back to the old hardcoded `(0.10, 0.90)`
  range (documented, not silently pretending to be real); once 20+ exist, it returns the real
  observed `min`/`max`. Because this runs for every track, Track 1's much higher cycle frequency
  on shared symbols (SPY/QQQ/mega-caps) passively accelerates how fast Track 4's range becomes
  real data for those names — a real 52-week range still takes a year to fully mature, but it's
  genuine accumulating data from day one, not a permanent stand-in.

### d) Portfolio risk snapshot (`app/quant/risk_metrics.py::portfolio_risk_snapshot`)

Two more Alpaca calls: `get_account_info()` (equity, cash, maintenance_margin) and
`get_all_positions()` (every open position, both asset classes). Returns
`{equity, cash, margin_utilization_pct, position_count, holds_underlying_shares, cost_basis, positions}` —
`holds_underlying_shares` and `cost_basis` both come from the same `WheelState` DB table
(the latter added in the 2026-08-26 streamlining), written by `position_monitor.py`'s Track 4
sweep (see the Track 4 doc §7), not computed here directly. `cost_basis` floors Track 4's next
covered-call strike selection (§5) — `None` until a cash-secured put has actually been assigned.

All four of (a)-(d) land in `AgentState` as `technical_signal`, `greeks`, `iv_percentile`,
`portfolio_risk` — read by both the LLM prompt (§4) and each strategy's deterministic
`propose_order()` (§5).

---

## 3a. News & Sentiment (`app/agents/news_analyst.py`) — tracks 2/3 only, LLM call #1 of 2

**As of the 2026-08-26 redesigns, neither Track 1 nor Track 4 reaches this node** — see §3b/§3c
for their replacements. This section describes tracks 2/3's unchanged behavior.

**Data source**: Alpaca MCP tool `get_news`, called as `get_news(state["symbol"])` — passing the
Alpaca MCP client `symbol` positionally where the underlying `mcp_client.get_news(symbols: list[str], limit: int = 10)` signature expects a *list*. In practice a bare string still round-trips through the MCP JSON-RPC call and has returned real headlines in live testing, but the type mismatch is real — flagged here rather than silently left undocumented; not fixed this pass since it isn't causing an observed failure.

**Exact system prompt** (verbatim, `news_analyst.py` line 13):

```
You are a market sentiment analyst. Given recent news headlines for a
symbol, return a JSON object {"score": float in [-1, 1], "rationale": str}.
score > 0.75 means strong bullish conviction, < -0.75 strong bearish conviction.
```

**Exact user message** (verbatim template):

```
Headlines for {symbol}:
{headline 1}
{headline 2}
...
```

(one headline per line, newline-joined, up to whatever `get_news` returned — no explicit cap in
this call, though the MCP tool itself defaults to `limit=10`)

**Call mechanics**: `llm.structured_generate(system=SYSTEM_PROMPT, user=..., schema={"score": float, "rationale": str})`. This is NOT native provider tool-calling/JSON mode — `structured_generate()` (in `app/llm/client.py`) appends a plain-text instruction (`f"{system}\n\nRespond with ONLY a JSON object: {{{fields}}}"`) to the system prompt and calls `json.loads()` on whatever text comes back. If the model doesn't comply exactly, this raises `json.JSONDecodeError` and the cycle fails for that symbol (caught by `run_agent_loop.py`'s per-symbol `except Exception`, logged, next symbol/pass continues).

**Output**: `state["sentiment_score"]` (float, -1..1), `state["sentiment_rationale"]` (str). This score is shown to `lead_architect.py`'s prompt as context for tracks 2/3.

---

## 3b. Track 1 Catalyst Validator (`app/agents/track1_validator.py`) — Track 1 only, one merged LLM call

Reached only when §2a's confluence screener already qualified the symbol. Replaces §3a +
§4 (news_analyst + lead_architect) for Track 1 with a single call that both validates the
setup against real news and produces sizing guidance — not a separate sentiment-then-thesis split.

**Data source**: `get_news([symbol])` — a one-element list, the type `mcp_client.get_news`
actually expects (unlike news_analyst.py's bare-string call — see §8).

**Exact system prompt** (verbatim):

```
You are the Lead Quantitative Strategist for an autonomous intraday options alpha agent.
Your sole role is to validate whether breaking news catalysts align with a deterministic technical breakout that has already been confirmed by a separate quantitative screener — you are not re-deriving the technical case, only checking whether news supports or contradicts it.

Evaluation Rules:
1. Directional Alignment: Bullish breakouts require positive catalysts; Bearish breakdowns require negative catalysts. If news is absent, neutral, or contradicts the technical direction, verdict must be "REJECT".
2. Sentiment Score: Output a float between -1.0 (max bearish) and +1.0 (max bullish). Neutral/conflicted news must fall between -0.49 and +0.49.
3. Confidence: Output a percentage (0 to 100) reflecting how strongly the news supports this specific trade.
4. Targets: Propose take_profit_pct (e.g. 40.0 to 100.0) and stop_loss_pct (e.g. 10.0 to 20.0) based on news intensity and catalyst horizon — these are guidance the deterministic strategy layer will still clamp to platform risk limits.
5. Strict Compliance: Output MUST be valid JSON matching the schema — no markdown, no prose outside the JSON fields.
```

**Exact user message template**:

```
Symbol: {symbol}
Trigger Direction: {direction} (1-minute confluence confirmed by 15-minute trend)
Technical Summary:
- 15m Trend: {trend_regime} (price vs 15m 50-EMA: {price_vs_15m_ema_pct:.2%})
- 1m Trend: price vs 1m 20-EMA: {price_vs_1m_ema_pct:.2%}
- 1m VWAP offset: {price_vs_vwap_pct:.2%}
- 1m Relative Volume (RVOL): {rvol:.2f}x
- 1m RSI(14): {rsi:.1f}
Recent News Headlines:
{headline 1}
{headline 2}
...
```

**Call mechanics**: `llm.structured_generate(system=..., user=..., schema={"verdict": str, "sentiment_score": float, "confidence_pct": float, "take_profit_pct": float, "stop_loss_pct": float, "max_hold_minutes": int, "thesis": str})` — same prompt-based JSON coercion as every other `structured_generate()` call (§3a), with its own retry-on-malformed-JSON loop (`app/llm/client.py`).

**The hardcoded gate** (not Controls-UI-tunable, unlike the old sentiment_threshold/volume_ratio_min):
```python
qualified = (
    result["verdict"] == "APPROVE"
    and abs(result["sentiment_score"]) >= 0.50
    and result["confidence_pct"] >= 70
)
```
If not qualified, `propose_order()` is never called — `state["proposed_order"] = None`, and
`risk_gate.py`'s existing "no order proposed" rejection fires unchanged, same code path every
other track's rejected cycle already uses.

**Output**: `state["sentiment_score"]`, `state["thesis"]`, `state["proposed_order"]` (via
`track1_alpha_spreads.propose_order(state, result)` when qualified — §5).

---

## 3c. Track 4 Risk Officer Validator (`app/agents/track4_validator.py`) — Track 4 only, one merged LLM call

Reached only when §2a's IV percentile gate (and, for a fresh cash-secured put only, the daily
regime check) already qualified. Replaces §3a + §4 (news_analyst + lead_architect) for Track 4,
same "merge two calls into one, gate it behind a deterministic screener" pattern as §3b — but a
genuinely different *job*: not a directional catalyst check, a solvency/binary-event risk gate,
per the user-supplied Wheel Strategy spec.

**Caveat, stated plainly**: there is no earnings-calendar data source anywhere in this codebase or
Alpaca's MCP tools (checked before building this) — the "earnings within 21 days" rule below is
necessarily an LLM judgment call from news headlines, not a real calendar lookup.

**Data source**: `get_news([symbol])` — correctly a one-element list (same as §3b; this node is
new code, so it never had §3a's bare-string bug to begin with).

**Exact system prompt** (verbatim):

```
You are the Lead Risk Officer for a systematic institutional Income Wheel Agent.
Your sole job is to protect capital from catastrophic tail risk, impending binary events, and severe structural degradation.

Evaluation Rules:
1. Binary Event Defense: If earnings or FDA announcements fall within the 21-day holding period, REJECT the trade (avoid IV crush / gap-down assignment).
2. Solvency & Sentiment: Evaluate if recent news indicates fraud, regulatory investigations, or systemic business deterioration.
3. Output strictly valid JSON matching the schema. No prose.
```

**Exact user message template**:

```
Symbol: {symbol}
Wheel leg under consideration: {covered call | cash-secured put} (~21 DTE)
IV percentile: {iv_percentile:.1f}
Daily regime: price vs 200-EMA {price_vs_200ema_pct:.2%}, RSI(14) {rsi:.1f}   [cash-secured put only]
Recent News Headlines:
{headline 1}
{headline 2}
...
```

**Call mechanics**: `llm.structured_generate(system=..., user=..., schema={"verdict": str, "risk_score": float, "earnings_conflict": bool, "confidence_pct": float, "profit_target_pct": float, "thesis": str})` — same prompt-based JSON coercion as §3a/§3b.

**The hardcoded gate** (not Controls-UI-tunable, same precedent as §3b):
```python
qualified = (
    result["verdict"] == "APPROVE"
    and not result["earnings_conflict"]
    and result["risk_score"] <= 0.35
    and result["confidence_pct"] >= 70
)
```
If not qualified, `propose_order()` is never called — same "no order proposed" rejection path
every other track's rejected cycle already uses.

**Output**: `state["thesis"]`, `state["proposed_order"]` (via
`track4_income_wheel.propose_order(state, result)` when qualified — §5). `profit_target_pct` is
carried in the LLM's result dict for thesis coherence only — the deterministic 50% rule
(`track4_income_wheel.md` §7) governs the real exit, same split as Track 1's TP/SL fields.

---

## 4. Lead Architect (`app/agents/lead_architect.py`) — tracks 2/3 only, LLM call #2 of 2

Writes the human-readable thesis shown in the dashboard. **Does not decide anything** — see §5.
**Neither Track 1 nor Track 4 uses this node** — see §3b/§3c.

**System prompt template** (verbatim, `SYSTEM_PROMPT_TEMPLATE`):

```
You are the lead trading strategist for an autonomous options agent.
The agent is currently running under exactly ONE strategy — you must reason
only within its rules below, even if the raw numbers might superficially
suggest a different strategy shape.

ACTIVE STRATEGY:
{track_rule}

Given the quantitative signals and sentiment score, produce a one-sentence
trading thesis that is explicit, testable, and consistent with the active
strategy above. If the active strategy's entry condition is not met, say so
plainly (e.g. "No breakout confirmed; sentiment alone is insufficient —
no trade this cycle") rather than inventing a rationale for a different
structure.
```

`{track_rule}` is substituted per-track from `TRACK_ENTRY_RULES` — plain strings for tracks
2/3 (neither Track 1 nor Track 4 has an entry here anymore; §3b/§3c cover their equivalents).

**Exact user message** (verbatim template, `lead_architect.py::run`):

```
Symbol: {symbol}
Greeks: {greeks dict}
IV percentile: {iv_percentile}
Technical signal: {technical_signal dict}
Sentiment: {sentiment_score} ({sentiment_rationale})
Portfolio risk: {portfolio_risk dict}
```

The dicts are Python `dict.__repr__` output interpolated via an f-string — not pretty-printed
JSON, just whatever `str({...})` produces. See §7 for one fully worked-out example with real
shapes.

**Call mechanics**: plain `llm.generate(system=..., user=...)` — free-text completion, no schema,
no JSON parsing. The raw string returned *is* the thesis, verbatim, persisted as-is.

**Output**: `state["thesis"]` (str) → then `strategy.propose_order(state, thesis)` is called for
`state["track"]`'s module, and `state["proposed_order"]` is whatever that returns (§5). The
`thesis` string is attached to the order/trade record purely for display — never parsed.

---

## 5. Strategy modules — deterministic, no LLM (`app/strategies/*.py`)

This is the part worth being precise about for judges: **the LLM's thesis text is never read by
this code.** Each strategy module reads the raw state fields directly.

**Track 1** (`track1_alpha_spreads.py::propose_order(state, llm_result)`) — called by
`track1_validator.py`, not `lead_architect.py`, and takes the LLM's structured result dict
directly rather than a thesis string:
```python
direction = technical_signal["direction"]           # already qualified by §2a/§3b before this runs
is_call = direction == "up"
liquid_chain = [c for c in option_chain if c["open_interest"] >= 500 and c["spread_pct"] <= 0.05]
contract = closest_by_delta(liquid_chain, ±0.50, is_call, target_dte=2)
# then: reject unless dte in (1, 2) and abs(delta) in [0.45, 0.55]
qty = max(1, int((equity * 0.03) // (contract["ask"] * 100)))
stop_loss_pct = min(llm_result["stop_loss_pct"] / 100, 0.20)   # clamped to risk_gate's ceiling
```
Single-leg (not a 2-leg spread), `qty` sized dynamically to 3% of equity (the first strategy
module to ever need `qty > 1` — see §7), `tp1_pct=0.50`/`tp2_pct=1.00` fixed constants (not
derived from the LLM's `take_profit_pct`), `max_hold_minutes` clamped to ≤120 (default 90).

**Track 4** (`track4_income_wheel.py::propose_order(state, llm_result)`) — called by
`track4_validator.py`, same validator-driven pattern as Track 1:
```python
if state["iv_percentile"] < 45: return None
liquid_chain = [c for c in option_chain if c["open_interest"] >= 500 and c["spread_pct"] <= 0.05]

if holds_shares:
    candidates = [c for c in liquid_chain if c["type"] != "call" or c["strike_price"] >= cost_basis]
    leg = closest_by_delta(candidates, 0.30, is_call=True, target_dte=21)   # covered call
else:
    if not technical_signal["qualified"]: return None                      # daily regime gate (§2a)
    leg = closest_by_delta(liquid_chain, -0.30, is_call=False, target_dte=21)  # cash-secured put
# then: reject unless dte in [14, 30] and abs(delta) in [0.25, 0.30]
```
Covered calls are floored at `cost_basis` (from `WheelState`, §2d) *before* ranking by delta —
degrades gracefully (no floor applied) if `cost_basis` isn't recorded. Fresh cash-secured puts
additionally require the daily 200-EMA/RSI regime check to have already qualified.

Both tracks attach `capital_at_risk` explicitly (net debit for Track 1's single-leg long; strike×100
for a CSP; $0 for a covered call — see each track's doc for why) and `stop_loss_pct` —
`risk_gate.py` rejects any order missing this or exceeding the platform ceiling. Track 4's
`capital_at_risk` also adds a `strike_price` field on the leg itself (new in the 2026-08-26
streamlining) — read by `position_monitor.py`'s assignment-detection sweep to compute
`cost_basis` without parsing the OCC option symbol.

---

## 6. Risk Gate (`app/agents/risk_gate.py`) — deterministic, zero LLM calls, checked in order

1. Order exists and has `symbol`+`legs`.
2. Position size: `capital_at_risk / equity <= cap`, where `cap` is **track-dependent** (added in
   the 2026-08-26 Track 4 streamlining) — `settings.max_wheel_collateral_pct` (25%) for Track 4,
   `settings.max_position_pct` (3%) for every other track. A cash-secured put's collateral (strike
   × 100) is posted cash, not capital-at-risk the way every other track's premium/net-debit is —
   applying the 3% cap to it would reject every symbol in the watchlist, including the cheapest
   (confirmed: even a $58 stock's 100-share collateral is 5.8% of a $100k account).
3. Margin utilization `<= 50%`.
4. Open position count `< 6` (`settings.max_open_positions`).
5. Projected cash reserve after this trade `>= 55%` of equity.
6. Sector exposure (via `app/watchlist.py`'s `SECTOR_MAP`) after this trade `<= 15%`.
7. `stop_loss_pct` present and `<= 20%` (`settings.stop_loss_pct`).

Any failure short-circuits with a specific rejection reason string, persisted to
`AgentDecision.risk_rejection_reason` — this is what the "REJECTED" rows in Decision History
show. All numeric defaults live in `app/config.py`.

## 7. Execution (`app/agents/execution.py`) — only reached if risk-approved

Translates each leg (`option_symbol` → `symbol`, per `mcp_client.OptionLeg`'s shape) and calls
the Alpaca MCP tool `place_option_order`:

```python
place_option_order(
    symbol=order["symbol"],
    legs=[{"symbol": ..., "ratio_qty": 1, "side": "buy"|"sell"}, ...],
    order_class="mleg" if len(legs) > 1 else "simple",
    order_type="market" | "limit",
    time_in_force="day",
    qty=order.get("qty", 1),   # Track 1 sizes this dynamically (§5); every other strategy implies 1
    limit_price=net_debit_credit(legs) / 100 if order_type == "limit" else None,
)
```

Every strategy sets `order_type: "limit"`, so `limit_price` is always populated —
`net_debit_credit()` sums signed per-share cost × 100 (dollar-scaled), divided back by 100 for
Alpaca's per-share `limit_price` convention; correct regardless of `qty` since each leg's own
`ratio_qty` stays `1` for a single-leg order (the real contract count travels via `qty` at the
order level, not `ratio_qty` — Track 1's `qty` is the first time this has ever been >1). Result
persisted via `save_trade()` with `status="open"`, `track`, the full order dict, and the thesis text.

---

## 8. Things that look like they should work a certain way, but don't (yet)

Worth knowing before assuming the system is doing more than it is:

- **`temperature` in the Controls UI is not wired to any LLM call.** It's stored in
  `config_store.py`/`routes_config.py`'s config schema, defaults to `"0.3"`, round-trips through
  Save/Load — but `llm/client.py`'s `generate()` never reads or passes it to either the OpenAI-
  compatible `.chat.completions.create()` call or the Anthropic `.messages.create()` call. Every
  live call runs at each provider's own default sampling temperature. Not fixed this pass —
  documented so nobody assumes changing it in the UI changes model behavior.
- **RSI, MACD, Bollinger Bands, etc. are not used by tracks 2/3.** Their only price-action signal
  is the SMA-breakout-plus-volume-confirmation in §2a — Track 1 (RSI(14), VWAP, dual EMA) and
  Track 4 (RSI(14), 200-EMA) both use real indicators, but tracks 2/3 still don't.
- **Greeks aren't computed by this system's own Black-Scholes model in the live path** — see §2b.
  The code to do so exists and is unit-tested, but the live pipeline reads Alpaca's own Greeks.
- **`iv_percentile`'s 52-week range self-bootstraps from real observations (see §2c) but starts
  thin** — until a symbol has 20+ recorded observations, it still falls back to the original
  hardcoded `(0.10, 0.90)` placeholder. Early in a fresh deployment, `iv_percentile` is only as
  meaningful as that placeholder; it becomes real data within the first ~20 cycles per symbol.
- **The LLM rate-limit budget (`app/llm/rate_limiter.py`, 300/hr, 2000/day) is per OS process, not
  global.** Track 1 and Track 4 run as separate subprocesses (see `docs/local_reliability.md`),
  each with its own in-memory budget — so running both concurrently means up to ~600 calls/hour
  combined in the worst case, not one shared 300/hour ceiling.
- **`mcp_client.get_news`'s type signature expects `list[str]`, but `news_analyst.py` (tracks
  2/3 only, as of the 2026-08-26 Track 4 streamlining) still passes a bare string** — see §3a. Has
  worked in live testing; not independently verified against the MCP server's actual argument
  validation. `track1_validator.py` (§3b) and `track4_validator.py` (§3c) both call it correctly
  (`get_news([symbol])`) since both are new code — the pre-existing bug wasn't fixed in
  `news_analyst.py` itself, only avoided at both new call sites.
- **Track 4's "earnings within 21 days" check (§3c) has no real calendar data behind it** — there
  is no earnings-calendar data source anywhere in this codebase or Alpaca's MCP tools (checked). It
  is necessarily an LLM judgment call from news headlines, same category of limitation as any
  catalyst-based reasoning in this system.
- **Track 1's RSI(14)/VWAP/15m EMA(50)/1m EMA(20) are real computed values (see §2a), not placeholders** — but
  the VWAP is a rolling-window approximation (whatever bars are on hand, not a true
  session-open-anchored VWAP) and the confluence screener has not yet been exercised against a
  real qualifying market cycle in live testing (unit-tested with synthetic bar data — see
  `tests/test_technical_signals_track1.py` — not yet confirmed against a real Alpaca bar stream).
- **Track 1's exit management (`position_monitor.py`'s tiered TP1/TP2/stop/time-stop/EOD sweep)
  is new, automated, order-submitting logic that has not yet been exercised against a real fill**
  — unit-tested indirectly via `track1_alpha_spreads.py`'s output shape, but the sweep itself
  needs a live position to actually validate the partial-close/breakeven-stop/EMA-reversal paths.
- **Track 4's exit management (`position_monitor.py`'s profit-target/stop-loss-defense/assignment/
  called-away sweep) is likewise brand new, automated, order-submitting logic that has never been
  exercised against a real fill** — no mocked unit tests exist for it either (consistent with how
  Track 1's sweep was tested: this codebase's test suite covers pure deterministic functions,
  not logic that requires mocking live Alpaca position state), so it's reviewed and internally
  consistent but unconfirmed against a real assignment/called-away/expiration event.
- **The red-folder news blackout calendar (§0, `app/quant/news_calendar.py`) is a manually curated
  list seeded for one specific week (Aug 28 - Sep 4, 2026), not a live economic-calendar feed.**
  It will silently stop blocking anything useful the moment the hackathon week ends unless someone
  adds that week's real events to `RED_FOLDER_CALENDAR` — there's no automatic rollover, no alert
  if the list goes stale, and no guarantee the seeded week itself is exhaustive (lower-tier
  releases weren't all individually verified). Treat it as a real but incomplete safety net, not
  a substitute for actually watching a live calendar during the hackathon.

---

## 9. One fully worked example (Track 1's new pipeline, hypothetical but realistic values)

Given a bar-close event for SPY where the confluence screener just qualified bullish:

**§2a's `check_track1_confluence()` output** (this is what gates the LLM call — computed before
any LLM node runs):
```python
{"qualified": True, "direction": "up", "trend_regime": "bullish", "price_vs_15m_ema_pct": 0.0091,
 "price_vs_1m_ema_pct": 0.0043, "vwap": 668.40, "price_vs_vwap_pct": 0.0024, "rvol": 2.1, "rsi": 58.3}
```

**`track1_validator.py`'s exact LLM call (§3b) — the only LLM call this cycle, since it qualified:**
- System: *(§3b's system prompt, verbatim)*
- User:
  ```
  Symbol: SPY
  Trigger Direction: up (1-minute confluence confirmed by 15-minute trend)
  Technical Summary:
  - 15m Trend: bullish (price vs 15m 50-EMA: 0.91%)
  - 1m Trend: price vs 1m 20-EMA: 0.43%
  - 1m VWAP offset: 0.24%
  - 1m Relative Volume (RVOL): 2.10x
  - 1m RSI(14): 58.3
  Recent News Headlines:
  Fed signals rate cuts likely in Q4
  S&P 500 hits new high on tech rally
  Retail sales beat expectations
  ```
- Model reply (`json.loads()`'d): `{"verdict": "APPROVE", "sentiment_score": 0.62, "confidence_pct": 78, "take_profit_pct": 65.0, "stop_loss_pct": 18.0, "max_hold_minutes": 90, "thesis": "SPY's 1m breakout above VWAP, confirmed by 2.1x RVOL and an intact 15m uptrend, is corroborated by two bullish macro catalysts (rate-cut signal, strong retail data) — the technical and news cases both point the same direction."}`
- Gate check: `"APPROVE" == "APPROVE"` and `abs(0.62) >= 0.50` and `78 >= 70` → **qualified**.

**`track1_alpha_spreads.propose_order()` — the actual decision, no LLM involved:**
```python
is_call = True   # direction == "up"
liquid_chain = [...]  # option_chain filtered to open_interest >= 500, spread_pct <= 0.05
contract = closest_by_delta(liquid_chain, 0.50, is_call=True, target_dte=2)
# → SPY $670 call, 2 DTE, delta 0.51, ask $2.10 — passes the (1,2) DTE guard and [0.45,0.55] delta band
qty = max(1, int((100_000 * 0.03) // (2.10 * 100)))   # = 14
stop_loss_pct = min(18.0 / 100, 0.20)                  # = 0.18 (LLM's own suggestion, tighter than the ceiling)
```
→ `{"symbol": "SPY", "legs": [{"side": "buy", "ratio_qty": 1, "option_symbol": "SPY...670C", "estimated_cost": 2.10}], "qty": 14, "capital_at_risk": 2940.0, "stop_loss_pct": 0.18, "tp1_pct": 0.50, "tp2_pct": 1.00, "max_hold_minutes": 90, "direction": "up", "thesis": "..."}`
→ `risk_gate.py` checks the 7 conditions in §6 (`$2,940 / $100,000 = 2.94% < 3%` — passes) →
if approved, `execution.py` submits it via `place_option_order(..., qty=14, ...)` exactly as
shown in §7.

From here, `position_monitor.py`'s sweep (see `track1_alpha_spreads.md` §5) checks this trade
every ~15s: closes 7 contracts at +50% (moving the stop to breakeven on the remaining 7), closes
the rest at +100% or a 15m EMA(50) reversal, force-closes everything at 3:45pm ET regardless of
P&L, and stops out at -18% (or breakeven, once the partial has already fired) or after 90 minutes
flat.

---

## 10. One fully worked example (Track 4's new pipeline, hypothetical but realistic values)

Given a poll cycle for XYZ where no shares are currently held (State 0) and IV percentile has
already qualified:

**§2a's `check_wheel_put_regime()` output** (this, plus IV percentile, gates the LLM call —
computed before any LLM node runs):
```python
{"qualified": True, "price_vs_200ema_pct": 0.081, "rsi": 44.2}
```

**§2c's `iv_percentile`**: `62.3` (above the 45 floor).

**`track4_validator.py`'s exact LLM call (§3c) — the only LLM call this cycle, since it qualified:**
- System: *(§3c's system prompt, verbatim)*
- User:
  ```
  Symbol: XYZ
  Wheel leg under consideration: cash-secured put (~21 DTE)
  IV percentile: 62.3
  Daily regime: price vs 200-EMA 8.10%, RSI(14) 44.2
  Recent News Headlines:
  XYZ reaffirms full-year guidance at investor day
  Analyst upgrades XYZ to Buy, cites stable cash flow
  No earnings date scheduled for the next 6 weeks
  ```
- Model reply (`json.loads()`'d): `{"verdict": "APPROVE", "risk_score": 0.15, "earnings_conflict": false, "confidence_pct": 92, "profit_target_pct": 50.0, "thesis": "XYZ has elevated IV (62nd percentile), a healthy pullback (RSI 44, price 8% above its 200-EMA), and no earnings for 6 weeks — premium selling is well-supported here."}`
- Gate check: `"APPROVE" == "APPROVE"` and `not False` and `0.15 <= 0.35` and `92 >= 70` → **qualified**.

**`track4_income_wheel.propose_order()` — the actual decision, no LLM involved:**
```python
holds_shares = False   # State 0
liquid_chain = [...]   # option_chain filtered to open_interest >= 500, spread_pct <= 0.05
leg = closest_by_delta(liquid_chain, -0.30, is_call=False, target_dte=21)
# → XYZ $95 put, 21 DTE, delta -0.28, bid $2.00 — passes the [14,30] DTE guard and [0.25,0.30] delta band
capital_at_risk = 95.0 * 100   # = $9,500 (the collateral, not the $200 premium)
```
→ `{"symbol": "XYZ", "legs": [{"side": "sell", "ratio_qty": 1, "option_symbol": "XYZ...95P", "estimated_cost": 2.00, "strike_price": 95.0}], "capital_at_risk": 9500.0, "stop_loss_pct": 0.20, "wheel_leg": "cash_secured_put", "thesis": "..."}`
→ `risk_gate.py` checks the conditions in §6, using Track 4's 25% wheel cap (not the 3% used by
every other track) — `$9,500 / $100,000 = 9.5% < 25%` — passes → if approved, `execution.py`
submits it via `place_option_order(..., qty=1, ...)` exactly as shown in §7.

From here, `position_monitor.py`'s sweep (see `track4_income_wheel.md` §7) checks this trade every
~15s: buys to close at +50% (the option has decayed to half its collected premium), buys to close
defensively if the cost to close reaches 3× the original premium **and** the daily 200-EMA has
broken, and — the two ways the option can vanish between sweeps — detects assignment (records
`cost_basis = 95.0 - 2.00 = 93.00`, flips `WheelState.holds_shares`) or plain expiration worthless
(closes the trade, keeps the full $200 premium, stays in State 0). If assigned, the next qualifying
cycle sells a covered call floored at that $93.00 cost basis instead.
