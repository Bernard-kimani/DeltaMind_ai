import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import type { AgentDecision, FlatConfig } from "../../api/types";
import { TRACKS, TRACK_LABELS } from "../../api/types";
import { Button, Card, DecisionRow, PositionRow, Section, Select, StatusDot, TextField } from "../../components/primitives";
import { MODELS_BY_PROVIDER, PROVIDER_LABELS } from "./models";

/** Wide, two-column popup for a single decision-history row — the full
 * thesis/proposed-order doesn't fit the one-line row, so it only ever
 * appears here. Facts (track/sentiment/verdict) in a narrow left rail,
 * reasoning given the rest of the width to breathe as prose. */
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
              <br />{TRACK_LABELS[decision.track as keyof typeof TRACK_LABELS] ?? decision.track}
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
              <>
                <div className="text-[10px] tracking-widest uppercase text-text-secondary mt-2">Proposed Order</div>
                <pre className="text-[11px] font-mono bg-ground border border-border p-2.5 overflow-x-auto">{JSON.stringify(decision.proposed_order, null, 2)}</pre>
              </>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}

const DEFAULTS: FlatConfig = {
  llm_provider: "featherless",
  llm_model: MODELS_BY_PROVIDER.featherless[0].value,
  featherless_api_key: "",
  fireworks_api_key: "",
  temperature: "0.3",
  symbols: "SPY,QQQ",
  track: "track1_alpha_spreads",
  interval_seconds: "300",
};

