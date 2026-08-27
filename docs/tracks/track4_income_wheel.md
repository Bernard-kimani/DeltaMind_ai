# Track 4 — Income & Overlay (The Wheel)

**Status: committed secondary track**, decided alongside Track 1 as primary. Read [00_options_basics.md](00_options_basics.md) first, especially section 3 (buying vs. selling) — this track is a mirror image of Track 1 in a real sense: Track 1 *buys* options and needs the market to move; Track 4 *sells* options and gets paid whether it moves or not, as long as it doesn't move against you by more than the premium collected.

**2026-08-26 streamlining**: this track was rebuilt from a user-supplied engineering spec — the
prior scaffold opened CSP/covered-call positions but never closed them, had no technical filter at
all, and its core IV metric was a permanent hardcoded placeholder. This version closes all three
gaps, plus a blocking bug found while reviewing the spec (see §8). Section history preserved
below in §9. Everything else describes the *current* strategy.

## 1. The structure, in plain English

The Wheel is two rotating steps:

1. **Sell a cash-secured put (CSP)** at ~0.25–0.30 delta on a stock you'd be fine owning, when implied volatility is elevated *and* the daily chart shows a healthy pullback within an uptrend (not a falling knife). You collect the premium immediately. Two outcomes at expiration:
   - Stock stays above the strike → the put expires worthless, you keep the *entire* premium, free and clear. Repeat.
   - Stock drops below the strike → you get **assigned**: you're obligated to buy 100 shares at the strike price (this is why it's "cash-secured" — you need the cash to cover that purchase set aside the whole time). Cost basis is recorded as `strike - premium collected`.
2. **If assigned, sell a covered call** at ~0.25–0.30 delta against those shares, floored at or above your cost basis so assignment can never turn into a guaranteed loss. Collect more premium. Two outcomes:
   - Stock stays below the call strike → call expires worthless, you keep the premium *and* the shares. Go back to selling calls.
   - Stock rallies above the call strike → shares get "called away" (sold at the strike), you keep the premium plus any gain up to that strike. Back to step 1.

You're paid to wait, in either direction — that's the "income" in the name.

## 2. Worked example

XYZ trading at $100, you're comfortable owning it, IV percentile is elevated (62nd) and the daily regime check qualifies (price 8% above the 200-EMA, RSI 44):

- **Sell 1x $95 put, ~0.28 delta, 21 DTE, premium $2.00** → collect $200 immediately, set aside $9,500 cash (100 shares x $95 strike) in case of assignment.
- **If XYZ stays above $95**: put expires worthless. You keep $200.
- **If XYZ drops to $90 at expiration**: assigned 100 shares at $95 (cost basis $93.00 after the premium). You now sell a covered call, floored at or above $93 — say the $96 strike at ~0.28 delta for $1.80 premium ($180). If XYZ recovers above $96, shares get called away at $96 — you've captured $95→$96 plus $200 + $180 in premium, despite the interim drop to $90. If XYZ stays under $96, you keep the shares and the $180, and sell another call.

The trade-off: your capital is tied up ($9,500 committed per contract), and if the stock craters hard (not just dips) while you're holding assigned shares, you carry that drawdown like any stock owner would — selling calls against it doesn't cap the downside the way Track 1's long option caps its loss. This is real risk, not "guaranteed income" — worth saying plainly to judges rather than glossing over it.

## 3. Entry rule — what the code checks (`backend/app/strategies/track4_income_wheel.py`)

**Gate 0 — red-folder news blackout** (`app/agents/news_blackout_gate.py`, checked before
anything else, for every symbol, every cycle, every track — same gate Track 1 uses): no new entry
within 5 minutes before/after a scheduled high-impact macro release, per
`app/quant/news_calendar.py`. See `docs/tracks/track1_alpha_spreads.md` §3 / `technical_pipeline.md`
§0 for the full mechanics — this is deterministic, applies identically here, and isn't
duplicated per-track logic.

Two further independent gates must both pass, in this order, so the (only) LLM call never fires on a
cycle that wouldn't qualify anyway — same early-exit cost principle as Track 1:

