import type {
  Account, AgentDecision, BacktestResult, EngineStats, EngineStatus,
  FlatConfig, LogStats, LogTailResponse, Position, TestResult, Trade,
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
  getTrades: (limit = 100) => getJSON<Trade[]>(`/api/trades?limit=${limit}`),
  getDecisions: (limit = 100) => getJSON<AgentDecision[]>(`/api/trades/decisions?limit=${limit}`),

  // Backtest
  runBacktest: (body: { symbol: string; track: string; start: string; end: string }) => postJSON<BacktestResult>("/api/backtest", body),

  // AI / engine configuration
  getConfig: () => getJSON<FlatConfig>("/api/config"),
  saveConfig: (config: FlatConfig) => postJSON<FlatConfig>("/api/config", config),
  resetConfig: () => postJSON<FlatConfig>("/api/config/reset"),
  testLLM: (provider: string, model: string, apiKey: string) => postJSON<TestResult>("/api/config/test-llm", { provider, model, api_key: apiKey }),
  testAlpaca: () => postJSON<TestResult>("/api/config/test-alpaca"),

  // Agent engine lifecycle
  getEngineStatus: () => getJSON<EngineStatus>("/api/engine/status"),
  getEngineStats: () => getJSON<EngineStats>("/api/engine/stats"),
  startEngine: (body: { symbols: string; track: string; interval_seconds: number }) => postJSON<{ ok: boolean; message: string }>("/api/engine/start", body),
  stopEngine: () => postJSON<{ ok: boolean; message: string }>("/api/engine/stop"),
  restartEngine: (body: { symbols: string; track: string; interval_seconds: number }) => postJSON<{ ok: boolean; message: string }>("/api/engine/restart", body),

  // Logs
  tailLog: (offset: number) => getJSON<LogTailResponse>(`/api/logs/tail?offset=${offset}`),
  getLogStats: () => getJSON<LogStats>("/api/logs/stats"),
  clearLog: () => postJSON<{ new_offset: number }>("/api/logs/clear"),
};