export default function ControlsPage({ onStatusMessage }: { onStatusMessage: (msg: string) => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState<FlatConfig>(DEFAULTS);
  const [dirty, setDirty] = useState(false);
  const [apiMsg, setApiMsg] = useState<string | null>(null);
  const [alpacaMsg, setAlpacaMsg] = useState<string | null>(null);
  const [openDecision, setOpenDecision] = useState<AgentDecision | null>(null);

  const { data: config } = useQuery({ queryKey: ["config"], queryFn: api.getConfig });
  const { data: status } = useQuery({ queryKey: ["engine-status"], queryFn: api.getEngineStatus, refetchInterval: 3000 });
  const { data: stats } = useQuery({ queryKey: ["engine-stats"], queryFn: api.getEngineStats, refetchInterval: status?.is_running ? 2000 : 5000 });
  const { data: decisions } = useQuery({ queryKey: ["decisions"], queryFn: () => api.getDecisions(50), refetchInterval: 3000 });
  const { data: positions } = useQuery({ queryKey: ["positions"], queryFn: api.getPositions, refetchInterval: 5000 });

  useEffect(() => {
    if (config && !dirty) setForm(config);
  }, [config, dirty]);

  const set = <K extends keyof FlatConfig>(key: K, value: FlatConfig[K]) => { setForm((f) => ({ ...f, [key]: value })); setDirty(true); };

  const saveMutation = useMutation({
    mutationFn: () => api.saveConfig(form),
    onSuccess: () => { setDirty(false); onStatusMessage("Configuration saved"); qc.invalidateQueries({ queryKey: ["config"] }); },
  });
  const resetMutation = useMutation({
    mutationFn: api.resetConfig,
    onSuccess: (cfg) => { setForm(cfg); setDirty(false); onStatusMessage("Configuration reset to defaults"); },
  });

  const testApiMutation = useMutation({
    mutationFn: () => api.testLLM(form.llm_provider, form.llm_model, form.llm_provider === "featherless" ? form.featherless_api_key : form.fireworks_api_key),
    onSuccess: (r) => setApiMsg(r.message),
  });
  const testAlpacaMutation = useMutation({
    mutationFn: api.testAlpaca,
    onSuccess: (r) => setAlpacaMsg(r.message),
  });

  const startMutation = useMutation({
    mutationFn: () => api.startEngine({ symbols: form.symbols, track: form.track, interval_seconds: Number(form.interval_seconds) }),
    onSuccess: (r) => { onStatusMessage(r.message); qc.invalidateQueries({ queryKey: ["engine-status"] }); },
  });
  const stopMutation = useMutation({
    mutationFn: api.stopEngine,
    onSuccess: (r) => { onStatusMessage(r.message); qc.invalidateQueries({ queryKey: ["engine-status"] }); },
  });
  const restartMutation = useMutation({
    mutationFn: () => api.restartEngine({ symbols: form.symbols, track: form.track, interval_seconds: Number(form.interval_seconds) }),
    onSuccess: (r) => { onStatusMessage(r.message); qc.invalidateQueries({ queryKey: ["engine-status"] }); },
  });

  const exportConfig = () => {
    const blob = new Blob([JSON.stringify(form, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "deltamind_config.json";
    a.click();
    URL.revokeObjectURL(url);
    onStatusMessage("Configuration exported");
  };
  const importConfig = (file: File) => {
    file.text().then((text) => {
      try {
        setForm({ ...DEFAULTS, ...JSON.parse(text) });
        setDirty(true);
        onStatusMessage("Configuration imported — review and Save");
      } catch {
        onStatusMessage("Import failed — invalid JSON");
      }
    });
  };

  const running = status?.is_running ?? false;
  const models = MODELS_BY_PROVIDER[form.llm_provider] ?? [];
  const currentApiKey = form.llm_provider === "featherless" ? form.featherless_api_key : form.fireworks_api_key;
  const setCurrentApiKey = (v: string) => set(form.llm_provider === "featherless" ? "featherless_api_key" : "fireworks_api_key", v);

  const lastDecisionLabel = stats?.last_decision_time ? new Date(stats.last_decision_time).toLocaleTimeString() : "None yet";

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_1fr_0.9fr] gap-6 items-start">
        <div className="flex flex-col">
          <Section title="AI Configuration">
            <div className="flex flex-col gap-3">
              <Select
                label="Provider" value={form.llm_provider}
                onChange={(e) => { const p = e.target.value as FlatConfig["llm_provider"]; set("llm_provider", p); set("llm_model", MODELS_BY_PROVIDER[p]?.[0]?.value ?? ""); }}
              >
                {Object.keys(MODELS_BY_PROVIDER).map((p) => <option key={p} value={p}>{PROVIDER_LABELS[p] ?? p}</option>)}
              </Select>
              <Select label="Model" value={form.llm_model} onChange={(e) => set("llm_model", e.target.value)}>
                {models.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
              </Select>
              <TextField
                label="API Key" mono type="password" autoComplete="off" value={currentApiKey}
                onChange={(e) => setCurrentApiKey(e.target.value)} placeholder="Enter your API key..."
              />
              <Button onClick={() => testApiMutation.mutate()} disabled={testApiMutation.isPending} className="self-start">Test API</Button>
              {apiMsg && <p className="text-xs text-text-secondary">{apiMsg}</p>}
              <TextField label="Temperature" mono value={form.temperature} onChange={(e) => set("temperature", e.target.value)} className="w-28" />
            </div>
          </Section>
        </div>

        <div className="flex flex-col lg:border-l lg:border-divider/15 lg:pl-6">
          <Section title="Telemetry">
            <div className="grid grid-cols-2 gap-x-6 gap-y-4">
              <div>
                <div className="text-[10px] tracking-widest uppercase text-text-secondary">Uptime</div>
                <div className="text-base font-mono tabular-nums font-medium mt-1">{stats?.uptime ?? "Not running"}</div>
              </div>
              <div>
                <div className="text-[10px] tracking-widest uppercase text-text-secondary">Last Decision</div>
                <div className="text-base font-mono tabular-nums font-medium mt-1">{lastDecisionLabel}</div>
              </div>

              <div className="col-span-2">
                <div className="text-[10px] tracking-widest uppercase text-text-secondary">Total Cycles</div>
                <div className="text-3xl font-mono tabular-nums font-semibold text-accent mt-1">{stats?.total_cycles ?? 0}</div>
              </div>

              <div className="col-span-2 h-px bg-divider/15" />

              <div>
                <div className="text-[10px] tracking-widest uppercase text-text-secondary">Approved Trades</div>
                <div className="text-base font-mono tabular-nums font-medium text-success mt-1">{stats?.approved_trades ?? 0}</div>
              </div>
              <div>
                <div className="text-[10px] tracking-widest uppercase text-text-secondary">Rejected / Vetoed</div>
                <div className="text-base font-mono tabular-nums font-medium text-warning mt-1">{stats?.rejected_cycles ?? 0}</div>
              </div>
            </div>
          </Section>
        </div>

        <div className="flex flex-col lg:border-l lg:border-divider/15 lg:pl-6">
          <Section title="Agent Engine">
            <p className="flex items-center gap-2.5 text-sm mb-1">
              <StatusDot live={running} color={running ? "success" : "error"} />
              <span className={`font-mono font-medium tracking-wide ${running ? "text-success" : "text-error"}`}>{running ? "RUNNING" : "STOPPED"}</span>
            </p>
            <p className="text-[11px] font-mono text-text-disabled mb-3 h-4">{running && status?.pid ? `pid ${status.pid}` : ""}</p>
            <div className="flex flex-col gap-3">
              <TextField label="Symbols" mono value={form.symbols} onChange={(e) => set("symbols", e.target.value)} placeholder="SPY,QQQ" />
              <Select label="Track" value={form.track} onChange={(e) => set("track", e.target.value as FlatConfig["track"])}>
                {TRACKS.map((t) => <option key={t} value={t}>{TRACK_LABELS[t]}</option>)}
              </Select>
              <TextField label="Interval (seconds)" mono value={form.interval_seconds} onChange={(e) => set("interval_seconds", e.target.value)} />
              <Button onClick={() => testAlpacaMutation.mutate()} disabled={testAlpacaMutation.isPending} className="self-start">Test Alpaca Connection</Button>
              {alpacaMsg && <p className="text-xs text-text-secondary">{alpacaMsg}</p>}
            </div>
            <div className="grid grid-cols-2 gap-2 mt-4">
              <Button variant="success" disabled={running || startMutation.isPending} onClick={() => startMutation.mutate()}>Start</Button>
              <Button variant="danger" disabled={!running || stopMutation.isPending} onClick={() => stopMutation.mutate()}>Stop</Button>
              <Button variant="warning" className="col-span-2" disabled={!running || restartMutation.isPending} onClick={() => restartMutation.mutate()}>Restart</Button>
            </div>
          </Section>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {dirty && <span className="text-xs text-warning mr-auto">Unsaved changes</span>}
        <Button onClick={() => resetMutation.mutate()} disabled={resetMutation.isPending}>Reset Defaults</Button>
        <label className="px-4 py-2 text-xs font-semibold tracking-wide uppercase transition-all duration-150 bg-surface-alt hover:brightness-95 dark:hover:brightness-125 text-text-primary cursor-pointer">
          Load Configuration
          <input type="file" accept="application/json" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) importConfig(f); e.target.value = ""; }} />
        </label>
        <Button onClick={exportConfig}>Export Config File</Button>
        <Button variant="primary" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>Save Changes</Button>
      </div>

      <Section title="Live Trading Activity">
        {!!positions?.length && (
          <div className="mb-5">
            <div className="text-[10px] tracking-widest uppercase text-text-secondary mb-1">Open Positions</div>
            <div className="flex flex-col divide-y divide-divider/10">
              {positions.map((p) => <PositionRow key={p.symbol} {...p} />)}
            </div>
          </div>
        )}

        <div>
          <div className="text-[10px] tracking-widest uppercase text-text-secondary mb-1">Decision History</div>
          {!decisions?.length && (
            <p className="text-xs text-text-secondary py-4">No decisions yet. Start the agent engine to begin receiving cycles.</p>
          )}
          <div className="flex flex-col divide-y divide-divider/10 max-h-105 overflow-y-auto">
            {decisions?.map((d) => <DecisionRow key={d.id} decision={d} onClick={() => setOpenDecision(d)} />)}
          </div>
        </div>
      </Section>

      {openDecision && <DecisionDetailModal decision={openDecision} onClose={() => setOpenDecision(null)} />}
    </div>
  );
}
