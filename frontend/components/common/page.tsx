import type { ReactNode } from "react";
import { CircleAlert, CircleCheck, CircleDashed, CircleMinus, CircleSlash, Clock, FlaskConical, MapPinned } from "lucide-react";

import { ReportUpdated } from "@/components/shell/Shell";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { LEVEL_TEXT, STATE_TEXT, date, levelVariant, since } from "@/lib/format";
import type { DataMode, FactorLevel, Level, SourceState, SourceStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

export function PageHeader({
  title,
  description,
  updatedAt,
  children,
}: {
  title: string;
  description?: ReactNode;
  updatedAt?: string | null;
  children?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      {updatedAt !== undefined ? <ReportUpdated at={updatedAt} /> : null}
      <div className="min-w-0">
        <h1 className="text-[26px] leading-tight font-semibold tracking-tight">{title}</h1>
        {description ? <p className="mt-1 max-w-3xl text-[15px] text-muted-foreground">{description}</p> : null}
      </div>
      {children ? <div className="flex flex-wrap items-center gap-2">{children}</div> : null}
    </div>
  );
}

export function LevelBadge({ level, label, className }: { level: Level | FactorLevel; label?: string; className?: string }) {
  const v = levelVariant(level);
  return (
    <Badge variant={v} className={cn("gap-1.5", className)}>
      <span aria-hidden className={cn("size-1.5 rounded-full", v === "unknown" ? "border border-current" : "bg-current")} />
      {label ?? LEVEL_TEXT[level]}
    </Badge>
  );
}

export function SampleNotice({ mode }: { mode: DataMode }) {
  if (mode !== "sample") return null;
  return (
    <div role="note" className="mb-5 flex items-start gap-3 rounded-lg border border-guarded/25 bg-guarded-soft px-4 py-3 text-sm">
      <FlaskConical aria-hidden className="mt-0.5 size-4 shrink-0 text-guarded" />
      <p className="text-foreground/85">
        <span className="font-semibold text-guarded">Sample headlines.</span> Live news isn&apos;t available, so this page uses a
        labelled demonstration dataset. It does not describe current conditions, and live weather, air and hazard feeds are not
        mixed into it.
      </p>
    </div>
  );
}

export function EmptyState({ icon, title, children, className }: { icon?: ReactNode; title: string; children?: ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col items-center justify-center rounded-lg border border-dashed px-6 py-8 text-center", className)}>
      {icon ? <div className="mb-2 text-unknown">{icon}</div> : null}
      <p className="text-sm font-medium">{title}</p>
      {children ? <div className="mt-1 max-w-md text-[13px] text-muted-foreground">{children}</div> : null}
    </div>
  );
}

const STATE_ICON: Record<SourceState, { icon: typeof CircleCheck; cls: string }> = {
  available: { icon: CircleCheck, cls: "text-low" },
  stale: { icon: Clock, cls: "text-guarded" },
  broader_region: { icon: MapPinned, cls: "text-brand" },
  no_data: { icon: CircleDashed, cls: "text-unknown" },
  unavailable: { icon: CircleAlert, cls: "text-elevated" },
  not_configured: { icon: CircleSlash, cls: "text-unknown" },
  not_applicable: { icon: CircleMinus, cls: "text-unknown" },
  sample: { icon: FlaskConical, cls: "text-guarded" },
};

export function SourceState({ state }: { state: SourceState }) {
  const { icon: Icon, cls } = STATE_ICON[state];
  return (
    <span className={cn("inline-flex items-center gap-1 text-xs font-medium whitespace-nowrap", cls)}>
      <Icon aria-hidden className="size-3.5" />
      {STATE_TEXT[state]}
    </span>
  );
}

export function SourceList({ sources, dense = false }: { sources: SourceStatus[]; dense?: boolean }) {
  return (
    <ul className="divide-y">
      {sources.map((s) => (
        <li key={s.key} className={cn("flex flex-col gap-0.5", dense ? "py-2" : "py-3")}>
          <div className="flex items-center justify-between gap-3">
            <span className="text-sm font-medium">{s.name}</span>
            <SourceState state={s.state} />
          </div>
          {!dense || s.message ? (
            <p className="text-[13px] text-muted-foreground">
              {[s.provider && !["not_configured", "unavailable"].includes(s.state) ? s.provider : null,
                s.updated_at && ["available", "stale", "broader_region", "no_data"].includes(s.state) ? `updated ${since(s.updated_at)}` : null]
                .filter(Boolean)
                .join(", ")}
              {s.message ? <span className="block text-foreground/75">{s.message}</span> : null}
              {!dense && s.resolution ? <span className="block">Coverage: {s.resolution}</span> : null}
            </p>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

export function SourcesCard({ sources, title = "Data sources", description }: { sources: SourceStatus[]; title?: string; description?: string }) {
  const attributions = Array.from(new Set(sources.filter((s) => s.attribution && s.state !== "not_applicable").map((s) => s.attribution)));
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </CardHeader>
      <CardContent>
        <SourceList sources={sources} />
        {attributions.length ? (
          <p className="mt-3 border-t pt-3 text-xs text-muted-foreground">{attributions.join(". ")}.</p>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function Metric({ label, value, hint, className }: { label: string; value: ReactNode; hint?: ReactNode; className?: string }) {
  return (
    <div className={cn("min-w-0", className)}>
      <dt className="text-[13px] text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-lg font-semibold tabular">{value}</dd>
      {hint ? <dd className="text-xs text-muted-foreground">{hint}</dd> : null}
    </div>
  );
}

export function Updated({ at, prefix = "Updated" }: { at: string | null | undefined; prefix?: string }) {
  if (!at) return null;
  return (
    <time dateTime={at} title={date(at, { time: true })} className="text-xs text-muted-foreground">
      {prefix} {since(at)}
    </time>
  );
}
