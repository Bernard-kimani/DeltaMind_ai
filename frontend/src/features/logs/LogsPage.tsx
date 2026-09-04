import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import type { Track } from "../../api/types";
import { Button, Divider, Select, TextField } from "../../components/primitives";
import { DEMO_SINGLE_TRACK, DEMO_TRACK } from "../../config";

const LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] as const;
const LEVEL_ORDER: Record<string, number> = { DEBUG: 0, INFO: 1, WARNING: 2, ERROR: 3, CRITICAL: 4 };

// Mirrors scripts/run_agent_loop.py's logging format:
// '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
const LOG_LINE_RE = /^(\S+ \S+) - (.+?) - (DEBUG|INFO|WARNING|ERROR|CRITICAL) - ([\s\S]*)$/;

type ParsedLine = { time: string; module: string; level: (typeof LEVELS)[number]; message: string };

function parseLine(line: string): ParsedLine | null {
  const m = line.match(LOG_LINE_RE);
  if (!m) return null;
  const [, timestamp, module, level, message] = m;
  const time = timestamp.split(" ")[1]?.split(",")[0] ?? timestamp;
  return { time, module, level: level as ParsedLine["level"], message };
}

function lineLevel(line: string): string | null {
  return parseLine(line)?.level ?? null;
}

const LEVEL_STYLE: Record<(typeof LEVELS)[number], { text: string; row: string }> = {
  DEBUG: { text: "text-text-disabled", row: "" },
  INFO: { text: "text-text-secondary", row: "" },
  WARNING: { text: "text-warning", row: "border-l-2 border-warning bg-warning/[0.06]" },
  ERROR: { text: "text-error", row: "border-l-2 border-error bg-error/[0.06]" },
  CRITICAL: { text: "text-error", row: "border-l-2 border-error bg-error/10" },
};

const LOG_TRACKS = ["track1_alpha_spreads", "track4_income_wheel", "track5_momentum_swing"] as const;
const TRACK_TAB_LABEL: Record<(typeof LOG_TRACKS)[number], string> = {
  track1_alpha_spreads: "Track 1",
  track4_income_wheel: "Track 4",
  track5_momentum_swing: "Track 5",
};

