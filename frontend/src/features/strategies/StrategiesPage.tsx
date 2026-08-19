import { TRACKS, TRACK_LABELS, TRACK_SUMMARY } from "../../api/types";
import { Card, Section } from "../../components/primitives";

// Mirrors the constants at the top of each backend/app/strategies/track*.py
// module — this page is reference documentation, not a live editor; tuning
// these means editing the strategy module directly (see PLAN.md).
const TRACK_PARAMS: Record<(typeof TRACKS)[number], { label: string; value: string }[]> = {
  track1_alpha_spreads: [
    { label: "Long leg delta", value: "0.70Δ" },
    { label: "Short leg delta", value: "0.30Δ" },
    { label: "Target DTE", value: "14 days" },
    { label: "Stop-loss", value: "30% of net debit" },
    { label: "Entry trigger", value: "Breakout + |sentiment| > 0.75" },
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
    { label: "CSP delta", value: "0.30Δ" },
    { label: "Covered call delta", value: "0.30Δ" },
    { label: "Target DTE", value: "14–30 days" },
    { label: "Stop-loss", value: "20% of premium" },
  ],
};

export default function StrategiesPage({ onStatusMessage: _onStatusMessage }: { onStatusMessage: (msg: string) => void }) {
  return (
    <div className="flex flex-col gap-6">
      <Section title="Hackathon Tracks">
        <p className="text-sm text-text-secondary max-w-2xl mb-4">
          All four tracks are implemented and share the same <code className="font-mono text-accent">propose_order(state, thesis)</code> interface
          in <code className="font-mono text-text-primary">backend/app/strategies/</code> — switching which one the live agent runs is a config
          change on the Controls tab, not a rewrite. See PLAN.md section 5 for the current track decision.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {TRACKS.map((t) => (
            <Card key={t} className="p-4 flex flex-col gap-3">
              <h3 className="text-sm font-semibold text-text-primary">{TRACK_LABELS[t]}</h3>
              <p className="text-xs text-text-secondary leading-relaxed">{TRACK_SUMMARY[t].structure}</p>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
                <span className="text-text-disabled uppercase tracking-wide">Regime</span>
                <span className="text-text-primary">{TRACK_SUMMARY[t].regime}</span>
                <span className="text-text-disabled uppercase tracking-wide">Key metric</span>
                <span className="text-text-primary">{TRACK_SUMMARY[t].metric}</span>
              </div>
              <div className="h-px bg-divider/15" />
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
                {TRACK_PARAMS[t].map((p) => (
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