**Gate 1 — deterministic screen** (`quant_engine.py`, before any LLM node runs — see `graph.py`'s conditional edge):

| Check | Applies to | Threshold |
|---|---|---|
| IV percentile | Both legs | ≥ 45 (elevated implied volatility, worth collecting) |
| Daily 200-EMA/RSI regime | **Cash-secured put only** | price > 200-day EMA AND RSI(14) in [35, 55] — avoid selling puts into a structural downtrend |
| Cost-basis floor | **Covered call only** | candidate strike ≥ recorded cost basis (checked at contract-selection time, not this gate) |

A fresh cash-secured put needs both IV percentile *and* the regime check; a covered call (shares
already held) only needs IV percentile — the regime check doesn't apply once you already own the
shares, per the spec.

**Gate 2 — LLM risk-officer validator** (`app/agents/track4_validator.py`, reached only when gate 1 passes): one merged LLM call returning a verdict, risk score, earnings-conflict flag, confidence, and profit-target guidance in one schema (see [technical_pipeline.md](technical_pipeline.md) §3c for the exact prompt). The hardcoded gate: `verdict == "APPROVE" AND NOT earnings_conflict AND risk_score <= 0.35 AND confidence_pct >= 70`. Not runtime-tunable via Controls, same precedent as Track 1.

If either gate fails, `propose_order()` is never called — the cycle logs a WAIT/REJECTED row with no new UI work needed, same as any other track.

**Contract selection** (once both gates pass): pre-filtered to `open_interest >= 500` and `spread_pct <= 0.05` (Track 4 previously had no liquidity filter at contract-selection time — only a one-time check when a symbol joins the watchlist). After `closest_by_delta()` picks the nearest ~0.30-delta contract at the nearest ~21-day expiration, two explicit guards reject the pick rather than trade a degenerate contract: DTE not in `[14, 30]`, or actual delta not in `[0.25, 0.30]`.

## 4. Who decides what — the LLM vs. the code

Same split as Track 1 (see its doc, section 4):

- **`track4_validator.py` (LLM)** validates whether real news/solvency signals support selling premium here right now — a risk-officer sign-off, not a directional call — and writes the thesis. It also proposes `profit_target_pct` as *guidance* — the deterministic exit layer (§7) uses its own fixed 50% rule regardless.
- **`track4_income_wheel.py`'s `propose_order()` (pure Python)** decides everything that actually matters — CSP vs. covered call, strike (floored at cost basis for calls), DTE, delta band, liquidity — from `state["iv_percentile"]`, `state["technical_signal"]`, and `state["portfolio_risk"]`. **The LLM's thesis text is never parsed or acted on for this decision.**
- **`risk_gate.py` (pure Python, zero LLM calls)** — same checks as every other track, except the position-size cap: Track 4 uses `max_wheel_collateral_pct` (25%), not `max_position_pct` (3%) — see §8 for why.

## 5. Why this pairs well with Track 1

Section 3 of [00_options_basics.md](00_options_basics.md) covers the mechanism; concretely for the hackathon week: Track 1 needs a **trend** (multi-timeframe confluence) to ever place a trade — in a quiet, range-bound week it could go days without qualifying. Track 4 doesn't need a trend at all; it just needs *an* underlying with elevated premium and a non-broken chart, which exists on any given day. Running both means the account accumulates trade history regardless of which regime the week actually turns out to be — momentum, or chop.

## 6. Real IV percentile history

`app/quant/iv_percentile.py`'s `compute_iv_percentile()` now records every observed ATM IV into a
new `iv_observations` table (`record_iv_observation`), for every track's every cycle unconditionally
— replacing what used to be a permanent hardcoded `(0.10, 0.90)` 52-week range. `get_iv_52wk_range()`
computes the real min/max from the last 365 days of observations once at least 20 exist for a
symbol; below that, it still falls back to the old placeholder (documented, not silently faked).
Because this runs for every track, Track 1's much higher cycle frequency on shared watchlist
symbols (SPY/QQQ/mega-caps) passively accelerates how fast Track 4's range becomes real data for
those same names.

## 7. Exit management (`app/agents/position_monitor.py`)

Previously Track 4 only ever synced a `holds_underlying_shares` boolean — it never closed
anything. As of this streamlining, a full sweep runs every ~15s cadence:

1. **Profit target (the 50% rule)** — if the sold option's value has decayed to 50% of the
   collected premium, buy-to-close immediately. Fixed deterministic constant
   (`WHEEL_PROFIT_TARGET_PCT = 0.50`), not derived from the LLM's `profit_target_pct` suggestion.
2. **Stop-loss defense** — if the cost to close has risen to 3× the original premium collected
   **and** the daily 200-EMA regime check (§3) now shows broken support, buy-to-close defensively.
   A distinct mechanism from the order-level `stop_loss_pct` field `risk_gate.py` checks at entry
   (that's a static declared ceiling; this is a dynamic mid-life defense trigger).
3. **Assignment detection** — if a CSP's option position vanishes from Alpaca's list *and* the
   account now holds shares of that symbol it didn't hold last sweep, the put was assigned:
   records `cost_basis = strike - premium`, flips `WheelState.holds_shares`.
4. **Called-away detection** — if a covered call's option position vanishes *and* the account no
   longer holds the shares, they were called away: realizes the premium plus the capital gain
   (`(strike - cost_basis) * 100`), clears `WheelState` back to State 0.
5. **Expired worthless** — the most common outcome (per the spec's own 70-85% win-rate estimate):
   if neither of the above applies, the option simply expired worthless — closes the trade,
   keeps 100% of the premium, and the wheel stays in whichever state it was already in.

## 8. Capital sizing — the blocking bug this streamlining found and fixed

A cash-secured put's real capital commitment is the **strike price x 100**, not the small premium
collected — `propose_order()` sets this explicitly as `capital_at_risk` rather than letting
`risk_gate.py` estimate it from premium alone. **Before this streamlining, `risk_gate.py` applied
the same 3% cap (`max_position_pct`, calibrated for Track 1's premium-based risk) to this
collateral — and direct inspection found that blocked every single symbol in the watchlist,
including the cheapest** (XLF at $58/share is already 5.8% collateral on a $100k account; SPY at
$765/share is 76.5%). Track 4 as originally wired could not have placed a single trade.

Fixed with a new, separate `max_wheel_collateral_pct` setting (25% per position) — collateral
posted for a CSP isn't the same thing as capital-at-risk, so it doesn't belong under the same cap
as every other track's premium/net-debit exposure. The user's own choice, given that even 25% of
$100k doesn't comfortably fit SPY/QQQ-class collateral: **fund the shared Alpaca paper account to
a larger balance** (their target: ~$500k) rather than building a separate cheaper watchlist or a
genuinely separate per-track brokerage account — the latter would also require threading per-track
credentials through `rest_client.py`'s cached clients and `mcp_client.py`'s session launch, out of
scope for the remaining hackathon-prep time. Also surfaced, not fixed: Track 1 and Track 4
currently share one Alpaca account entirely (`portfolio_risk_snapshot()` has zero track
filtering), so `max_open_positions`/cash-reserve/margin checks are combined across both tracks,
not per-track.

## 9. History (superseded by this streamlining)

The original scaffold (IV percentile floor of 50, no technical regime filter, no exit management
beyond a `holds_underlying_shares` boolean sync, hardcoded `(0.10, 0.90)` IV range) shipped
2026-08-24 and is fully superseded above. Its DTE-targeting and assignment-detection groundwork
(reading Alpaca's own live position list rather than guessing) carries forward unchanged into
this streamlining.

## 10. Status

All gaps identified in this streamlining are closed as of 2026-08-26: real technical regime gate,
real exit management (profit-target/stop-loss-defense/assignment/called-away/expired-worthless),
real self-bootstrapping IV history, the merged risk-officer LLM validator, and the wheel-specific
collateral cap that actually lets trades clear `risk_gate`. Not yet exercised: no real order has
been accepted by the risk gate in live testing, and the new exit-management sweep has no mocked
unit tests (consistent with how this test suite covers pure deterministic functions, not logic
that requires mocking live Alpaca position state) — reviewed and internally consistent, but
unconfirmed against a real fill, assignment, or expiration event.
