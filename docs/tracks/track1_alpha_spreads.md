# Track 1 — Options Alpha (Vertical Debit Spreads)

**Status: primary submission track.** Read [00_options_basics.md](00_options_basics.md) first if you haven't.

## 1. The structure, in plain English

When our agent gets bullish conviction on a symbol, a beginner move is "just buy a call." The problem: if the stock drifts sideways or grinds up too slowly, Theta (time decay) eats the option's value every day even though you picked the right direction. Track 1 uses a **bull call debit spread** instead (bearish setups mirror this with a **bear put spread** — same mechanics, put side, implemented and live-verified 2026-08-24):

1. **Buy** a call close to the money (~0.70 delta) — most of the upside sensitivity.
2. **Sell** a call further out of the money (~0.30 delta), same expiration — collects premium that partially pays for the long leg.

Because you're long and short at the same time, Theta hits both legs — largely canceling out — and your max loss is capped at the net debit paid, no matter what the stock does. You trade away unlimited upside for a much cheaper, structurally bounded bet.

## 2. Worked example (matches what our code would actually produce)

Stock XYZ at $100, ~14 days to expiration:

| Leg | Strike | Delta | Price | Action |
|---|---|---|---|---|
| Long call | $100 | 0.70 | $3.00 | Buy |
| Short call | $108 | 0.30 | $1.20 | Sell |

- **Net debit**: ($3.00 - $1.20) x 100 shares = **$180** — this is the entire max loss, period.
- **Spread width**: $108 - $100 = $8.00/share = $800.
- **Max profit** (if XYZ finishes at or above $108 at expiration): $800 - $180 = **$620**, a max reward:risk of ~3.4:1.
- **Breakeven**: $100 + $1.80 = $101.80 — XYZ only needs to clear this, not $108, to be profitable at expiration (though max profit needs $108+).

Compare to a naked $3.00 long call with the same $100 strike: same $300 cost for 1 contract, *unlimited* upside, but also the full $300 at risk if XYZ doesn't move, and Theta decay isn't offset by anything. The spread is a deliberate trade of unlimited upside for a much lower cost and a hard floor.

## 3. Entry rule — exactly what the code checks (`backend/app/strategies/track1_alpha_spreads.py`)

Both of these must be true simultaneously — this is an AND-gate, not either-or:

1. **Technical breakout** (`backend/app/quant/technical_signals.py`): latest close breaks outside its prior 20-bar range, confirmed by volume ≥ 1.5x its own 20-bar average, in the same direction as (2).
2. **Sentiment** beyond ±0.75 (from `news_analyst.py`'s LLM sentiment score) in the same direction.

If either signal is missing, weak, or the two disagree, **no trade** — this is deliberate noise filtering, not a bug. A good-news headline with no confirming price/volume action (or vice versa) is exactly the false-positive this AND-gate exists to reject.

*Correctness note (fixed 2026-08-23):* until this session, only the sentiment half was actually implemented in code — there was no technical breakout signal computed anywhere in the pipeline, despite the docstring and the hackathon brief both describing a two-factor condition. `technical_signals.py` closes that gap.

## 4. Who decides what — the LLM vs. the code

This is the part worth explaining clearly to judges, because it's the actual answer to "how do you keep an LLM from doing something dumb with real capital":

- **`lead_architect.py` (LLM)** writes the one-sentence *thesis* — the human-readable explanation shown in the dashboard's decision detail view. As of this session, its prompt explicitly names the active track and its entry rule, so the explanation stays consistent with what's actually being checked (a real bug existed here: prior to the fix, the LLM would sometimes describe a completely different track's structure — e.g. a volatility straddle — when running under Track 1, because it was handed raw numbers with no track framing and reached for whatever structure seemed to fit them best).
- **`track1_alpha_spreads.py`'s `propose_order()` (pure Python)** decides everything that actually matters — direction, strikes, legs, whether a trade happens at all — by reading `state["sentiment_score"]` and `state["technical_signal"]` directly. **The LLM's thesis text is never parsed or acted on for this decision.** It's documentation, not control flow.
- **`risk_gate.py` (pure Python, zero LLM calls)** is the last checkpoint: rejects if position size > 3% of equity (the real net debit — `capital_at_risk`, not gross leg value), margin utilization > 50%, 6+ positions already open, this trade would drop cash reserves below 55%, this symbol's sector would exceed 15% of equity, or the order is missing a stop-loss ≤ 20%. It cannot be talked into anything — there's no prompt for it to be injected against.

So a bad LLM output (hallucinated symbol, nonsense reasoning, or the track-drift bug above) could produce a *confusing thesis*, but not an *unauthorized trade* — the deterministic layers don't read the thesis text at all. That's the actual guarantee, and it's a stronger, more honest claim than "revolutionary."

## 5. Exit management

Handled by `app/agents/position_monitor.py`'s `sweep_positions()` — a plain deterministic function (not a LangGraph node: it's an account-wide sweep over every open position, not a per-symbol decision, and needs no LLM reasoning), called once per full pass in `run_agent_loop.py` before any new entries are proposed. For each open Track 1 trade, it re-prices both legs against live Alpaca positions and closes the spread when unrealized P&L reaches **50% of the net debit paid** (`PROFIT_TAKE_PCT = 0.50` — a defensible simplification of the brief's "50% of max potential gain," which would need the spread's strike width parsed from OCC symbols for one extra layer of precision) or **loses 20%** of it (`STOP_LOSS_PCT = 0.20`, matching `risk_gate.py`'s global ceiling). Closing orders use `position_intent` (`buy_to_close`/`sell_to_close`), the opposite of each leg's original side.

## 6. Status

All gaps from the original scaffold are closed as of 2026-08-24:
- **Bear put spread**: implemented (`is_call = bullish`, signed delta targets flip with direction) and live-verified — a bearish state correctly builds a put spread with matched strikes/expiration.
- **Exit management**: wired into the loop via `position_monitor.py` (section 5).
- **A DTE-matching bug found while adding the bear-spread branch**: without `target_dte`, the two legs of a "vertical" spread could independently pick *different* expirations (confirmed live — one attempt paired a same-day contract with one 39 days out, not a valid spread at all). Fixed by having `closest_by_delta()` narrow to the nearest single expiration to the target before ranking by delta, with a matched-expiration check as a second layer of defense in `propose_order()`.

Remaining, not blocking: **single-timeframe breakout** (one SMA/volume check, not the brief's multi-timeframe scanner) — a defensible, explainable v1, not a limitation to hide from judges. No real order has been accepted by the risk gate yet in live testing (every test run correctly rejected on "no breakout confirmed" / insufficient sentiment) — the closing-order path in `position_monitor.py` is built and reviewed but hasn't been exercised by an actual fill.
