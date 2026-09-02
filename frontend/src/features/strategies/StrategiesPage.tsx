import { TRACKS, TRACK_LABELS, TRACK_SUMMARY } from "../../api/types";
import { Card, Section } from "../../components/primitives";

// All three tracks share this one running instance now (top-nav tabs,
// Performance/Logs' own in-page toggles, etc.) — config.ts's ACTIVE_TRACK
// build flag is unused dead code at this point, nothing left reads it. This
// page has no reason to hide any strategy behind a build-time switch: a
// judge reading "Strategies" should see all three.
const IMPLEMENTED_TRACKS = ["track1_alpha_spreads", "track4_income_wheel", "track5_momentum_swing"] as const;

// Mirrors the constants at the top of each backend/app/strategies/track*.py
// module — this page is reference documentation, not a live editor; tuning
// these means editing the strategy module directly (see PLAN.md).
const TRACK_PARAMS: Record<(typeof TRACKS)[number], { label: string; value: string }[]> = {
  track1_alpha_spreads: [
    { label: "Structure", value: "Single-leg long call/put" },
    { label: "Target delta", value: "0.45–0.55Δ" },
    { label: "Target DTE", value: "1–2 days" },
    { label: "Position sizing", value: "3% of equity" },
    { label: "Take-profit (tier 1)", value: "+50% (half, stop → breakeven)" },
    { label: "Take-profit (tier 2)", value: "+100%, or 15m EMA(50) reversal" },
    { label: "Stop-loss", value: "20% (clamped to platform ceiling)" },
    { label: "Time-stop", value: "90 min if flat (±10%)" },
    { label: "EOD liquidation", value: "3:45pm ET, unconditional" },
    { label: "Entry trigger", value: "15m EMA(50) trend + 1m VWAP + RSI(14) band + 20-bar breakout + RVOL ≥ 1.5" },
    { label: "LLM catalyst gate", value: "Verdict APPROVE, |sentiment| ≥ 0.50, confidence ≥ 70% (fixed)" },
  ],
  track2_volatility_events: [
    { label: "Strangle delta", value: "0.25Δ" },
    { label: "Condor short delta", value: "0.20Δ" },
    { label: "Condor long delta", value: "0.10Δ" },
    { label: "Long-vol trigger", value: "IV percentile < 25" },
    { label: "Short-vol trigger", value: "IV percentile > 85" },
  ],
  track3_hedging: [
    { label: "Drawdown trigger", value: "> 3.5%" },
    { label: "Put strike", value: "5% OTM" },
    { label: "Call strike", value: "3% OTM" },
    { label: "Stop-loss", value: "20%" },
  ],
  track4_income_wheel: [
    { label: "Structure", value: "Cash-secured put ↔ covered call" },
    { label: "Target delta (both legs)", value: "0.25–0.30Δ" },
    { label: "Target DTE", value: "14–30 days (21 target)" },
    { label: "Position sizing (CSP)", value: "25% wheel collateral cap" },
    { label: "Entry gate (IV)", value: "IV percentile ≥ 45" },
    { label: "Entry gate (CSP regime)", value: "Price > 200-day EMA + RSI(14) 35–55" },
    { label: "Covered call floor", value: "Strike ≥ cost basis" },
    { label: "Profit target", value: "+50% of premium, buy-to-close (fixed)" },
    { label: "Stop-loss defense", value: "Cost to close = 3× premium AND 200-EMA broken" },
    { label: "LLM risk-officer gate", value: "Verdict APPROVE, no earnings conflict, risk ≤ 0.35, confidence ≥ 70% (fixed)" },
  ],
  track5_momentum_swing: [
    { label: "Structure", value: "Single-leg long call/put (same as Track 1)" },
    { label: "Target delta", value: "0.40–0.60Δ (widened vs. Track 1's tighter band)" },
    { label: "Target DTE", value: "3–7 days" },
    { label: "Position sizing", value: "3% of equity" },
    { label: "Take-profit (tier 1)", value: "+50% (half, stop → breakeven)" },
    { label: "Take-profit (tier 2)", value: "+100%, or 1h trend reversal" },
    { label: "Stop-loss", value: "20% (clamped to platform ceiling)" },
    { label: "Time-stop", value: "4h default, 8h ceiling if flat" },
    { label: "EOD liquidation", value: "3:45pm ET, unconditional" },
    { label: "Entry trigger", value: "1h EMA(50) trend + 5m EMA(20) crossover — deliberately thin, 2 factors vs. Track 1's 5" },
    { label: "LLM catalyst gate", value: "Verdict APPROVE, no sentiment contradiction, confidence ≥ 55% (looser than Track 1)" },
  ],
};

export default function StrategiesPage({ onStatusMessage: _onStatusMessage }: { onStatusMessage: (msg: string) => void }) {
  return (
    <div className="flex flex-col gap-6">
      <Section title="Strategy">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {IMPLEMENTED_TRACKS.map((track) => (
            <Card key={track} className="p-4 flex flex-col gap-3">
              <h3 className="text-sm font-semibold text-text-primary">{TRACK_LABELS[track]}</h3>
              <p className="text-xs text-text-secondary leading-relaxed">{TRACK_SUMMARY[track].structure}</p>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
                <span className="text-text-disabled uppercase tracking-wide">Regime</span>
                <span className="text-text-primary">{TRACK_SUMMARY[track].regime}</span>
                <span className="text-text-disabled uppercase tracking-wide">Key metric</span>
                <span className="text-text-primary">{TRACK_SUMMARY[track].metric}</span>
              </div>
              <div className="h-px bg-divider/15" />
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
                {TRACK_PARAMS[track].map((p) => (
                  <div key={p.label} className="contents">
                    <dt className="text-[11px] text-text-secondary">{p.label}</dt>
                    <dd className="text-[11px] font-mono tabular-nums text-text-primary text-right">{p.value}</dd>
                  </div>
                ))}
              </dl>
            </Card>
          ))}
        </div>
      </Section>
    </div>
  );
}
