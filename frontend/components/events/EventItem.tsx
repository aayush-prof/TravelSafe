import { ChevronDown, ExternalLink, Layers } from "lucide-react";

import { date, relative } from "@/lib/format";
import type { EventItem as Ev, Severity } from "@/lib/types";

const SEV: Record<Severity, { n: number; tone: string; text: string }> = {
  severe: { n: 3, tone: "bg-high", text: "text-high" },
  serious: { n: 2, tone: "bg-elevated", text: "text-elevated" },
  minor: { n: 1, tone: "bg-guarded", text: "text-guarded" },
  none: { n: 0, tone: "bg-border", text: "text-muted-foreground" },
  positive: { n: 0, tone: "bg-border", text: "text-low" },
};

/** Severity: three bars plus a word, so it never relies on colour alone. */
export function SeverityTag({ severity, label }: { severity: Severity; label: string }) {
  const s = SEV[severity];
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <span aria-hidden className="inline-flex gap-[3px]">
        {[1, 2, 3].map((i) => (
          <span key={i} className={`h-3 w-[5px] rounded-[2px] ${i <= s.n ? s.tone : "bg-border"}`} />
        ))}
      </span>
      <span className={`text-[13px] font-medium ${s.text}`}>{label}</span>
    </span>
  );
}

/**
 * Event list item. Title, category, source and age are always visible; the
 * summary is optional; reliability details are behind "Details".
 */
export function EventItem({ e, showSummary = true, showCategory = true }: { e: Ev; showSummary?: boolean; showCategory?: boolean }) {
  const dim = e.status === "not_counted";
  return (
    <li className="border-b border-border py-4 first:pt-0 last:border-b-0 last:pb-0">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className={`text-[15px] leading-snug font-medium break-words ${dim ? "text-muted-foreground" : "text-foreground"}`}>{e.title}</h3>
          <p className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[13px] text-muted-foreground">
            {showCategory ? <span className="text-secondary-foreground">{e.category_label}</span> : null}
            <span>{e.source}</span>
            <span title={date(e.published_at, { time: true }) || undefined}>{relative(e.age_hours)}</span>
            {e.report_count > 1 ? (
              <span className="inline-flex items-center gap-1 text-accent-foreground">
                <Layers aria-hidden className="size-3.5" />
                {e.report_count} reports, one incident
              </span>
            ) : null}
            {e.origin === "sample" ? <span className="text-guarded">Sample</span> : null}
          </p>
        </div>
        {e.severity !== "none" ? <SeverityTag severity={e.severity} label={e.severity_label} /> : null}
      </div>
      {showSummary && e.summary ? <p className="mt-2 line-clamp-2 max-w-3xl text-sm text-secondary-foreground">{e.summary}</p> : null}
      <details className="group mt-2">
        <summary className="inline-flex cursor-pointer items-center gap-1 rounded text-[13px] font-medium text-accent-foreground hover:underline">
          Details
          <ChevronDown aria-hidden className="size-3.5 transition-transform group-open:rotate-180" />
        </summary>
        <div className="mt-2 max-w-3xl space-y-2 rounded-md bg-secondary px-4 py-3 text-sm text-secondary-foreground">
          <p className={e.status === "counted" ? "text-foreground" : ""}>{e.status_note}</p>
          {!showSummary && e.summary ? <p>{e.summary}</p> : null}
          <p className="text-[13px] text-muted-foreground">
            {e.confidence_label}. Location: {e.location_label.toLowerCase()}.
            {e.subtype_label ? ` Type: ${e.subtype_label.toLowerCase()}.` : ""}
            {e.published_at ? ` Published ${date(e.published_at, { time: true })}.` : ""}
          </p>
          {e.notes.length ? <p className="text-[13px] text-muted-foreground">{e.notes.join(". ")}.</p> : null}
          {e.sources.length > 1 ? <p className="text-[13px] text-muted-foreground">Reported by {e.sources.join(", ")}.</p> : null}
          {e.url ? (
            <a
              href={e.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-[13px] font-medium text-accent-foreground hover:underline"
            >
              Read the original report
              <ExternalLink aria-hidden className="size-3.5" />
              <span className="sr-only">(opens in a new tab)</span>
            </a>
          ) : null}
        </div>
      </details>
    </li>
  );
}

export function EventList({ events, showSummary = true, showCategory = true }: { events: Ev[]; showSummary?: boolean; showCategory?: boolean }) {
  return (
    <ul>
      {events.map((e) => (
        <EventItem key={e.id} e={e} showSummary={showSummary} showCategory={showCategory} />
      ))}
    </ul>
  );
}
