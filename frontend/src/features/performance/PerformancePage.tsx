import { Fragment, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import type { AgentDecision, PnlPoint } from "../../api/types";
import { Card, DecisionRow, Section, StatTile } from "../../components/primitives";

const WIDTH = 720;
const HEIGHT = 140;
const MARGIN = { top: 10, right: 12, bottom: 18, left: 56 };
const PLOT_W = WIDTH - MARGIN.left - MARGIN.right;
const PLOT_H = HEIGHT - MARGIN.top - MARGIN.bottom;

function niceTicks(min: number, max: number, count = 4): number[] {
  if (min === max) return [min];
  const step = (max - min) / count;
  return Array.from({ length: count + 1 }, (_, i) => min + step * i);
}

function fmtMoney(v: number): string {
  return `${v >= 0 ? "+" : "-"}$${Math.abs(v).toFixed(2)}`;
}

interface HoverState {
  x: number; // continuous pixel position, unsnapped
  value: number; // linearly interpolated cumulative_pnl at that x
  nearest: PnlPoint;
}

/** Alpaca-style equity chart: "starting capital" (0 realized P&L) sits at
 * the vertical MIDDLE of the plot — a symmetric y-domain around 0, not a
 * domain fit tightly to the data's own min/max — so gains/losses read as
 * movement up/down from a centered baseline. The crosshair tracks the
 * pointer continuously (linear interpolation between the two neighboring
 * points, never snapping to "nearest data point"), so dragging the mouse
 * feels like a smooth pass rather than jumping between discrete stops. */
function PnlChart({ series }: { series: PnlPoint[] }) {
  const [hover, setHover] = useState<HoverState | null>(null);

  const points = useMemo(() => [{ date: "start", cumulative_pnl: 0, trade_pnl: 0, symbol: "" }, ...series], [series]);
  const { yScale, yTicks, linePath, zeroY, lineColor } = useMemo(() => {
    const values = points.map((p) => p.cumulative_pnl);
    const maxAbs = Math.max(...values.map(Math.abs), 10) * 1.15;
    const min = -maxAbs;
    const max = maxAbs;
    const n = points.length;
    const xScale = (i: number) => (n <= 1 ? 0 : (i / (n - 1)) * PLOT_W);
    const yScale = (v: number) => PLOT_H - ((v - min) / (max - min)) * PLOT_H;
    const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"}${xScale(i).toFixed(1)},${yScale(p.cumulative_pnl).toFixed(1)}`).join(" ");
    const last = values[values.length - 1] ?? 0;
    return { xScale, yScale, yTicks: niceTicks(min, max), linePath, zeroY: yScale(0), lineColor: last >= 0 ? "var(--success)" : "var(--error)" };
  }, [points]);

  if (series.length === 0) {
    return <div className="text-xs text-text-secondary py-10 text-center">No closed trades yet — the P&amp;L curve fills in as trades close.</div>;
  }

  const handleMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const relX = ((e.clientX - rect.left) / rect.width) * WIDTH - MARGIN.left;
    const clampedX = Math.min(PLOT_W, Math.max(0, relX));
    const n = points.length;
    const t = (clampedX / PLOT_W) * (n - 1);
    const i0 = Math.min(n - 2, Math.max(0, Math.floor(t)));
    const i1 = i0 + 1;
    const frac = Math.min(1, Math.max(0, t - i0));
    const value = points[i0].cumulative_pnl + (points[i1].cumulative_pnl - points[i0].cumulative_pnl) * frac;
    const nearest = frac < 0.5 ? points[i0] : points[i1];
    setHover({ x: clampedX, value, nearest });
  };

  const tooltipLeft = hover !== null && hover.x > PLOT_W / 2;

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full h-auto touch-none"
        onPointerMove={handleMove}
        onPointerLeave={() => setHover(null)}
        role="img"
        aria-label="Cumulative realized P&L over time, centered on starting capital"
      >
        <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
          {yTicks.map((t, i) => (
            <g key={i}>
              <line x1={0} x2={PLOT_W} y1={yScale(t)} y2={yScale(t)} stroke="var(--border)" strokeWidth={1} />
              <text x={-8} y={yScale(t)} textAnchor="end" dominantBaseline="middle" className="fill-text-secondary font-mono" fontSize={8}>
                {t >= 0 ? "+" : "-"}${Math.abs(t).toFixed(0)}
              </text>
            </g>
          ))}
          <line x1={0} x2={PLOT_W} y1={zeroY} y2={zeroY} stroke="var(--text-disabled)" strokeWidth={1.5} />

          <path d={linePath} fill="none" stroke={lineColor} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />

          {hover !== null && (
            <>
              <line x1={hover.x} x2={hover.x} y1={0} y2={PLOT_H} stroke="var(--text-disabled)" strokeWidth={1} strokeDasharray="3,3" />
              <circle cx={hover.x} cy={yScale(hover.value)} r={5} fill={lineColor} stroke="var(--surface)" strokeWidth={2} />
            </>
          )}
        </g>
      </svg>

      {hover !== null && (
        <div
          className="pointer-events-none absolute top-2 bg-surface border border-border px-2.5 py-1.5 text-xs shadow-lg"
          style={tooltipLeft ? { right: `${((PLOT_W - hover.x) / WIDTH) * 100 + 2}%` } : { left: `${((MARGIN.left + hover.x) / WIDTH) * 100 + 2}%` }}
        >
          <div className="font-mono tabular-nums font-semibold" style={{ color: hover.value >= 0 ? "var(--success)" : "var(--error)" }}>
            {fmtMoney(hover.value)}
          </div>
          {hover.nearest.symbol && <div className="text-text-secondary">near {hover.nearest.symbol} · {new Date(hover.nearest.date).toLocaleString()}</div>}
        </div>
      )}
    </div>
  );
}