export default function LogsPage({ onStatusMessage }: { onStatusMessage: (msg: string) => void }) {
  // Used to be locked to config.ts's build-time ACTIVE_TRACK (a single-
  // track-per-deploy flag from before this app grew a multi-engine
  // Controls tab) -- every other page already lets you pick a track
  // in-page (see PerformancePage's toggle), so this was the one place
  // still hardcoded to Track 1, showing an empty pane whenever Track 1
  // wasn't the engine actually running.
  const [track, setTrack] = useState<Track>(DEMO_SINGLE_TRACK ? DEMO_TRACK : "track5_momentum_swing");
  const [buffer, setBuffer] = useState<string[]>([]);
  // Defaults to WARNING, not INFO — 2026-08-27: once the pipeline's been
  // confirmed working, day-to-day monitoring only needs TRADE (logged at
  // WARNING specifically so it survives this default — see
  // run_agent_stream_track1.py/run_agent_loop.py), REJECTED, and real
  // errors, not every WAIT/BLOCKED no-op cycle. Still switchable back to
  // INFO from the dropdown for full per-cycle detail.
  const [level, setLevel] = useState<(typeof LEVELS)[number]>("WARNING");
  const [search, setSearch] = useState("");
  const [autoScroll, setAutoScroll] = useState(true);
  const offsetRef = useRef(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const qc = useQueryClient();

  useEffect(() => {
    // Switching tracks means tailing a different log file from scratch —
    // the old buffer/offset belong to the previous track's file.
    offsetRef.current = 0;
    setBuffer([]);

    let cancelled = false;
    let inFlight = false;
    const poll = async () => {
      // Guards against overlapping requests: if a tailLog call ever takes
      // longer than the 1s interval (e.g. the backend is busy), setInterval
      // would otherwise fire a second poll before the first's response
      // arrives — both read the same stale offsetRef.current, both get
      // back the same batch of lines, and both append them, duplicating
      // every line in that batch in the UI (confirmed: the log FILE itself
      // never had duplicates, only the rendered buffer did).
      if (inFlight) return;
      inFlight = true;
      try {
        const { lines, new_offset } = await api.tailLog(track, offsetRef.current);
        if (cancelled) return;
        if (lines.length) {
          offsetRef.current = new_offset;
          setBuffer((b) => [...b, ...lines].slice(-1000));
        }
      } catch {
        // backend not reachable yet — next poll retries
      } finally {
        inFlight = false;
      }
    };
    poll();
    const id = setInterval(poll, 1000);
    return () => { cancelled = true; clearInterval(id); };
  }, [track]);

  const filtered = buffer.filter((line) => {
    const lvl = lineLevel(line);
    if (lvl && LEVEL_ORDER[lvl] < LEVEL_ORDER[level]) return false;
    if (search && !line.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  useEffect(() => {
    if (!autoScroll || !scrollRef.current) return;
    const selection = window.getSelection();
    if (selection && selection.toString().length > 0 && scrollRef.current.contains(selection.anchorNode)) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [filtered.length, autoScroll]);

  const { data: stats } = useQuery({ queryKey: ["log-stats", track], queryFn: () => api.getLogStats(track), refetchInterval: 5000 });

  const clearMutation = useMutation({
    mutationFn: () => api.clearLog(track),
    onSuccess: (r) => { offsetRef.current = r.new_offset; setBuffer([]); onStatusMessage("Logs cleared"); qc.invalidateQueries({ queryKey: ["log-stats"] }); },
  });

  return (
    <div className="flex flex-col h-full">
      <div className="flex flex-wrap items-end gap-3 pb-4">
        {!DEMO_SINGLE_TRACK && (
          <div className="flex gap-1">
            {LOG_TRACKS.map((t) => (
              <button
                key={t}
                onClick={() => setTrack(t)}
                className={`px-3 py-1 text-[11px] font-semibold tracking-wide uppercase border ${track === t ? "border-accent text-accent" : "border-border text-text-secondary hover:text-text-primary"}`}
              >
                {TRACK_TAB_LABEL[t]}
              </button>
            ))}
          </div>
        )}
        <Select label="Level" value={level} onChange={(e) => setLevel(e.target.value as typeof level)} className="w-32">
          {LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
        </Select>
        <TextField label="Search" mono placeholder="Filter logs…" value={search} onChange={(e) => setSearch(e.target.value)} className="w-56" />
        <label className="flex items-center gap-1.5 text-xs text-text-secondary pb-2">
          <input type="checkbox" checked={autoScroll} onChange={(e) => setAutoScroll(e.target.checked)} className="accent-(--accent)" /> Auto-scroll
        </label>
        <div className="ml-auto flex gap-2">
          <Button onClick={() => clearMutation.mutate()} disabled={clearMutation.isPending}>Clear</Button>
        </div>
      </div>
      <Divider />
      <div ref={scrollRef} className="flex-1 overflow-auto bg-surface border border-border font-mono tabular-nums text-[11px] leading-relaxed py-2 my-4">
        {filtered.length === 0
          ? <div className="px-4 py-2 text-text-disabled">Waiting for agent activity — logs stream here once the engine is running.</div>
          : filtered.map((l, i) => {
              const parsed = parseLine(l);
              if (!parsed) {
                return <div key={i} className="px-4 py-0.5 text-text-disabled whitespace-pre">{l}</div>;
              }
              const style = LEVEL_STYLE[parsed.level];
              return (
                <div key={i} className={`flex gap-3 px-3.5 py-0.5 ${style.row}`}>
                  <span className="shrink-0 w-17.5 text-text-disabled">{parsed.time}</span>
                  <span className={`shrink-0 w-16 font-semibold ${style.text}`}>{parsed.level}</span>
                  <span className="shrink-0 w-35 truncate text-accent/85">[{parsed.module}]</span>
                  <span className="min-w-0 flex-1 text-text-primary wrap-break-word">{parsed.message}</span>
                </div>
              );
            })}
      </div>
      <Divider />
      <div className="flex items-center gap-2 pt-4">
        <span className="ml-auto text-[11px] font-mono tabular-nums text-text-secondary">
          {stats ? `${stats.total_entries} entries · ${((stats.file_size_bytes ?? 0) / 1024).toFixed(1)} KB` : "Log file: not available"}
        </span>
      </div>
    </div>
  );
}
