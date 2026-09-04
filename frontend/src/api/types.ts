export const TRACKS = ["track1_alpha_spreads", "track2_volatility_events", "track3_hedging", "track4_income_wheel", "track5_momentum_swing"] as const;
export type Track = (typeof TRACKS)[number];

export const TRACK_LABELS: Record<Track, string> = {
  track1_alpha_spreads: "Track 1 — Options Alpha",
  track2_volatility_events: "Track 2 — Volatility & Events",
  track3_hedging: "Track 3 — Hedging & Protection",
  track4_income_wheel: "Track 4 — Income & Overlay (Wheel)",
  // Internally built 2026-09-01 as a looser sibling of Track 1's gate
  // after both went a full live session without a trade -- submitted as
  // Track 1 itself, so the user-visible label reads as Track 1, not a
  // separate/secondary variant.
  track5_momentum_swing: "Track 1 — Momentum Swing",
};

export const TRACK_SUMMARY: Record<Track, { structure: string; regime: string; metric: string }> = {
  track1_alpha_spreads: {
    structure: "Single-leg long call/put, ~0.50Δ, 1-2 DTE — bar-close triggered",
    regime: "Strong trend / momentum (1m confluence + 15m trend)",
    metric: "RVOL + RSI band + VWAP + 15m EMA(50) trend",
  },
  track2_volatility_events: {
    structure: "Long strangle (IV%<25) or iron condor (IV%>85) around events",
    regime: "Pre-earnings / macro announcements",
    metric: "IV percentile vs. realized volatility",
  },
  track3_hedging: {
    structure: "Costless collar (5% OTM put / 3% OTM call) at >3.5% drawdown",
    regime: "High volatility / drawdowns",
    metric: "Portfolio drawdown + beta-weighted delta",
  },
  track4_income_wheel: {
    structure: "The Wheel — 0.25–0.30Δ cash-secured puts ↔ covered calls, ~21 DTE",
    regime: "Elevated IV + healthy pullback (200-EMA/RSI regime, CSP entries only)",
    metric: "IV percentile ≥ 45 + daily 200-EMA/RSI(14) regime",
  },
  track5_momentum_swing: {
    structure: "Single-leg long call/put, ~0.50Δ, 3-7 DTE — bar-close triggered, same shape as Track 1",
    regime: "Any 1h-trend-aligned 5m momentum crossover — deliberately thin gate",
    metric: "1h EMA(50) trend + 5m EMA(20) crossover, LLM given real decision weight (lower confidence bar than Track 1)",
  },
};

export interface Account {
  equity: string;
  cash: string;
  buying_power: string;
  portfolio_value: string;
}

export interface Position {
  symbol: string;
  qty: string;
  market_value: string;
  unrealized_pl: string;
  side: string;
}

export interface Trade {
  id: number;
  created_at: string;
  symbol: string;
  track: string | null;
  order: Record<string, unknown>;
  result: Record<string, unknown>;
  thesis: string;
}

export interface AgentDecision {
  id: number;
  created_at: string;
  symbol: string;
  track: string;
  sentiment_score: number | null;
  thesis: string | null;
  proposed_order: Record<string, unknown> | null;
  risk_approved: boolean | null;
  risk_rejection_reason: string | null;
}

export interface FlatConfig {
  llm_provider: "featherless" | "fireworks";
  llm_model: string;
  featherless_api_key: string;
  fireworks_api_key: string;
  temperature: string;
  symbols: string;
  track: Track;
  interval_seconds: string;
  sentiment_threshold: string;
  volume_ratio_min: string;
}

export interface EngineStatus {
  is_running: boolean;
  pid: number | null;
  started_at: string | null;
  auto_restart_count: number;
  circuit_breaker_tripped: boolean;
  last_crash_reason: string | null;
}

export interface EngineStats {
  uptime: string;
  total_cycles: number;
  approved_trades: number;
  rejected_cycles: number;
  last_decision_time: string | null;
}

export interface TrackPnlSummary {
  track: string;
  realized_pnl: number;
  unrealized_pnl: number;
  open_count: number;
  closed_count: number;
  win_count: number;
  matched_open_positions: number;
}

export interface PnlPoint {
  date: string;
  cumulative_pnl: number;
  trade_pnl: number;
  symbol: string;
}

export interface CompletedTrade {
  id: number;
  symbol: string;
  closed_at: string;
  realized_pnl: number;
  thesis: string | null;
}

export interface PerformanceMetrics {
  cumulative_pnl_series: PnlPoint[];
  sharpe_ratio: number | null;
  profit_factor: number | null;
  recovery_factor: number | null;
  max_drawdown: number;
  net_realized_pnl: number;
  closed_count: number;
  open_count: number;
  recent_completed_trades: CompletedTrade[];
  known_gaps: string[];
}

export interface TestResult {
  ok: boolean;
  message: string;
}

export interface LogTailResponse {
  lines: string[];
  new_offset: number;
}

export interface LogStats {
  total_entries: number;
  file_size_bytes: number;
}

export interface QualifyingEvent {
  timestamp: string;
  symbol: string;
  direction: string | null;
  detail: Record<string, unknown>;
}

export interface BacktestResult {
  trades: unknown[];
  total_pnl: number;
  win_rate: number;
  max_drawdown_pct: number;
  total_bars_evaluated?: number;
  qualified_count?: number;
  qualification_rate?: number;
  qualifying_events?: QualifyingEvent[];
  qualification_by_month?: Record<string, { evaluated: number; qualified: number }>;
  known_gaps?: string[];
  daily_prices?: { date: string; close: number }[];
  qualifying_dates?: string[];
}
