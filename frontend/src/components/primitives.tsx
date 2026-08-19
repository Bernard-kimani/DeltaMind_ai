import type { ButtonHTMLAttributes, HTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";
import type { AgentDecision, Position } from "../api/types";

// Shared layout/visual primitives for DeltaMind's dashboard. Structural
// philosophy: content sits directly on the window background; Section is
// the workhorse (heading + hairline divider + content), Card is reserved
// for genuinely repeating self-contained units. Section titles render as
// small tracked uppercase labels — "everything is labeled, nothing is
// decorated," the vernacular of a trading terminal, not a stylistic flourish.

export function Section({ title, action, children, className = "" }: { title: ReactNode; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`mb-7 ${className}`}>
      <div className="flex items-center justify-between mb-2">
        <h2 className="flex items-center gap-2 text-[11px] font-semibold tracking-[0.14em] uppercase text-text-secondary">{title}</h2>
        {action}
      </div>
      <div className="h-px bg-divider/15 mb-3.5" />
      <div>{children}</div>
    </section>
  );
}

export function Divider({ vertical = false, className = "" }: { vertical?: boolean; className?: string }) {
  return vertical ? <div className={`w-px bg-divider/15 self-stretch ${className}`} /> : <div className={`h-px bg-divider/15 ${className}`} />;
}

/** `square` opts out of the card's default 10px radius — for popups/modals,
 * which read as precise, dialog-like overlays rather than the persistent
 * "financial terminal" surfaces the rounded corner is meant for elsewhere. */
export function Card({ children, className = "", square = false, ...props }: HTMLAttributes<HTMLDivElement> & { children: ReactNode; className?: string; square?: boolean }) {
  return (
    <div {...props} className={`bg-surface border border-border ${square ? "" : "rounded-card"} ${className}`}>
      {children}
    </div>
  );
}

const buttonVariants = {
  primary: "bg-accent hover:bg-accent-hover active:bg-accent-pressed text-text-on-accent",
  success: "bg-success hover:brightness-110 text-text-on-accent",
  danger: "bg-error hover:brightness-110 text-text-on-accent",
  warning: "bg-warning hover:brightness-110 text-text-on-accent",
  neutral: "bg-surface-alt hover:brightness-95 dark:hover:brightness-125 text-text-primary",
  ghost: "bg-transparent hover:bg-surface-alt text-text-primary border border-border",
} as const;

export function Button({
  variant = "neutral", pill = false, className = "", children, ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: keyof typeof buttonVariants; pill?: boolean }) {
  return (
    <button
      {...props}
      className={`px-4 py-2 text-xs font-semibold tracking-wide uppercase transition-all duration-150 disabled:opacity-35 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-ground active:scale-[0.98] ${pill ? "rounded-full" : ""} ${buttonVariants[variant]} ${className}`}
    >
      {children}
    </button>
  );
}

const fieldBase = "bg-surface border border-border px-3 py-1.5 text-sm text-text-primary placeholder:text-text-disabled transition-colors focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/40";

export function TextField({ label, mono = false, className = "", ...props }: InputHTMLAttributes<HTMLInputElement> & { label?: string; mono?: boolean }) {
  return (
    <label className="flex flex-col gap-1.5 text-sm">
      {label && <span className="text-[11px] tracking-[0.08em] uppercase text-text-secondary">{label}</span>}
      <input {...props} className={`${fieldBase} ${mono ? "font-mono tabular-nums" : ""} ${className}`} />
    </label>
  );
}

export function Select({ label, className = "", children, ...props }: SelectHTMLAttributes<HTMLSelectElement> & { label?: string }) {
  return (
    <label className="flex flex-col gap-1.5 text-sm">
      {label && <span className="text-[11px] tracking-[0.08em] uppercase text-text-secondary">{label}</span>}
      <span className="relative inline-block">
        <select {...props} className={`${fieldBase} appearance-none pr-8 cursor-pointer ${className}`}>
          {children}
        </select>
        <svg className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-text-secondary" width="10" height="6" viewBox="0 0 10 6" fill="none">
          <path d="M1 1L5 5L9 1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
    </label>
  );
}

