import { Fragment, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import type { BacktestResult } from "../../api/types";
import { TRACKS, TRACK_LABELS } from "../../api/types";
import { Button, Section, Select, TextField } from "../../components/primitives";
import { SymbolPicker } from "../controls/SymbolPicker";

type RunState = "pending" | "done" | "error";

function RateMeter({ rate, maxRate }: { rate: number; maxRate: number }) {
  const pct = maxRate > 0 ? Math.max((rate / maxRate) * 100, rate > 0 ? 3 : 0) : 0;
  return (
    <div className="flex items-center gap-2 w-40">
      <div className="flex-1 h-1.5 bg-surface-alt rounded-full overflow-hidden">
        <div className="h-full bg-accent rounded-full" style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono tabular-nums text-text-primary text-xs w-14 text-right">{(rate * 100).toFixed(2)}%</span>
    </div>
  );
}

export default function BacktestPage({ onStatusMessage }: { onStatusMessage: (msg: string) => void }) {
  const [symbols, setSymbols] = useState("SPY,QQQ");
  const [track, setTrack] = useState<(typeof TRACKS)[number]>("track1_alpha_spreads");
  const [start, setStart] = useState("2026-03-01");
  const [end, setEnd] = useState("2026-08-27");
  const [results, setResults] = useState<Record<string, BacktestResult>>({});
  const [runState, setRunState] = useState<Record<string, RunState>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const { data: watchlist } = useQuery({ queryKey: ["watchlist"], queryFn: api.getWatchlist, staleTime: Infinity });

  const symbolList = symbols.split(",").map((s) => s.trim().toUpperCase()).filter(Boolean);
  const isRunning = Object.values(runState).some((s) => s === "pending");

  const run = () => {
    if (symbolList.length === 0) return;
    setResults({});
    setErrors({});
    setExpanded(new Set());
    setRunState(Object.fromEntries(symbolList.map((s) => [s, "pending" as RunState])));
    onStatusMessage(`Running backtest for ${symbolList.length} symbol${symbolList.length > 1 ? "s" : ""}…`);

    for (const symbol of symbolList) {
      api.runBacktest({ symbol, track, start, end })
        .then((r) => {
          setResults((prev) => ({ ...prev, [symbol]: r }));
          setRunState((prev) => ({ ...prev, [symbol]: "done" }));
        })
        .catch((err) => {
          setErrors((prev) => ({ ...prev, [symbol]: err instanceof Error ? err.message : String(err) }));
          setRunState((prev) => ({ ...prev, [symbol]: "error" }));
        });
    }
  };

  const toggleExpanded = (symbol: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(symbol) ? next.delete(symbol) : next.add(symbol);
      return next;
    });
  };

  const doneSymbols = symbolList.filter((s) => runState[s] === "done" && results[s]);
  const maxRate = Math.max(...doneSymbols.map((s) => results[s].qualification_rate ?? 0), 0.0001);
  const knownGaps = doneSymbols.length > 0 ? results[doneSymbols[0]].known_gaps ?? [] : [];

  return (
    <div className="flex flex-col gap-6">
      <Section title="Run Backtest">
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-80">
            <SymbolPicker value={symbols} onChange={setSymbols} categories={watchlist?.categories ?? {}} />
          </div>
          <Select label="Track" value={track} onChange={(e) => setTrack(e.target.value as typeof track)} className="w-64">
            {TRACKS.map((t) => <option key={t} value={t}>{TRACK_LABELS[t]}</option>)}
          </Select>
          <TextField label="Start" type="date" mono value={start} onChange={(e) => setStart(e.target.value)} />
          <TextField label="End" type="date" mono value={end} onChange={(e) => setEnd(e.target.value)} />
          <Button variant="primary" onClick={run} disabled={isRunning || symbolList.length === 0}>
            {isRunning ? "Running…" : `Run Backtest${symbolList.length > 1 ? ` (${symbolList.length})` : ""}`}
          </Button>
        </div>
        <p className="mt-3 text-xs text-text-secondary max-w-xl">
          Replays real historical bars through each track's deterministic (non-LLM) entry gate and reports how often it would have
          qualified — a signal-frequency report, not a trade simulation (no historical options/IV data source exists to price a
          hypothetical fill against).
        </p>
        {symbolList.length > 0 && Object.keys(runState).length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {symbolList.map((s) => (
              <span
                key={s}
                className={`px-2 py-0.5 text-[11px] font-mono tabular-nums border ${
                  runState[s] === "done" ? "border-success/40 text-success" :
                  runState[s] === "error" ? "border-error/40 text-error" :
                  "border-border text-text-secondary"
                }`}
              >
                {s} {runState[s] === "pending" ? "…" : runState[s] === "done" ? "✓" : "✕"}
              </span>
            ))}
          </div>
        )}
        {Object.entries(errors).map(([s, msg]) => (
          <p key={s} className="mt-1 text-xs text-error">{s}: {msg}</p>
        ))}
      </Section>

      {doneSymbols.length > 0 && (
        <Section title="Results">
          {knownGaps.length > 0 && (
            <p className="mb-3 text-xs text-text-secondary">
              <span className="text-warning font-semibold">Known gaps: </span>
              {knownGaps.join(" · ")}
            </p>
          )}
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-text-secondary">
                  <th className="pr-4 py-1.5 w-6" />
                  <th className="pr-4 py-1.5">Symbol</th>
                  <th className="pr-4 py-1.5">Bars Evaluated</th>
                  <th className="pr-4 py-1.5">Qualified</th>
                  <th className="pr-4 py-1.5">Rate</th>
                </tr>
              </thead>
              <tbody>
                {[...doneSymbols].sort((a, b) => (results[b].qualification_rate ?? 0) - (results[a].qualification_rate ?? 0)).map((symbol) => {
                  const r = results[symbol];
                  const isOpen = expanded.has(symbol);
                  const hasDetail = (r.qualification_by_month && Object.keys(r.qualification_by_month).length > 0) ||
                    (r.qualifying_events && r.qualifying_events.length > 0);
                  return (
                    <Fragment key={symbol}>
                      <tr
                        className="border-t border-border/40 hover:bg-surface-alt/40 cursor-pointer"
                        onClick={() => hasDetail && toggleExpanded(symbol)}
                      >
                        <td className="pr-4 py-2 text-text-secondary">{hasDetail ? (isOpen ? "▾" : "▸") : ""}</td>
                        <td className="pr-4 py-2 font-mono font-semibold text-text-primary">{symbol}</td>
                        <td className="pr-4 py-2 font-mono tabular-nums">{r.total_bars_evaluated ?? 0}</td>
                        <td className="pr-4 py-2 font-mono tabular-nums">{r.qualified_count ?? 0}</td>
                        <td className="pr-4 py-2"><RateMeter rate={r.qualification_rate ?? 0} maxRate={maxRate} /></td>
                      </tr>
                      {isOpen && (
                        <tr key={`${symbol}-detail`} className="border-t border-border/20 bg-surface-alt/20">
                          <td />
                          <td colSpan={4} className="pb-4 pt-1 pr-4">
                            {r.qualification_by_month && Object.keys(r.qualification_by_month).length > 0 && (
                              <div className="mb-3">
                                <p className="mb-1.5 text-[11px] font-semibold text-text-secondary uppercase tracking-wide">Qualification by month</p>
                                <div className="overflow-x-auto">
                                  <table className="text-[11px]">
                                    <thead>
                                      <tr className="text-left text-text-secondary">
                                        <th className="pr-4 py-0.5">Month</th>
                                        <th className="pr-4 py-0.5">Evaluated</th>
                                        <th className="pr-4 py-0.5">Qualified</th>
                                        <th className="pr-4 py-0.5">Rate</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {Object.entries(r.qualification_by_month).sort(([a], [b]) => a.localeCompare(b)).map(([month, stats]) => (
                                        <tr key={month}>
                                          <td className="pr-4 py-0.5 font-mono">{month}</td>
                                          <td className="pr-4 py-0.5">{stats.evaluated}</td>
                                          <td className="pr-4 py-0.5">{stats.qualified}</td>
                                          <td className="pr-4 py-0.5">{stats.evaluated ? `${((stats.qualified / stats.evaluated) * 100).toFixed(2)}%` : "—"}</td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              </div>
                            )}
                            {r.qualifying_events && r.qualifying_events.length > 0 && (
                              <div>
                                <p className="mb-1.5 text-[11px] font-semibold text-text-secondary uppercase tracking-wide">
                                  Sample qualifying events ({r.qualifying_events.length})
                                </p>
                                <div className="max-h-40 overflow-y-auto">
                                  <table className="text-[11px]">
                                    <tbody>
                                      {r.qualifying_events.slice(0, 100).map((ev, i) => (
                                        <tr key={i}>
                                          <td className="pr-4 py-0.5 font-mono text-text-secondary">{ev.timestamp}</td>
                                          <td className="pr-4 py-0.5">{ev.direction ?? "—"}</td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              </div>
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Section>
      )}
    </div>
  );
}
