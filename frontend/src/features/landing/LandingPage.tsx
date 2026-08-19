import { ArrowRight } from "lucide-react";

/** No hero photo asset (unlike a design this was styled after) — an
 * abstract instrument-panel backdrop instead: a faint chart grid plus a
 * single drawn "price line" in the accent color, kept low-opacity so it
 * reads as texture, not a competing focal point. */
function TerminalBackdrop() {
  return (
    <svg className="absolute inset-0 h-full w-full" preserveAspectRatio="none" viewBox="0 0 1200 800" aria-hidden="true">
      <defs>
        <pattern id="grid" width="60" height="60" patternUnits="userSpaceOnUse">
          <path d="M60 0 L0 0 0 60" fill="none" stroke="var(--border)" strokeWidth="1" />
        </pattern>
        <linearGradient id="fade" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--ground)" stopOpacity="0" />
          <stop offset="100%" stopColor="var(--ground)" stopOpacity="1" />
        </linearGradient>
      </defs>
      <rect width="1200" height="800" fill="url(#grid)" opacity="0.4" />
      <polyline
        points="0,560 120,540 220,580 340,470 460,510 560,380 680,420 800,300 920,340 1040,220 1200,260"
        fill="none"
        stroke="var(--accent)"
        strokeWidth="2"
        opacity="0.35"
      />
      <rect width="1200" height="800" fill="url(#fade)" />
    </svg>
  );
}

export default function LandingPage({ onEnter }: { onEnter: () => void }) {
  return (
    <div className="relative flex h-screen flex-col overflow-hidden bg-ground text-text-primary">
      <TerminalBackdrop />
      <div
        className="pointer-events-none absolute left-1/2 top-1/3 h-[600px] w-[900px] -translate-x-1/2 -translate-y-1/2 rounded-full blur-3xl"
        style={{ background: "var(--accent-glow)" }}
      />

      <header className="relative z-10 shrink-0 px-6 py-3.5 md:px-16">
        <span className="text-[20px] tracking-wide" style={{ fontFamily: "var(--font-logo)" }}>
          <span className="text-accent">Delta</span>
          <span className="text-text-primary">Mind</span> <span className="text-accent">AI</span>
        </span>
      </header>

      <main className="relative z-10 flex flex-1 items-end px-6 pb-16 md:px-16 md:pb-24">
        <div className="max-w-2xl">
          <p className="mb-4 text-[11px] font-mono font-semibold uppercase tracking-[0.22em] text-accent">
            Multi-Agent Options Desk · Alpaca Paper Trading
          </p>
          <h1 className="text-[40px] font-medium leading-[1.1] md:text-[52px]" style={{ fontFamily: "var(--font-display)" }}>
            It Reads Every Greek.
            <br />
            <span className="font-semibold italic text-accent">It Trades Only What Adds Up.</span>
          </h1>
          <p className="mt-6 max-w-md text-[15px] leading-relaxed text-text-secondary">
            A live options pipeline runs Greeks, IV percentile, and sentiment through a deterministic risk gate
            before a single multi-leg order reaches Alpaca. Every decision — approved or rejected — ships with
            its own reasoning and a full audit trail.
          </p>
          <div className="mt-9 flex flex-wrap items-center gap-4">
            <button
              onClick={onEnter}
              className="inline-flex items-center gap-2 rounded-full bg-accent px-7 py-3.5 text-[13px] font-semibold uppercase tracking-[0.08em] text-text-on-accent transition-all duration-150 hover:bg-accent-hover active:scale-[0.98] active:bg-accent-pressed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-ground"
            >
              Console
              <ArrowRight size={15} />
            </button>
          </div>
        </div>
      </main>

      <footer className="relative z-10 grid shrink-0 grid-cols-3 items-center px-6 py-4 text-[11px] text-text-disabled md:px-16">
        <span className="justify-self-start">© {new Date().getFullYear()} DeltaMind AI</span>
        <span className="justify-self-center text-center">Paper trading only. Nothing here is investment advice.</span>
        <span aria-hidden="true" />
      </footer>
    </div>
  );
}