export function StatTile({ label, value, tone = "primary" }: { label: string; value: string; tone?: "primary" | "success" | "warning" | "accent" }) {
  const toneClass = { primary: "text-text-primary", success: "text-success", warning: "text-warning", accent: "text-accent" }[tone];
  return (
    <Card className="p-3.5">
      <div className="text-[10px] tracking-widest uppercase text-text-secondary">{label}</div>
      <div className={`text-base font-mono tabular-nums font-medium mt-1.5 ${toneClass}`}>{value}</div>
    </Card>
  );
}

/** RUNNING/STOPPED-style status dot. Motion (a soft pulse ring) is reserved
 * for the one truly live signal in the app — everything else stays still.
 * `pulse` opts a given usage out of that ring entirely (e.g. a badge that
 * should read as calmly "on" rather than actively blinking). */
export function StatusDot({ live, color, pulse = true }: { live: boolean; color: "success" | "error" | "neutral"; pulse?: boolean }) {
  const hex = color === "success" ? "var(--success)" : color === "error" ? "var(--error)" : "var(--text-disabled)";
  return (
    <span
      className={`inline-block h-2 w-2 rounded-full ${live && pulse ? "animate-pulse-ring" : ""}`}
      style={{ backgroundColor: hex, ["--pulse-color" as string]: hex }}
    />
  );
}

export function Spinner({ className = "" }: { className?: string }) {
  return <div className={`inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent ${className}`} />;
}

/** One compact, single-line row in the decision-history list — mirrors a
 * trading terminal's fill/signal tape. TRADE = risk gate approved and an
 * order was dispatched; REJECTED = the risk gate vetoed a proposal (reason
 * shown inline); WAIT = the cycle ran but no setup qualified this pass. */
export function DecisionRow({ decision, onClick }: { decision: AgentDecision; onClick: () => void }) {
  const { symbol, track, thesis, risk_approved, risk_rejection_reason, sentiment_score, created_at } = decision;
  const style =
    risk_approved === true
      ? { icon: "▲", color: "text-success", label: "TRADE" }
      : risk_approved === false
        ? { icon: "▼", color: "text-error", label: "REJECTED" }
        : { icon: "■", color: "text-signal-wait", label: "WAIT" };

  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-4 py-2 first:pt-0 last:pb-0 text-left hover:bg-surface-alt/50 transition-colors focus-visible:outline-none focus-visible:bg-surface-alt/50"
    >
      <span className={`text-xs font-semibold tracking-wide shrink-0 whitespace-nowrap ${style.color}`}>
        {style.icon} {style.label} <span className="font-mono text-text-primary">{symbol}</span>
      </span>
      <span className="flex-1 min-w-0 truncate text-[11px] font-mono tabular-nums text-text-secondary">
        {risk_approved === false ? risk_rejection_reason : thesis || track}
      </span>
      {sentiment_score != null && (
        <span className="shrink-0 text-[10px] font-semibold tracking-widest uppercase text-warning">{sentiment_score >= 0 ? "+" : ""}{sentiment_score.toFixed(2)}</span>
      )}
      <span className="shrink-0 text-[11px] font-mono tabular-nums text-text-secondary">{new Date(created_at).toLocaleTimeString()}</span>
    </button>
  );
}

/** One row in the live open-positions list, sourced straight from the
 * Alpaca account — real-time floating P&L, not a decision record. */
export function PositionRow({ symbol, qty, side, market_value, unrealized_pl }: Position) {
  const pl = Number(unrealized_pl);
  const plColor = pl > 0 ? "text-success" : pl < 0 ? "text-error" : "text-text-secondary";
  return (
    <div className="py-2.5 first:pt-0 last:pb-0 flex items-center justify-between gap-3">
      <div className="flex flex-col gap-0.5 min-w-0">
        <span className="text-xs font-semibold tracking-wide">
          <span className="font-mono text-text-primary">{symbol}</span>{" "}
          <span className="font-mono text-text-secondary font-normal">{side} · {qty}</span>
        </span>
        <span className="text-[11px] font-mono tabular-nums text-text-secondary truncate">Market value ${market_value}</span>
      </div>
      <span className={`text-sm font-mono tabular-nums font-semibold shrink-0 ${plColor}`}>
        {pl >= 0 ? "+" : ""}{pl.toFixed(2)}
      </span>
    </div>
  );
}
