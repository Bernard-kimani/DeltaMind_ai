# Options Basics — the primer both track docs build on

This is the shared foundation for [track1_alpha_spreads.md](track1_alpha_spreads.md) and [track4_income_wheel.md](track4_income_wheel.md). Read this first — it fixes a couple of mathematical nuances that are easy to get wrong (and that a judge who trades options *will* notice if we get them wrong on stage).

## 1. What an option actually is

A **call option** is the right (not the obligation) to *buy* 100 shares of a stock at a fixed price (the **strike**) on or before a fixed date (**expiration**). A **put option** is the same right, but to *sell*.

The house-deposit analogy is a fine starting intuition: paying a small non-refundable fee to lock in today's price for a few days, walking away if the deal turns out bad. Where it needs sharpening is the *shape* of the payoff — an option isn't "buy the house or don't," it's "the contract itself has a market price that moves every day before you ever decide to exercise it," and that price is made of two components that get conflated constantly:

- **Intrinsic value** — the payoff if exercised *right now*. For a call: `max(stock_price - strike, 0)`. For a put: `max(strike - stock_price, 0)`.
- **Extrinsic value** (a.k.a. time value) — everything else: compensation for the time remaining and the volatility of the underlying. This is what **Theta (Θ)** decays every single day, and it's largest when the stock is near the strike and expiration is far away.

An option's actual market price = intrinsic + extrinsic. This matters because of the next point.

## 2. The multiplier, and the mistake in the "$2 → $10" example

You had the multiplier right: 1 contract = 100 shares, so a $2.00 quote costs $200 to buy. Where the video's math oversimplifies: **it assumes the option's value at the moment of the price move equals pure intrinsic value.** That's only exactly true *at expiration* (or so deep in-the-money that extrinsic value is negligible). Before expiration, an at-the-money option doesn't move dollar-for-dollar with the stock — its immediate sensitivity is given by **Delta (Δ)**, which for a stock exactly at the strike is roughly 0.5, not 1.0.

So: stock $100 → $110, a $2.00 at-the-money call with weeks left to run would *not* suddenly be worth exactly $10.00. It'd be worth roughly (intrinsic $10) + (whatever extrinsic value survives) minus some Theta decay — plausibly $10.50–$12.00 depending on time-to-expiration and implied volatility, or it could even be a bit less than $10 combined if you're very close to expiration and volatility collapsed. The "$800 profit, 400% ROI" figure in the pasted conversation is the **correct end-state number if held to expiration** — it's a legitimate teaching example, just worth labeling as "at expiration," not "the instant the stock moves." This is exactly what our `app/quant/greeks.py` module computes for real (Δ, Γ, Θ, Vega, ρ) instead of assuming intrinsic-only math — the whole point of having a deterministic Greeks engine is to not get this wrong live.

## 3. Buying options vs. selling options — the fork that splits our two tracks

This is the most important distinction in the whole project, because **Track 1 buys options and Track 4 sells them** — structurally opposite trades with opposite relationships to time:

| | Buying (long premium) | Selling (short premium) |
|---|---|---|
| You pay/receive | Pay premium upfront | Collect premium upfront |
| Theta (time decay) | Works **against** you | Works **for** you |
| Max loss | Capped at premium paid | Can be large (a naked short) — **which is why Track 4 only sells *cash-secured* puts and *covered* calls**, never naked |
| Needs | A move (direction or volatility) before expiration | Time passing, or the stock staying roughly put |
| Our track | Track 1 (debit spreads) | Track 4 (the Wheel) |

Neither is "better" — they profit from different things, which is exactly why running both together (section 5 of PLAN.md) is a genuinely sound idea, not just hedge-your-bets diversification: Track 1 needs a market that *moves*; Track 4 needs a market that mostly *doesn't*, or moves slowly. One week is unlikely to be neither.

## 4. Spreads: why combine two legs instead of one

Buying a single call is a bet resolved by "did the stock move enough, fast enough, to beat Theta." A **vertical debit spread** (Track 1's structure) buys one option and *simultaneously sells* a further-out-of-the-money option in the same direction:

- The premium collected from the short leg **partially offsets** the cost of the long leg — cheaper entry (how much cheaper depends on strike width and implied volatility, not a fixed 50–70%; that figure from the pasted conversation is a rough real-world range, not a rule).
- Max loss is capped at the **net debit paid**, full stop, no matter how far the stock moves against you.
- Max profit is capped too, at `(strike width - net debit) x 100 x contracts` — you give up the unlimited upside of a naked call in exchange for a much lower cost and a hard floor on the loss.

See [track1_alpha_spreads.md](track1_alpha_spreads.md) section 2 for the exact worked numbers our code would actually produce.

## 5. On calling this "revolutionary" and "bound to be profitable"

Worth being direct about this one, since it's the kind of phrasing that reads as a red flag to anyone who's actually traded — including a judge with options experience. **No structure is "bound to be" profitable; a debit spread caps loss per trade, it does not guarantee a profitable week.** LLM-reasoning-plus-deterministic-risk-gate multi-agent trading systems are also an active, known area, not a first-of-its-kind invention — plenty of quant shops and open-source projects do versions of this. What *is* true, and is a perfectly strong story for judges without overclaiming:

- The **separation of concerns** is real and demonstrable: the LLM only ever writes the *explanation*, never decides the trade — `propose_order()` in each strategy module is 100% deterministic Python a judge can read start to finish (see PLAN.md section 3, and the architectural note at the top of `lead_architect.py`).
- The **risk bound is real and enforced in code** (the risk gate, section 9 of PLAN.md), not a marketing claim.
- The **dual-track regime coverage** (section 3 above) is a genuine, explainable design decision, not hand-waving.

That's a strong, honest pitch. Lead with it instead of "revolutionary."
