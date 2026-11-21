"use client";

import { useState } from "react";
import { BellRing, ChevronDown, ExternalLink } from "lucide-react";

import { LevelBadge } from "@/components/common/page";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { LEVEL_COLOR, date, levelVariant, since } from "@/lib/format";
import type { Factor } from "@/lib/types";
import { cn } from "@/lib/utils";

// Level bands on a 0–100 intensity scale (backend thresholds 0.15 / 0.35 / 0.60).
const BANDS = [
  { from: 0, to: 15, key: "low" },
  { from: 15, to: 35, key: "guarded" },
  { from: 35, to: 60, key: "elevated" },
  { from: 60, to: 100, key: "high" },
] as const;

const RELIABILITY: Record<Factor["reliability"], string> = {
  good: "Good evidence",
  limited: "Limited evidence",
  none: "No evidence",
};

/**
 * The factor meter. An assessed factor fills the banded track up to its
 * intensity; a factor that couldn't be assessed shows a hatched track and the
 * words "Not assessed" – it is never drawn as an empty (= safe) bar.
 */
function Meter({ value, level }: { value: number | null; level: Factor["level"] }) {
  if (value === null) {
    return (
      <div className="hatch relative h-2.5 w-full rounded-full" role="img" aria-label="Not assessed: no usable data" />
    );
  }
  const v = Math.max(2, Math.min(100, value));
  return (
    <div className="relative h-2.5 w-full" role="img" aria-label={`Intensity ${value} of 100`}>
      <div className="absolute inset-0 flex gap-[2px] overflow-hidden rounded-full">
        {BANDS.map((b) => (
          <span key={b.key} className="h-full bg-secondary" style={{ width: `${b.to - b.from}%` }} />
        ))}
      </div>
      <div
        className="absolute inset-y-0 left-0 rounded-full"
        style={{ width: `${v}%`, background: LEVEL_COLOR[levelVariant(level)] }}
      />
    </div>
  );
}

function FactorRow({ f, personal }: { f: Factor; personal: boolean }) {
  const [open, setOpen] = useState(false);
  const level = personal ? f.persona_level : f.level;
  const value = personal ? f.persona_intensity : f.intensity;
  return (
    <Collapsible open={open} onOpenChange={setOpen} asChild>
      <li className="py-3">
        <CollapsibleTrigger className="group grid w-full grid-cols-[minmax(0,9.5rem)_minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 rounded-md text-left focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none max-sm:grid-cols-[1fr_auto]">
          <span className="flex items-center gap-1.5 text-sm font-medium">
            {f.label}
            {f.raised_by_alert ? <BellRing aria-label="Raised by an alert" className="size-3.5 text-high" /> : null}
          </span>
          <span className="max-sm:order-last max-sm:col-span-2">
            <Meter value={value} level={level} />
          </span>
          <span className="flex items-center gap-2">
            <LevelBadge level={level} />
            <ChevronDown aria-hidden className="size-4 text-muted-foreground transition-transform group-data-[state=open]:rotate-180" />
          </span>
        </CollapsibleTrigger>
        <p className={cn("mt-1.5 text-[13px] text-muted-foreground sm:ml-[calc(9.5rem+1rem)]", !f.assessed && "text-foreground/75")}>
          {f.summary}
        </p>
        <CollapsibleContent className="data-[state=open]:animate-in data-[state=open]:fade-in-0">
          <div className="mt-3 grid gap-4 rounded-lg bg-secondary/70 p-4 text-[13px] sm:ml-[calc(9.5rem+1rem)] md:grid-cols-2">
            <dl className="space-y-2">
              <div>
                <dt className="text-muted-foreground">What it covers</dt>
                <dd>{f.definition}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Evidence</dt>
                <dd>
                  {RELIABILITY[f.reliability]}
                  {f.reliability_note ? `: ${f.reliability_note}` : ""}
                </dd>
              </div>
              {f.sources.length ? (
                <div>
                  <dt className="text-muted-foreground">Sources</dt>
                  <dd>{f.sources.join(", ")}</dd>
                </div>
              ) : null}
              {f.time_window ? (
                <div>
                  <dt className="text-muted-foreground">Time window</dt>
                  <dd>{f.time_window}</dd>
                </div>
              ) : null}
              {f.geo_match ? (
                <div>
                  <dt className="text-muted-foreground">Geographic match</dt>
                  <dd>{f.geo_match}</dd>
                </div>
              ) : null}
              {f.updated_at ? (
                <div>
                  <dt className="text-muted-foreground">Latest evidence</dt>
                  <dd title={date(f.updated_at, { time: true })}>{since(f.updated_at)}</dd>
                </div>
              ) : null}
              {f.persona_note ? (
                <div>
                  <dt className="text-muted-foreground">Traveller profile</dt>
                  <dd>{f.persona_note}</dd>
                </div>
              ) : null}
            </dl>
            <div>
              <p className="text-muted-foreground">Strongest evidence</p>
              {f.evidence.length ? (
                <ul className="mt-1 space-y-2">
                  {f.evidence.map((e, i) => (
                    <li key={i} className="leading-snug">
                      {e.url ? (
                        <a href={e.url} target="_blank" rel="noopener noreferrer" className="hover:underline">
                          {e.text}
                          <ExternalLink aria-hidden className="ml-1 inline size-3 align-baseline" />
                          <span className="sr-only">(opens in a new tab)</span>
                        </a>
                      ) : (
                        e.text
                      )}
                      <span className="block text-xs text-muted-foreground">
                        {e.source}
                        {e.when ? `, ${since(e.when)}` : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1">{f.assessed ? "Nothing notable in the current data." : "No usable data for this factor right now."}</p>
              )}
            </div>
          </div>
        </CollapsibleContent>
      </li>
    </Collapsible>
  );
}

export function FactorProfile({ factors, personaName }: { factors: Factor[]; personaName: string }) {
  const [view, setView] = useState("general");
  return (
    <div>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-3">
        <Tabs value={view} onValueChange={setView}>
          <TabsList aria-label="Weighting">
            <TabsTrigger value="general">General</TabsTrigger>
            <TabsTrigger value="personal">For {personaName.toLowerCase()} travellers</TabsTrigger>
          </TabsList>
        </Tabs>
        <ul aria-label="Scale" className="flex items-center gap-3 text-xs text-muted-foreground">
          {(["low", "guarded", "elevated", "high"] as const).map((k) => (
            <li key={k} className="flex items-center gap-1">
              <span aria-hidden className="size-2 rounded-full" style={{ background: LEVEL_COLOR[k] }} />
              {k[0]!.toUpperCase() + k.slice(1)}
            </li>
          ))}
          <li className="flex items-center gap-1">
            <span aria-hidden className="hatch size-2.5 rounded-full" />
            Not assessed
          </li>
        </ul>
      </div>
      <ul className="divide-y">
        {factors.map((f) => (
          <FactorRow key={f.key} f={f} personal={view === "personal"} />
        ))}
      </ul>
    </div>
  );
}
