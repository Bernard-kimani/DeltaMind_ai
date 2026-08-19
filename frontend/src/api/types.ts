export const TRACKS = ["track1_alpha_spreads", "track2_volatility_events", "track3_hedging", "track4_income_wheel"] as const;
export type Track = (typeof TRACKS)[number];

export const TRACK_LABELS: Record<Track, string> = {
  track1_alpha_spreads: "Track 1 — Options Alpha",
  track2_volatility_events: "Track 2 — Volatility & Events",
  track3_hedging: "Track 3 — Hedging & Protection",
  track4_income_wheel: "Track 4 — Income & Overlay (Wheel)",
};

export const TRACK_SUMMARY: Record<Track, { structure: string; regime: string; metric: string }> = {
  track1_alpha_spreads: {
    structure: "Vertical debit spreads — buy 0.70Δ, sell 0.30Δ, 14 DTE",
    regime: "Strong trend / momentum",
    metric: "Signal conviction + Delta balance",
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
    structure: "The Wheel — 0.30Δ cash-secured puts → covered calls",
    regime: "Sideways / range-bound",
    metric: "Theta capture rate + assignment risk",
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
}

export interface EngineStatus {
  is_running: boolean;
  pid: number | null;
  started_at: string | null;
}

export interface EngineStats {
  uptime: string;
  total_cycles: number;
  approved_trades: number;
  rejected_cycles: number;
  last_decision_time: string | null;
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

export interface BacktestResult {
  trades: unknown[];
  total_pnl: number;
  win_rate: number;
  max_drawdown_pct: number;
}
