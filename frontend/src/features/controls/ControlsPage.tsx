import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import type { FlatConfig, Track } from "../../api/types";
import { Button, Card, parseUtcTimestamp, PositionRow, Section, Select, StatusDot, TextField } from "../../components/primitives";
import { MODELS_BY_PROVIDER, PROVIDER_LABELS } from "./models";
import { SymbolPicker } from "./SymbolPicker";

const BASE_DEFAULTS: Omit<FlatConfig, "track"> = {
  llm_provider: "featherless",
  llm_model: MODELS_BY_PROVIDER.featherless[0].value,
  featherless_api_key: "",
  fireworks_api_key: "",
  temperature: "0.3",
  symbols: "SPY,QQQ",
  interval_seconds: "300",
  sentiment_threshold: "0.5",
  volume_ratio_min: "1.2",
};

export default function ControlsPage({ track, onStatusMessage }: { track: Track; onStatusMessage: (msg: string) => void }) {
  const qc = useQueryClient();
  // Both tracks now hardcode their LLM gate (track1_validator.py /
  // track4_validator.py) — neither reads sentiment_threshold/volume_ratio_min
  // any more, so those fields are hidden for both. Track 1 runs bar-close-
  // triggered off a real websocket stream (no fixed interval); only Track 4's
  // interval-polling loop still needs the Interval field.
  const SHOW_INTERVAL = track === "track4_income_wheel";
  const [form, setForm] = useState<FlatConfig>({ ...BASE_DEFAULTS, track });
  const [dirty, setDirty] = useState(false);
  const [apiMsg, setApiMsg] = useState<string | null>(null);
  const [alpacaMsg, setAlpacaMsg] = useState<string | null>(null);
  const [showDemoModeConfirm, setShowDemoModeConfirm] = useState(false);

  const { data: config } = useQuery({ queryKey: ["config", track], queryFn: () => api.getConfig(track) });
  const { data: status } = useQuery({ queryKey: ["engine-status", track], queryFn: () => api.getEngineStatus(track), refetchInterval: 3000 });
  const { data: stats } = useQuery({ queryKey: ["engine-stats", track], queryFn: () => api.getEngineStats(track), refetchInterval: status?.is_running ? 2000 : 5000 });
  const { data: positions } = useQuery({ queryKey: ["positions"], queryFn: api.getPositions, refetchInterval: 5000 });
  const { data: watchlist } = useQuery({ queryKey: ["watchlist"], queryFn: api.getWatchlist, staleTime: Infinity });

  useEffect(() => {
    if (config && !dirty) setForm(config);
  }, [config, dirty]);

  const set = <K extends keyof FlatConfig>(key: K, value: FlatConfig[K]) => { setForm((f) => ({ ...f, [key]: value })); setDirty(true); };

  const saveMutation = useMutation({
    mutationFn: () => api.saveConfig(form),
    onSuccess: () => { setDirty(false); onStatusMessage("Configuration saved"); qc.invalidateQueries({ queryKey: ["config", track] }); },
  });
  const resetMutation = useMutation({
    mutationFn: () => api.resetConfig(track),
    onSuccess: (cfg) => { setForm(cfg); setDirty(false); onStatusMessage("Configuration reset to defaults"); },
  });
  const discardChanges = () => {
    if (config) { setForm(config); setDirty(false); onStatusMessage("Unsaved changes discarded"); }
  };

  const testApiMutation = useMutation({
    mutationFn: () => api.testLLM(form.llm_provider, form.llm_model, form.llm_provider === "featherless" ? form.featherless_api_key : form.fireworks_api_key),
    onSuccess: (r) => setApiMsg(r.message),
  });
  const clearKeyMutation = useMutation({
    mutationFn: () =>
      api.saveConfig({
        ...form,
        featherless_api_key: "",
        fireworks_api_key: "",
        clear_featherless_key: form.llm_provider === "featherless",
        clear_fireworks_key: form.llm_provider === "fireworks",
      }),
    onSuccess: (cfg) => {
      setForm(cfg);
      setDirty(false);
      onStatusMessage("API key cleared — this track now runs in demo mode (no LLM) until a new key is saved");
      qc.invalidateQueries({ queryKey: ["config", track] });
    },
  });
  const testAlpacaMutation = useMutation({
    mutationFn: () => api.testAlpaca(track),
    onSuccess: (r) => setAlpacaMsg(r.message),
  });

  const engineArgs = () => ({
    track,
    symbols: form.symbols,
    interval_seconds: Number(form.interval_seconds),
    sentiment_threshold: Number(form.sentiment_threshold),
    volume_ratio_min: Number(form.volume_ratio_min),
  });
  const invalidateEngine = () => { qc.invalidateQueries({ queryKey: ["engine-status", track] }); qc.invalidateQueries({ queryKey: ["engine-stats", track] }); };
  const startMutation = useMutation({
    mutationFn: () => api.startEngine(engineArgs()),
    onSuccess: (r) => { onStatusMessage(r.message); invalidateEngine(); },
  });
  const stopMutation = useMutation({
    mutationFn: () => api.stopEngine(track),
    onSuccess: (r) => { onStatusMessage(r.message); invalidateEngine(); },
  });
  const restartMutation = useMutation({
    mutationFn: () => api.restartEngine(engineArgs()),
    onSuccess: (r) => { onStatusMessage(r.message); invalidateEngine(); },
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
        setForm({ ...BASE_DEFAULTS, track, ...JSON.parse(text) });
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
  const currentApiKeySet = form.llm_provider === "featherless" ? !!form.featherless_api_key_set : !!form.fireworks_api_key_set;

  const handleStartClick = () => {
    if (!currentApiKeySet) { setShowDemoModeConfirm(true); return; }
    startMutation.mutate();
  };

  const lastDecisionLabel = stats?.last_decision_time ? parseUtcTimestamp(stats.last_decision_time).toLocaleTimeString() : "None yet";

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 lg:grid-cols-[2fr_0.9fr] gap-6 items-start">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          <div className="flex flex-col">
            <Section title="AI Configuration">
              <div className="flex flex-col gap-3">
                <div className="grid grid-cols-2 gap-3">
                  <Select
                    label="Provider" value={form.llm_provider}
                    onChange={(e) => { const p = e.target.value as FlatConfig["llm_provider"]; set("llm_provider", p); set("llm_model", MODELS_BY_PROVIDER[p]?.[0]?.value ?? ""); }}
                  >
                    {Object.keys(MODELS_BY_PROVIDER).map((p) => <option key={p} value={p}>{PROVIDER_LABELS[p] ?? p}</option>)}
                  </Select>
                  <Select label="Model" value={form.llm_model} onChange={(e) => set("llm_model", e.target.value)}>
                    {models.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                  </Select>
                </div>
                <div className="flex items-end gap-2">
                  <div className="flex-1 min-w-0">
                    <TextField
                      label="API Key" mono type="password" autoComplete="off" value={currentApiKey}
                      onChange={(e) => setCurrentApiKey(e.target.value)}
                      placeholder={currentApiKeySet ? "Key configured — paste a new one to replace it" : "No key configured — paste one to enable LLM reasoning"}
                    />
                  </div>
                  <Button onClick={() => testApiMutation.mutate()} disabled={testApiMutation.isPending} className="shrink-0">Test API</Button>
                  {currentApiKeySet && (
                    <Button onClick={() => clearKeyMutation.mutate()} disabled={clearKeyMutation.isPending} className="shrink-0">Clear Key</Button>
                  )}
                </div>
                {apiMsg && <p className="text-xs text-text-secondary">{apiMsg}</p>}
                {!currentApiKeySet && (
                  <p className="text-xs text-warning">
                    No {PROVIDER_LABELS[form.llm_provider] ?? form.llm_provider} key configured — this track will run in demo mode: every stage runs live except the LLM validator, which is skipped and logged as such.
                  </p>
                )}
              </div>
            </Section>
          </div>

          <div className="flex flex-col sm:border-l sm:border-divider/15 sm:pl-6">
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

          <div className="flex flex-col sm:col-span-2">
            <Section title="Config Actions">
              <div className="flex flex-wrap items-center justify-center gap-2 py-2">
                {dirty && (
                  <>
                    <span className="text-xs text-warning mr-1">Unsaved changes</span>
                    <Button onClick={discardChanges}>Discard Changes</Button>
                  </>
                )}
                <Button onClick={() => resetMutation.mutate()} disabled={resetMutation.isPending}>Reset Defaults</Button>
                <label className="px-4 py-2 text-xs font-semibold tracking-wide uppercase transition-all duration-150 bg-surface-alt hover:brightness-95 dark:hover:brightness-125 text-text-primary cursor-pointer">
                  Load Configuration
                  <input type="file" accept="application/json" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) importConfig(f); e.target.value = ""; }} />
                </label>
                <Button onClick={exportConfig}>Export Config File</Button>
                <Button variant="primary" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>Save Changes</Button>
              </div>
            </Section>
          </div>
        </div>

        <div className="flex flex-col lg:border-l lg:border-divider/15 lg:pl-6">
          <Section title="Agent Engine">
            <p className="flex items-center gap-2.5 text-sm mb-1">
              <StatusDot live={running} color={running ? "success" : "error"} />
              <span className={`font-mono font-medium tracking-wide ${running ? "text-success" : "text-error"}`}>{running ? "RUNNING" : "STOPPED"}</span>
            </p>
            <p className="text-[11px] font-mono text-text-disabled mb-1 h-4">{running && status?.pid ? `pid ${status.pid}` : ""}</p>
            {status?.circuit_breaker_tripped && (
              <p className="text-xs text-error mb-2">Circuit breaker tripped — repeated failures, check Logs. Fix the issue, then Start again.</p>
            )}
            {!status?.circuit_breaker_tripped && !!status?.auto_restart_count && (
              <p className="text-xs text-warning mb-2">Auto-restarted {status.auto_restart_count}x — {status.last_crash_reason ?? "check Logs for details"}</p>
            )}
            <div className="flex flex-col gap-3">
              <SymbolPicker value={form.symbols} onChange={(csv) => set("symbols", csv)} categories={watchlist?.categories ?? {}} />
              {SHOW_INTERVAL && (
                <div className="flex flex-col gap-1.5">
                  <TextField label="Interval (seconds)" mono value={form.interval_seconds} onChange={(e) => set("interval_seconds", e.target.value)} />
                  {Number(form.interval_seconds) < 60 && (
                    <p className="text-xs text-warning">Minimum is 60s — the engine will reject anything lower.</p>
                  )}
                </div>
              )}
              <Button onClick={() => testAlpacaMutation.mutate()} disabled={testAlpacaMutation.isPending} className="self-start">Test Alpaca Connection</Button>
              {alpacaMsg && <p className="text-xs text-text-secondary">{alpacaMsg}</p>}
            </div>
            <div className="grid grid-cols-2 gap-2 mt-4">
              <Button variant="success" disabled={running || startMutation.isPending} onClick={handleStartClick}>Start</Button>
              <Button variant="danger" disabled={!running || stopMutation.isPending} onClick={() => stopMutation.mutate()}>Stop</Button>
              <Button variant="warning" className="col-span-2" disabled={!running || restartMutation.isPending} onClick={() => restartMutation.mutate()}>Restart</Button>
            </div>
          </Section>
        </div>
      </div>

      <Section title="Live Trading Activity">
        {!positions?.length && (
          <p className="text-xs text-text-secondary py-2">No open positions.</p>
        )}
        <div className="flex flex-col divide-y divide-divider/10">
          {positions?.map((p) => <PositionRow key={p.symbol} {...p} />)}
        </div>
      </Section>

      {showDemoModeConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/50" onClick={() => setShowDemoModeConfirm(false)} />
          <Card square className="relative w-full max-w-sm p-6 flex flex-col gap-4">
            <h2 className="text-[11px] font-semibold tracking-[0.14em] uppercase text-text-secondary">No LLM key configured</h2>
            <p className="text-sm text-text-primary">
              Without a {PROVIDER_LABELS[form.llm_provider] ?? form.llm_provider} API key, the engine still runs live — Alpaca connection, the technical gate, and the risk gate all execute for real — but a qualifying setup won't be sent to the LLM validator. This is demo mode.
            </p>
            <p className="text-xs text-text-secondary">Paste a key above and Save first if you want full reasoning, or start now in demo mode.</p>
            <div className="flex justify-end gap-2">
              <Button onClick={() => setShowDemoModeConfirm(false)}>Cancel</Button>
              <Button
                variant="success"
                onClick={() => { setShowDemoModeConfirm(false); startMutation.mutate(); }}
              >
                Start in Demo Mode
              </Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
