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
          The backtest engine replays real historical bars through each track's deterministic (non-LLM) entry gate and reports how often
          it would have qualified. It does not simulate fills/P&amp;L — no historical options-chain/Greeks/IV data source is available,
          so those fields stay at zero. See "Known gaps" below for what this run does and doesn't cover.
        </p>
      </Section>

      {result && (
        <Section title="Results">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatTile label="Bars Evaluated" value={String(result.total_bars_evaluated ?? 0)} />
            <StatTile label="Qualified" value={String(result.qualified_count ?? 0)} />
            <StatTile
              label="Qualification Rate"
              value={`${(((result.qualification_rate ?? 0)) * 100).toFixed(2)}%`}
              tone={(result.qualification_rate ?? 0) > 0 ? "success" : "warning"}
            />
            <StatTile label="Trades Simulated" value={String(result.trades.length)} />
          </div>

          {result.known_gaps && result.known_gaps.length > 0 && (
            <div className="mt-4 rounded border border-warning/40 bg-warning/5 p-3 text-xs text-text-secondary">
              <p className="mb-1 font-semibold text-warning">Known gaps</p>
              <ul className="list-disc pl-4 space-y-1">
                {result.known_gaps.map((gap, i) => <li key={i}>{gap}</li>)}
              </ul>
            </div>
          )}

          {result.qualification_by_month && Object.keys(result.qualification_by_month).length > 0 && (
            <div className="mt-4">
              <p className="mb-2 text-xs font-semibold text-text-secondary">Qualification by month</p>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-text-secondary">
                      <th className="pr-4 py-1">Month</th>
                      <th className="pr-4 py-1">Evaluated</th>
                      <th className="pr-4 py-1">Qualified</th>
                      <th className="pr-4 py-1">Rate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(result.qualification_by_month).sort(([a], [b]) => a.localeCompare(b)).map(([month, stats]) => (
                      <tr key={month} className="border-t border-border/40">
                        <td className="pr-4 py-1 font-mono">{month}</td>
                        <td className="pr-4 py-1">{stats.evaluated}</td>
                        <td className="pr-4 py-1">{stats.qualified}</td>
                        <td className="pr-4 py-1">{stats.evaluated ? `${((stats.qualified / stats.evaluated) * 100).toFixed(2)}%` : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {result.qualifying_events && result.qualifying_events.length > 0 && (
            <div className="mt-4">
              <p className="mb-2 text-xs font-semibold text-text-secondary">
                Sample qualifying events (showing up to {result.qualifying_events.length})
              </p>
              <div className="max-h-64 overflow-y-auto overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-text-secondary">
                      <th className="pr-4 py-1">Timestamp</th>
                      <th className="pr-4 py-1">Symbol</th>
                      <th className="pr-4 py-1">Direction</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.qualifying_events.slice(0, 100).map((ev, i) => (
                      <tr key={i} className="border-t border-border/40">
                        <td className="pr-4 py-1 font-mono">{ev.timestamp}</td>
                        <td className="pr-4 py-1 font-mono">{ev.symbol}</td>
                        <td className="pr-4 py-1">{ev.direction ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </Section>
      )}
    </div>
  );
}