/** Mirrors ControlsPage's DecisionDetailModal — moved here since Decision
 * History now lives on this page instead of Controls. */
function DecisionDetailModal({ decision, onClose }: { decision: AgentDecision; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const verdict = decision.risk_approved === true ? "TRADE" : decision.risk_approved === false ? "REJECTED" : "WAIT";
  const verdictColor = decision.risk_approved === true ? "text-success" : decision.risk_approved === false ? "text-error" : "text-signal-wait";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-6" onClick={onClose}>
      <Card square className="w-full max-w-3xl max-h-[85vh] overflow-y-auto p-5 flex flex-col gap-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-baseline gap-2">
            <span className={`text-sm font-semibold tracking-wide ${verdictColor}`}>{verdict}</span>
            <span className="font-mono text-base text-text-primary">{decision.symbol}</span>
          </div>
          <button onClick={onClose} aria-label="Close" className="flex h-7 w-7 items-center justify-center text-text-secondary transition hover:text-text-primary">×</button>
        </div>
        <div className="flex flex-col md:flex-row gap-6">
          <div className="md:w-48 shrink-0 flex flex-col gap-3">
            <div className="text-[11px] font-mono tabular-nums text-text-secondary">
              {new Date(decision.created_at).toLocaleString()}
            </div>
            {decision.sentiment_score != null && (
              <div className="text-xs font-mono tabular-nums">Sentiment <span className="text-text-primary">{decision.sentiment_score.toFixed(2)}</span></div>
            )}
            {decision.risk_rejection_reason && (
              <div className="text-xs text-error">Risk gate: {decision.risk_rejection_reason}</div>
            )}
          </div>
          <div className="flex-1 min-w-0 flex flex-col gap-2">
            <div className="text-[10px] tracking-widest uppercase text-text-secondary">Thesis</div>
            <p className="text-sm leading-relaxed text-text-primary whitespace-pre-wrap">{decision.thesis || "—"}</p>
            {decision.proposed_order && (
              <Fragment>
                <div className="text-[10px] tracking-widest uppercase text-text-secondary mt-2">Proposed Order</div>
                <pre className="text-[11px] font-mono bg-ground border border-border p-2.5 overflow-x-auto">{JSON.stringify(decision.proposed_order, null, 2)}</pre>
              </Fragment>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}

const fmtRatio = (v: number | null) => (v === null ? "—" : v.toFixed(2));

export default function PerformancePage({ onStatusMessage }: { onStatusMessage: (msg: string) => void }) {
  const [track, setTrack] = useState<"track1_alpha_spreads" | "track4_income_wheel" | "track5_momentum_swing">("track1_alpha_spreads");
  const [openDecision, setOpenDecision] = useState<AgentDecision | null>(null);

  const { data: perf } = useQuery({ queryKey: ["performance", track], queryFn: () => api.getPerformance(track), refetchInterval: 10000 });
  const { data: decisions } = useQuery({ queryKey: ["decisions-llm", track], queryFn: () => api.getDecisions(50, track, true), refetchInterval: 5000 });

  const net = perf?.net_realized_pnl ?? 0;

  return (
    <div className="flex flex-col gap-6">
      <Section
        title="Performance"
        action={
          <div className="flex gap-1">
            {(["track1_alpha_spreads", "track4_income_wheel", "track5_momentum_swing"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTrack(t)}
                className={`px-3 py-1 text-[11px] font-semibold tracking-wide uppercase border ${track === t ? "border-accent text-accent" : "border-border text-text-secondary hover:text-text-primary"}`}
              >
                {t === "track1_alpha_spreads" ? "Track 1" : t === "track4_income_wheel" ? "Track 4" : "Track 5"}
              </button>
            ))}
          </div>
        }
      >
        <div className="grid grid-cols-3 md:grid-cols-6 gap-3 mb-5">
          <StatTile square label="Net Realized P&L" value={fmtMoney(net)} tone={net >= 0 ? "success" : "warning"} />
          <StatTile square label="Closed / Open" value={`${perf?.closed_count ?? 0} / ${perf?.open_count ?? 0}`} />
          <StatTile square label="Max Drawdown" value={`$${(perf?.max_drawdown ?? 0).toFixed(2)}`} />
          <StatTile square label="Sharpe Ratio" value={fmtRatio(perf?.sharpe_ratio ?? null)} />
          <StatTile square label="Profit Factor" value={fmtRatio(perf?.profit_factor ?? null)} />
          <StatTile square label="Recovery Factor" value={fmtRatio(perf?.recovery_factor ?? null)} />
        </div>

        <PnlChart series={perf?.cumulative_pnl_series ?? []} />

        {perf?.known_gaps && perf.known_gaps.length > 0 && (
          <p className="mt-3 text-xs text-text-secondary">
            <span className="text-warning font-semibold">Note: </span>{perf.known_gaps.join(" · ")}
          </p>
        )}
      </Section>

      <Section title="Recent Completed Trades">
        {!perf?.recent_completed_trades?.length && <p className="text-xs text-text-secondary py-2">No completed trades yet.</p>}
        <div className="flex flex-col divide-y divide-divider/10">
          {perf?.recent_completed_trades.map((t) => (
            <div key={t.id} className="py-2.5 first:pt-0 last:pb-0 flex items-center justify-between gap-3">
              <div className="flex flex-col gap-0.5 min-w-0">
                <span className="font-mono text-xs font-semibold text-text-primary">{t.symbol}</span>
                <span className="text-[11px] font-mono tabular-nums text-text-secondary truncate">{t.thesis || "—"}</span>
              </div>
              <div className="flex items-center gap-3 shrink-0">
                <span className="text-[11px] font-mono tabular-nums text-text-secondary">{new Date(t.closed_at).toLocaleString()}</span>
                <span className={`text-sm font-mono tabular-nums font-semibold ${t.realized_pnl >= 0 ? "text-success" : "text-error"}`}>
                  {fmtMoney(t.realized_pnl)}
                </span>
              </div>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Decision History">
        <p className="text-xs text-text-secondary mb-2">Showing LLM-validated decisions only — routine per-cycle waits with no qualifying setup are filtered out.</p>
        {!decisions?.length && <p className="text-xs text-text-secondary py-4">No LLM decisions yet.</p>}
        <div className="flex flex-col divide-y divide-divider/10 max-h-105 overflow-y-auto">
          {decisions?.map((d) => <DecisionRow key={d.id} decision={d} onClick={() => { setOpenDecision(d); onStatusMessage(`Viewing decision for ${d.symbol}`); }} />)}
        </div>
      </Section>

      {openDecision && <DecisionDetailModal decision={openDecision} onClose={() => setOpenDecision(null)} />}
    </div>
  );
}
