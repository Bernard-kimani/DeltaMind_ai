import { useEffect, useMemo, useRef, useState } from "react";

/** Searchable multi-select for the engine's symbol watchlist. Replaces a
 * plain CSV text field + a separate "Load Curated Watchlist" button — the
 * curated list lives inside the dropdown itself (as a one-click "select
 * all" plus browsable/searchable categories), and typing a ticker not in
 * the list still adds it, so nothing the old free-text field could do is
 * lost. */
export function SymbolPicker({
  value,
  onChange,
  categories,
}: {
  value: string;
  onChange: (csv: string) => void;
  categories: Record<string, string[]>;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const selected = useMemo(() => value.split(",").map((s) => s.trim().toUpperCase()).filter(Boolean), [value]);
  const groups = useMemo(() => Object.entries(categories), [categories]);
  const allCurated = useMemo(() => Object.values(categories).flat(), [categories]);

  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const setSelected = (next: string[]) => onChange(next.join(","));
  const toggle = (sym: string) => setSelected(selected.includes(sym) ? selected.filter((s) => s !== sym) : [...selected, sym]);
  const addCustom = (raw: string) => {
    const sym = raw.trim().toUpperCase();
    if (!sym || selected.includes(sym)) return;
    setSelected([...selected, sym]);
    setQuery("");
  };

  const q = query.trim().toUpperCase();

  return (
    <div ref={rootRef} className="relative flex flex-col gap-1.5 text-sm">
      <span className="text-[11px] tracking-[0.08em] uppercase text-text-secondary">Symbols</span>
      <div
        className="flex flex-wrap items-center gap-1.5 bg-surface border border-border px-2 py-1.5 cursor-text transition-colors focus-within:border-accent focus-within:ring-1 focus-within:ring-accent/40"
        onClick={() => { setOpen(true); inputRef.current?.focus(); }}
      >
        {selected.map((sym) => (
          <span key={sym} className="flex items-center gap-1 bg-surface-alt px-2 py-0.5 text-xs font-mono tabular-nums text-text-primary">
            {sym}
            <button type="button" onClick={(e) => { e.stopPropagation(); toggle(sym); }} className="text-text-secondary hover:text-error" aria-label={`Remove ${sym}`}>
              ×
            </button>
          </span>
        ))}
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "Enter") { e.preventDefault(); addCustom(query); }
            if (e.key === "Backspace" && !query && selected.length) toggle(selected[selected.length - 1]);
          }}
          placeholder={selected.length ? "" : "Search or type a symbol…"}
          className="flex-1 min-w-24 bg-transparent text-sm font-mono tabular-nums text-text-primary placeholder:text-text-disabled focus:outline-none py-0.5"
        />
      </div>

      {open && (
        <div className="absolute top-full left-0 right-0 z-20 mt-1 max-h-72 overflow-y-auto bg-surface border border-border shadow-lg">
          <button
            type="button"
            onClick={() => { setSelected(allCurated); setOpen(false); }}
            className="w-full text-left px-3 py-2 text-[11px] font-semibold tracking-wide uppercase text-accent hover:bg-surface-alt border-b border-divider/15"
          >
            Load curated watchlist ({allCurated.length})
          </button>
          {groups.map(([category, symbols]) => {
            const visible = symbols.filter((sym) => !q || sym.includes(q));
            if (!visible.length) return null;
            return (
              <div key={category}>
                <div className="px-3 pt-2 pb-1 text-[10px] tracking-widest uppercase text-text-disabled">{category}</div>
                {visible.map((sym) => (
                  <button
                    key={sym}
                    type="button"
                    onClick={() => toggle(sym)}
                    className={`w-full flex items-center justify-between px-3 py-1.5 text-xs font-mono tabular-nums hover:bg-surface-alt ${selected.includes(sym) ? "text-accent" : "text-text-primary"}`}
                  >
                    {sym}
                    {selected.includes(sym) && <span>✓</span>}
                  </button>
                ))}
              </div>
            );
          })}
          {q && !allCurated.includes(q) && (
            <button
              type="button"
              onClick={() => addCustom(q)}
              className="w-full text-left px-3 py-2 text-xs font-mono text-text-secondary hover:bg-surface-alt border-t border-divider/15"
            >
              Add “{q}” (not in curated list)
            </button>
          )}
        </div>
      )}
    </div>
  );
}
