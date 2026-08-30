import { ArrowRight } from "lucide-react";

/** Real hero photograph (a pre-dawn Lower Manhattan skyline, /public/alpaca-landing.*)
 * replaces the old abstract instrument-panel placeholder now that one exists.
 * Text over a photo needs its own fixed light-on-dark treatment regardless of
 * the app's own light/dark theme toggle — a scrim (not the theme's --ground
 * variable) carries contrast here, same convention as most marketing heroes. */
function HeroPhoto() {
  return (
    <>
      <picture>
        <source srcSet="/alpaca-landing.webp" type="image/webp" />
        <img
          src="/alpaca-landing.jpg"
          alt=""
          aria-hidden="true"
          className="absolute inset-0 h-full w-full object-cover"
          fetchPriority="high"
          decoding="async"
        />
      </picture>
      {/* Uniform tint first (keeps the header/logo readable against the bright
          horizon glow), then a stronger bottom-up gradient under the CTA copy. */}
      <div className="absolute inset-0 bg-black/35" aria-hidden="true" />
      <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/25 to-transparent" aria-hidden="true" />
      <div className="absolute inset-0 bg-gradient-to-b from-black/40 via-transparent to-transparent" aria-hidden="true" />
    </>
  );
}

export default function LandingPage({ onEnter }: { onEnter: () => void }) {
  return (
    <div className="relative flex h-screen flex-col overflow-hidden bg-black text-white">
      <HeroPhoto />

      <header className="relative z-10 shrink-0 px-6 py-3.5 md:px-16">
        <span className="text-[20px] tracking-wide" style={{ fontFamily: "var(--font-logo)" }}>
          <span className="text-accent">Delta</span>
          <span className="text-white">Mind</span> <span className="text-accent">AI</span>
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
          <p className="mt-6 max-w-md text-[15px] leading-relaxed text-white/70">
            A live options pipeline runs Greeks, IV percentile, and sentiment through a deterministic risk gate
            before a single multi-leg order reaches Alpaca. Every decision — approved or rejected — ships with
            its own reasoning and a full audit trail.
          </p>
          <div className="mt-9 flex flex-wrap items-center gap-4">
            <button
              onClick={onEnter}
              className="inline-flex items-center gap-2 rounded-full bg-accent px-7 py-3.5 text-[13px] font-semibold uppercase tracking-[0.08em] text-text-on-accent transition-all duration-150 hover:bg-accent-hover active:scale-[0.98] active:bg-accent-pressed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-black"
            >
              Console
              <ArrowRight size={15} />
            </button>
          </div>
        </div>
      </main>

      <footer className="relative z-10 grid shrink-0 grid-cols-3 items-center px-6 py-4 text-[11px] text-white/50 md:px-16">
        <span className="justify-self-start">© {new Date().getFullYear()} DeltaMind AI</span>
        <span className="justify-self-center text-center">Paper trading only. Nothing here is investment advice.</span>
        <span aria-hidden="true" />
      </footer>
    </div>
  );
}
