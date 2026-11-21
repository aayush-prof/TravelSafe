"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import { Search, X } from "lucide-react";

const CATEGORIES = [
  ["", "All topics"],
  ["crime", "Crime"],
  ["protest", "Protests & civil disruption"],
  ["accident", "Accidents & service disruption"],
  ["disaster", "Disasters & public health"],
  ["weather", "Weather"],
  ["positive", "Positive / civic"],
  ["neutral", "General news"],
] as const;

const FILTER_KEYS = ["q", "category", "severity", "days", "status", "sort"];

function Select({
  id,
  label,
  value,
  onChange,
  options,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: readonly (readonly [string, string])[];
}) {
  return (
    <div className="min-w-0">
      <label htmlFor={id} className="mb-1 block text-[13px] text-muted-foreground">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 w-full rounded-md border border-input bg-card px-2.5 text-sm text-foreground focus:border-ring focus:outline-none"
      >
        {options.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
    </div>
  );
}

/** Filters live in the URL, so they survive reloads and work with the server-rendered list. */
export function FilterToolbar({ counts }: { counts: Record<string, number> }) {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const [pending, start] = useTransition();
  const [q, setQ] = useState(sp.get("q") ?? "");

  const set = (key: string, value: string) => {
    const p = new URLSearchParams(sp.toString());
    if (value) p.set(key, value);
    else p.delete(key);
    p.delete("page");
    start(() => router.replace(`${pathname}?${p.toString()}`, { scroll: false }));
  };

  useEffect(() => {
    if ((sp.get("q") ?? "") === q) return;
    const t = setTimeout(() => set("q", q.trim()), 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const active = FILTER_KEYS.some((k) => sp.get(k));
  const reset = () => {
    const p = new URLSearchParams(sp.toString());
    FILTER_KEYS.forEach((k) => p.delete(k));
    p.delete("page");
    setQ("");
    start(() => router.replace(`${pathname}?${p.toString()}`, { scroll: false }));
  };

  const categoryOptions = CATEGORIES.map(
    ([v, l]) => [v, v ? `${l} (${counts[v] ?? 0})` : l] as const,
  );

  return (
    <div aria-busy={pending} className="grid grid-cols-2 gap-3 lg:grid-cols-[minmax(0,1.6fr)_repeat(4,minmax(0,1fr))_auto] lg:items-end">
      <div className="relative col-span-2 lg:col-span-1">
        <label htmlFor="ev-q" className="mb-1 block text-[13px] text-muted-foreground">
          Search
        </label>
        <Search aria-hidden className="pointer-events-none absolute bottom-3 left-3 size-4 text-muted-foreground" />
        <input
          id="ev-q"
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Headline or source"
          className="h-9 w-full rounded-md border border-input bg-card pr-3 pl-9 text-sm focus:border-ring focus:outline-none"
        />
      </div>
      <Select id="ev-cat" label="Topic" value={sp.get("category") ?? ""} onChange={(v) => set("category", v)} options={categoryOptions} />
      <Select
        id="ev-sev"
        label="Severity"
        value={sp.get("severity") ?? ""}
        onChange={(v) => set("severity", v)}
        options={[
          ["", "Any"],
          ["minor", "Minor or worse"],
          ["serious", "Serious or worse"],
          ["severe", "Severe only"],
        ]}
      />
      <Select
        id="ev-days"
        label="Period"
        value={sp.get("days") ?? ""}
        onChange={(v) => set("days", v)}
        options={[
          ["", "All analysed"],
          ["2", "Last 48 hours"],
          ["7", "Last 7 days"],
          ["30", "Last 30 days"],
        ]}
      />
      <Select
        id="ev-status"
        label="Show"
        value={sp.get("status") ?? "counted"}
        onChange={(v) => set("status", v === "counted" ? "" : v)}
        options={[
          ["counted", "Counted reports"],
          ["all", "All reports"],
          ["not_counted", "Not counted"],
          ["context", "Positive and general"],
        ]}
      />
      {active ? (
        <button
          type="button"
          onClick={reset}
          className="col-span-2 inline-flex h-9 items-center justify-center gap-1.5 rounded-md px-3 text-sm font-medium text-accent-foreground hover:bg-secondary lg:col-span-1"
        >
          <X aria-hidden className="size-4" />
          Clear filters
        </button>
      ) : (
        <span className="hidden lg:block" />
      )}
    </div>
  );
}

export function SortSelect() {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  return (
    <label className="flex items-center gap-2 text-sm text-muted-foreground">
      Sort by
      <select
        value={sp.get("sort") ?? "relevance"}
        onChange={(e) => {
          const p = new URLSearchParams(sp.toString());
          if (e.target.value === "relevance") p.delete("sort");
          else p.set("sort", e.target.value);
          p.delete("page");
          router.replace(`${pathname}?${p.toString()}`, { scroll: false });
        }}
        className="h-9 rounded-md border border-input bg-card px-2 text-sm text-foreground"
      >
        <option value="relevance">Most relevant</option>
        <option value="date">Most recent</option>
        <option value="severity">Most severe</option>
      </select>
    </label>
  );
}
