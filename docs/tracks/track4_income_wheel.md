# Track 4 — Income & Overlay (The Wheel)

**Status: committed secondary track**, decided alongside Track 1 as primary. Read [00_options_basics.md](00_options_basics.md) first, especially section 3 (buying vs. selling) — this track is a mirror image of Track 1 in a real sense: Track 1 *buys* options and needs the market to move; Track 4 *sells* options and gets paid whether it moves or not, as long as it doesn't move against you by more than the premium collected.

## 1. The structure, in plain English

The Wheel is two rotating steps:

1. **Sell a cash-secured put (CSP)** at ~0.30 delta on a stock you'd be fine owning. You collect the premium immediately. Two outcomes at expiration:
   - Stock stays above the strike → the put expires worthless, you keep the *entire* premium, free and clear. Repeat.
   - Stock drops below the strike → you get **assigned**: you're obligated to buy 100 shares at the strike price (this is why it's "cash-secured" — you need the cash to cover that purchase set aside the whole time).
2. **If assigned, sell a covered call** at ~0.30 delta against those shares. Collect more premium. Two outcomes:
   - Stock stays below the call strike → call expires worthless, you keep the premium *and* the shares. Go back to selling calls, or CSPs if you sell the shares.
   - Stock rallies above the call strike → shares get "called away" (sold at the strike), you keep the premium plus any gain up to that strike. Back to step 1.

You're paid to wait, in either direction — that's the "income" in the name. Delta (~0.30) is chosen deliberately: it's the option-pricing-model's own estimate of roughly a 30% probability of finishing in-the-money, i.e. you're selling something with a ~70% base-rate chance of just expiring worthless in your favor, in exchange for accepting assignment risk that 30% of the time.

## 2. Worked example

XYZ trading at $100, you're comfortable owning it:

- **Sell 1x $95 put, ~0.30 delta, 21 DTE, premium $1.50** → collect $150 immediately, set aside $9,500 cash (100 shares x $95 strike) in case of assignment.
- **If XYZ stays above $95**: put expires worthless. You keep $150. Annualized on the $9,500 secured, that's a real, repeatable yield if you can do this consistently — not a one-off.
- **If XYZ drops to $90 at expiration**: assigned 100 shares at $95 (cost basis effectively $93.50 after the premium). You now sell a covered call, say the $98 strike at ~0.30 delta for $1.20 premium ($120). If XYZ recovers above $98, shares get called away at $98 — you've captured $95→$98 plus $150 + $120 in premium, despite the interim drop to $90. If XYZ stays under $98, you keep the shares and the $120, and sell another call.

The trade-off: your capital is tied up ($9,500 committed per contract), and if the stock craters hard (not just dips) while you're holding assigned shares, you carry that drawdown like any stock owner would — selling calls against it doesn't cap the downside the way Track 1's spread caps its loss. This is real risk, not "guaranteed income" — worth saying plainly to judges rather than glossing over it.

## 3. Entry rule — what the code checks (`backend/app/strategies/track4_income_wheel.py`)

Much simpler branch logic than Track 1 — no sentiment or breakout gate at all, by design (this track doesn't bet on direction):

- Only sells when `iv_percentile >= IV_PERCENTILE_FLOOR` (50 — a concrete reading of "elevated IV"; selling options on a low-IV name collects a thin premium for the same assignment risk).
- If the portfolio already holds shares of the underlying (`portfolio_risk.holds_underlying_shares`, now genuinely reflecting real Alpaca positions — see section 5) → sell a ~0.30-delta covered call, ~21 DTE.
- Otherwise → sell a ~0.30-delta cash-secured put, ~21 DTE.

The 21-day figure is a single point estimate for the brief's 14–30 DTE range — `closest_by_delta()` narrows to the *nearest single expiration* to one target, not a band; a true range filter would need a different (still small) change if this ever needs to be a real 14–30 window instead of a point.

## 4. Why this pairs well with Track 1

Section 3 of [00_options_basics.md](00_options_basics.md) covers the mechanism; concretely for the hackathon week: Track 1 needs a **trend** (breakout + sentiment agreeing) to ever place a trade — in a quiet, range-bound week it could go days without qualifying, which is bad for the "trade frequency/consistency" judging criteria on its own. Track 4 doesn't need a trend at all; it just needs *an* underlying with reasonable premium to sell, which exists on any given day. Running both means the account accumulates trade history regardless of which regime the week actually turns out to be — momentum, or chop.

## 5. Assignment detection

`app/agents/position_monitor.py`'s `sweep_positions()` (the same monitor Track 1 uses for exit management — see its doc, section 5) syncs `holds_underlying_shares` once per full pass: it reads Alpaca's actual position list fresh each sweep (does this symbol currently have a real, positive-quantity `us_equity` position?) and writes the result to a small `WheelState` DB table, rather than trying to detect an assignment *transition*. `quant_engine.py` reads that table (via `portfolio_risk_snapshot(symbol)`) and merges it into `portfolio_risk.holds_underlying_shares` each cycle. This is the fix for the original gap where that field was hardcoded unreachable-`False` — assignment is now a real, live signal.

## 6. Capital sizing note

A cash-secured put's real capital commitment is the **strike price x 100**, not the small premium collected — `propose_order()` sets this explicitly as `capital_at_risk` (leg's `strike_price * 100`) rather than letting `risk_gate.py` estimate it from premium alone, which would understate a CSP's true position size by roughly two orders of magnitude. A covered call's `capital_at_risk` is $0 — the shares are already owned, so selling a call against them commits no *new* capital.

## 7. Status

All gaps from the original scaffold are closed as of 2026-08-24: IV screening, DTE targeting, and assignment detection (sections 3, 5). Not yet exercised: no real order has been accepted by the risk gate in live testing yet (Track 1 test cycles haven't triggered — Track 4 hasn't been run live this session), so the CSP/covered-call order path is built and reviewed but unconfirmed against a real fill.
