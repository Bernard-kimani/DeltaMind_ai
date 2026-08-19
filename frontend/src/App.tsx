import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Settings, X } from "lucide-react";
import { api } from "./api/client";
import { StatusDot } from "./components/primitives";
import ControlsPage from "./features/controls/ControlsPage";
import StrategiesPage from "./features/strategies/StrategiesPage";
import BacktestPage from "./features/backtest/BacktestPage";
import LogsPage from "./features/logs/LogsPage";
import LandingPage from "./features/landing/LandingPage";

const TABS = ["Controls", "Strategies", "Backtest", "Logs"] as const;
type Tab = (typeof TABS)[number];

export default function App() {
  // Every load starts at the landing gate — Console hands off into the
  // actual workspace below. No persistence on purpose: there's no login, so
  // "loading the url" and "entering the console" stay two distinct steps
  // every time, not just on a fresh session.
  const [view, setView] = useState<"landing" | "app">("landing");
  const [tab, setTab] = useState<Tab>("Controls");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [theme, setTheme] = useState<"dark" | "light">(() => (localStorage.getItem("deltamind_theme") === "light" ? "light" : "dark"));
  const [statusMessage, setStatusMessage] = useState("Ready");

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem("deltamind_theme", theme);
  }, [theme]);

  const { data: status } = useQuery({
    queryKey: ["engine-status"],
    queryFn: () => api.getEngineStatus(),
    refetchInterval: 3000,
  });

  const running = status?.is_running ?? false;

  if (view === "landing") {
    return <LandingPage onEnter={() => setView("app")} />;
  }

  return (
    <div className="flex h-screen flex-col bg-ground text-text-primary">
      <header className="grid grid-cols-3 items-center px-6 py-3.5 shrink-0">
        <button
          onClick={() => setView("landing")}
          className="justify-self-start text-[24px] leading-none tracking-wide focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-ground"
          style={{ fontFamily: "var(--font-logo)" }}
        >
          <span className="text-accent">Delta</span>
          <span className="text-text-primary">Mind</span> <span className="text-accent">AI</span>
        </button>

        <nav className="flex justify-self-center gap-6">
          {TABS.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`border-b-2 pb-1 text-[11px] font-semibold tracking-[0.14em] uppercase transition-colors focus-visible:outline-none ${
                tab === t ? "border-accent text-text-primary" : "border-transparent text-text-secondary hover:text-text-primary"
              }`}
            >
              {t}
            </button>
          ))}
        </nav>

        <button
          onClick={() => setDrawerOpen(true)}
          className="justify-self-end p-2 rounded-full text-text-secondary hover:text-text-primary hover:bg-surface-alt transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          aria-label="Settings"
        >
          <Settings size={18} />
        </button>
      </header>

      {/* Ticker rule — a thin line that carries the accent only while the
          agent loop is actually live, echoing the app's one real-time
          signal instead of decorating unconditionally. */}
      <div className={`h-px shrink-0 transition-colors duration-700 ${running ? "bg-accent" : "bg-divider/15"}`} />

      <main className="flex-1 overflow-auto p-6">
        {tab === "Controls" && <ControlsPage onStatusMessage={setStatusMessage} />}
        {tab === "Strategies" && <StrategiesPage onStatusMessage={setStatusMessage} />}
        {tab === "Backtest" && <BacktestPage onStatusMessage={setStatusMessage} />}
        {tab === "Logs" && <LogsPage onStatusMessage={setStatusMessage} />}
      </main>

      <footer className="flex items-center justify-between px-6 py-2.5 border-t border-border text-[11px] text-text-secondary shrink-0">
        <span>{statusMessage}</span>
        <span className="flex items-center gap-2 font-mono tracking-wide">
          <StatusDot live={running} color={running ? "success" : "error"} />
          {running ? "RUNNING" : "STOPPED"}
        </span>
      </footer>

      {drawerOpen && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div className="flex-1 bg-black/40" onClick={() => setDrawerOpen(false)} />
          <div className="w-80 bg-surface border-l border-border p-6 flex flex-col gap-5">
            <div className="flex items-center justify-between">
              <h2 className="text-[11px] font-semibold tracking-[0.14em] uppercase text-text-secondary">Settings</h2>
              <button onClick={() => setDrawerOpen(false)} aria-label="Close" className="text-text-secondary hover:text-text-primary">
                <X size={16} />
              </button>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm">Appearance</span>
              <button
                onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
                className="px-3 py-1.5 text-[11px] font-semibold tracking-wide uppercase bg-accent text-text-on-accent rounded-full transition hover:bg-accent-hover"
              >
                {theme === "dark" ? "Dark" : "Light"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
