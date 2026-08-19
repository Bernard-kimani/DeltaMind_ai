import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../../api/client";
import type { BacktestResult } from "../../api/types";
import { TRACKS, TRACK_LABELS } from "../../api/types";
import { Button, Section, Select, StatTile, TextField } from "../../components/primitives";

export default function BacktestPage({ onStatusMessage }: { onStatusMessage: (msg: string) => void }) {
  const [symbol, setSymbol] = useState("SPY");
  const [track, setTrack] = useState<(typeof TRACKS)[number]>("track1_alpha_spreads");
  const [start, setStart] = useState("2026-01-01");
  const [end, setEnd] = useState("2026-06-01");
  const [result, setResult] = useState<BacktestResult | null>(null);

  const runMutation = useMutation({
    mutationFn: () => api.runBacktest({ symbol, track, start, end }),
    onSuccess: (r) => { setResult(r); onStatusMessage(`Backtest complete for ${symbol}`); },
    onError: () => onStatusMessage("Backtest failed — check backend logs"),
  });

  return (
    <div className="flex flex-col gap-6">
      <Section title="Run Backtest">
        <div className="flex flex-wrap items-end gap-3">
          <TextField label="Symbol" mono value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} className="w-28" />
          <Select label="Track" value={track} onChange={(e) => setTrack(e.target.value as typeof track)} className="w-64">
            {TRACKS.map((t) => <option key={t} value={t}>{TRACK_LABELS[t]}</option>)}
          </Select>
          <TextField label="Start" type="date" mono value={start} onChange={(e) => setStart(e.target.value)} />
          <TextField label="End" type="date" mono value={end} onChange={(e) => setEnd(e.target.value)} />
          <Button variant="primary" onClick={() => runMutation.mutate()} disabled={runMutation.isPending}>
            {runMutation.isPending ? "Running…" : "Run Backtest"}
          </Button>
        </div>
        <p className="mt-3 text-xs text-text-secondary max-w-xl">
          The backtest engine (<code className="font-mono text-accent">backend/app/backtest/engine.py</code>) is currently a stub pending
          confirmation of historical options-chain-with-Greeks access on the Alpaca data plan — see PLAN.md section 10. Running it now
          will return zeroed results without erroring.
        </p>
      </Section>

      {result && (
        <Section title="Results">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatTile label="Total P&L" value={`$${result.total_pnl.toFixed(2)}`} tone={result.total_pnl >= 0 ? "success" : "warning"} />
            <StatTile label="Win Rate" value={`${(result.win_rate * 100).toFixed(1)}%`} />
            <StatTile label="Max Drawdown" value={`${(result.max_drawdown_pct * 100).toFixed(1)}%`} />
            <StatTile label="Trades" value={String(result.trades.length)} />
          </div>
        </Section>
      )}
    </div>
  );
}
