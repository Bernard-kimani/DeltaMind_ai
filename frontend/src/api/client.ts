import type {
  Account, AgentDecision, BacktestResult, EngineStats, EngineStatus,
  FlatConfig, LogStats, LogTailResponse, PerformanceMetrics, Position, TestResult, Trade, TrackPnlSummary,
} from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    throw new Error(`${init?.method ?? "GET"} ${path} failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

const getJSON = <T>(path: string) => request<T>(path);
const postJSON = <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });

export const api = {
  // Account / positions / trades
  getAccount: () => getJSON<Account>("/api/account"),
  getPositions: () => getJSON<Position[]>("/api/positions"),
  getTrades: (limit = 100, track?: string) => getJSON<Trade[]>(`/api/trades?limit=${limit}${track ? `&track=${track}` : ""}`),
  getDecisions: (limit = 100, track?: string, llmOnly = false) => getJSON<AgentDecision[]>(`/api/trades/decisions?limit=${limit}${track ? `&track=${track}` : ""}${llmOnly ? "&llm_only=true" : ""}`),
  getPnlSummary: () => getJSON<TrackPnlSummary[]>("/api/trades/pnl-summary"),
  getPerformance: (track: string) => getJSON<PerformanceMetrics>(`/api/performance?track=${track}`),

  // Backtest
  runBacktest: (body: { symbol: string; track: string; start: string; end: string }) => postJSON<BacktestResult>("/api/backtest", body),

  // AI / engine configuration
  getConfig: () => getJSON<FlatConfig>("/api/config"),
  saveConfig: (config: FlatConfig) => postJSON<FlatConfig>("/api/config", config),
  resetConfig: () => postJSON<FlatConfig>("/api/config/reset"),
  testLLM: (provider: string, model: string, apiKey: string) => postJSON<TestResult>("/api/config/test-llm", { provider, model, api_key: apiKey }),
  testAlpaca: (track: string) => postJSON<TestResult>(`/api/config/test-alpaca?track=${track}`),
  getWatchlist: () => getJSON<{ csv: string; categories: Record<string, string[]> }>("/api/config/watchlist"),

  // Agent engine lifecycle — Track 1 and Track 4 run as independent
  // concurrent engines, so every call is scoped to one `track`.
  getEngineStatus: (track: string) => getJSON<EngineStatus>(`/api/engine/status?track=${track}`),
  getEngineStats: (track: string) => getJSON<EngineStats>(`/api/engine/stats?track=${track}`),
  startEngine: (body: { symbols: string; track: string; interval_seconds: number; sentiment_threshold: number; volume_ratio_min: number }) => postJSON<{ ok: boolean; message: string }>("/api/engine/start", body),
  stopEngine: (track: string) => postJSON<{ ok: boolean; message: string }>("/api/engine/stop", { track }),
  restartEngine: (body: { symbols: string; track: string; interval_seconds: number; sentiment_threshold: number; volume_ratio_min: number }) => postJSON<{ ok: boolean; message: string }>("/api/engine/restart", body),

  // Logs — also scoped per track (separate log files)
  tailLog: (track: string, offset: number) => getJSON<LogTailResponse>(`/api/logs/tail?track=${track}&offset=${offset}`),
  getLogStats: (track: string) => getJSON<LogStats>(`/api/logs/stats?track=${track}`),
  clearLog: (track: string) => postJSON<{ new_offset: number }>(`/api/logs/clear?track=${track}`),
};
