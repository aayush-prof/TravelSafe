import Link from "next/link";
import { BellRing, CloudSun, FileText, Siren, Wind } from "lucide-react";

import { EventTimelineChart, ContributionChart } from "@/components/charts/charts";
import { ErrorState } from "@/components/common/actions";
import { EmptyState, LevelBadge, PageHeader, SampleNotice, SourceList } from "@/components/common/page";
import { EventList } from "@/components/events/EventItem";
import { FactorProfile } from "@/components/factors/FactorProfile";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getCities, getOverview } from "@/lib/api";
import { attempt } from "@/lib/attempt";
import { LEVEL_COLOR, date, levelVariant, num, placeLine, signed, since, withParams } from "@/lib/format";
import { resolveSelection, type SearchParams } from "@/lib/selection";
import type { Overview } from "@/lib/types";
import { cn } from "@/lib/utils";

export const metadata = { title: "Overview" };

function IndexScale({ index, level }: { index: number | null; level: Overview["general"]["level"] }) {
  if (index === null) return <div className="hatch mt-3 h-1.5 rounded-full" aria-hidden />;
  const pos = ((index + 10) / 20) * 100;
  return (
    <div className="relative mt-3 h-1.5 rounded-full bg-secondary" aria-hidden>
      <span className="absolute top-1/2 left-1/2 h-3 w-px -translate-y-1/2 bg-border" />
      <span
        className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-card"
        style={{ left: `${pos}%`, background: LEVEL_COLOR[levelVariant(level)] }}
      />
    </div>
  );
}

function SummaryCards({ ov, href }: { ov: Overview; href: (p: string) => string }) {
  const g = ov.general;
  const weatherAlerts = ov.sources.find((s) => s.key === "alerts");
  const answered = ov.sources.filter((s) => ["available", "stale", "broader_region", "no_data", "sample"].includes(s.state)).length;
  const used = ov.sources.filter((s) => s.state !== "not_applicable").length;
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Card className="gap-0">
        <CardHeader>
          <CardDescription>Overall assessment</CardDescription>
          <CardAction>
            <LevelBadge level={g.level} />
          </CardAction>
        </CardHeader>
        <CardContent className="mt-2">
          <p className="text-xl leading-tight font-semibold">{g.label}</p>
          <p className="mt-1 text-[13px] text-muted-foreground">
            {g.index === null ? "No index without enough evidence" : <>Index <span className="font-medium text-foreground tabular">{signed(g.index)}</span> on a −10 to +10 scale</>}
          </p>
          <IndexScale index={g.index} level={g.level} />
          <p className="mt-3 text-xs text-muted-foreground">
            For {ov.persona.name.toLowerCase()} travellers: <span className="font-medium text-foreground">{ov.personalized.label.toLowerCase()}</span>
          </p>
        </CardContent>
      </Card>

      <Card className="gap-0">
        <CardHeader>
          <CardDescription>Data coverage</CardDescription>
          <CardAction>
            <span className={cn("text-xs font-medium", ov.coverage.state === "good" ? "text-low" : ov.coverage.state === "limited" ? "text-guarded" : "text-unknown")}>
              {ov.coverage.label}
            </span>
          </CardAction>
        </CardHeader>
        <CardContent className="mt-2">
          <p className="text-xl font-semibold tabular">
            {ov.coverage.factors_assessed} of {ov.coverage.factors_total}
            <span className="ml-1.5 text-sm font-normal text-muted-foreground">factors assessed</span>
          </p>
          <ul className="mt-3 grid grid-cols-6 gap-1" aria-label="Factors">
            {ov.factors.map((f) => (
              <li key={f.key} title={`${f.label}: ${f.assessed ? "assessed" : "not assessed"}`}>
                <span className={cn("block h-6 rounded-[4px]", f.assessed ? "bg-brand/80" : "hatch")} />
                <span className="sr-only">{`${f.label}: ${f.assessed ? "assessed" : "not assessed"}`}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 line-clamp-2 text-xs text-muted-foreground">{ov.coverage.reasons.find((r, i) => i > 0 && !r.startsWith("Not assessed")) ?? ov.coverage.summary}</p>
        </CardContent>
      </Card>

      <Card className="gap-0">
        <CardHeader>
          <CardDescription>Active alerts</CardDescription>
          <CardAction>
            <BellRing aria-hidden className={cn("size-4", ov.critical_alerts.length ? "text-high" : "text-muted-foreground")} />
          </CardAction>
        </CardHeader>
        <CardContent className="mt-2">
          <p className="text-xl font-semibold tabular">{ov.critical_alerts.length}</p>
          <p className="mt-1 line-clamp-2 text-[13px] text-muted-foreground">
            {ov.critical_alerts[0]?.title ?? "No alerts from the sources that were checked."}
          </p>
          {weatherAlerts && weatherAlerts.state !== "available" ? (
            <p className="mt-2 text-xs text-muted-foreground">Official weather alerts weren&apos;t checked. <Link href={href("/weather")} className="text-accent-foreground hover:underline">Why</Link></p>
          ) : null}
        </CardContent>
      </Card>

      <Card className="gap-0">
        <CardHeader>
          <CardDescription>Last updated</CardDescription>
        </CardHeader>
        <CardContent className="mt-2">
          <p className="text-xl font-semibold">{ov.updated_at ? since(ov.updated_at) : "Not yet"}</p>
          <p className="mt-1 text-[13px] text-muted-foreground">
            {answered} of {used} data sources answered
          </p>
          <p className="mt-2 text-xs text-muted-foreground">
            {ov.latest_report_at ? `Newest news report ${date(ov.latest_report_at)}` : "No dated news reports"}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

export default async function OverviewPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const meta = await attempt(getCities);
  const { city, persona } = resolveSelection(sp, meta.ok ? meta.data : null);
  const res = await attempt(() => getOverview(city, persona));
  if (!res.ok) return <ErrorState title="Overview unavailable" message={res.message} city={city} />;
  const ov = res.data;
  const href = (p: string) => withParams(p, city, persona);
  const contributions = ov.factors
    .filter((f) => f.assessed && (f.contribution ?? 0) >= 0.005)
    .map((f) => ({ key: f.key, label: f.label, share: f.contribution ?? 0 }))
    .sort((a, b) => b.share - a.share);
  const anyConcern = ov.factors.some((f) => f.assessed && f.level !== "low");
  const w = ov.weather_now;
  const a = ov.air_now;

  return (
    <>
      <PageHeader
        title={ov.city.name}
        updatedAt={ov.updated_at}
        description={`${placeLine(ov.city.region, ov.city.area, ov.city.country)}. Travel conditions for ${ov.persona.name.toLowerCase()} travellers, from the last ${ov.period.days} days of reports and current feeds.`}
      >
        <Button asChild variant="outline" size="sm">
          <Link href={href("/reports")}>
            <FileText aria-hidden />
            Briefing
          </Link>
        </Button>
      </PageHeader>

      <SampleNotice mode={ov.data_mode} />

      {ov.critical_alerts.length ? (
        <div className="mb-4 space-y-2">
          {ov.critical_alerts.slice(0, 3).map((c, i) => (
            <Alert key={i} variant={c.level === "high" ? "destructive" : c.level === "elevated" ? "elevated" : "warning"}>
              <Siren aria-hidden />
              <AlertTitle>{c.title}</AlertTitle>
              <AlertDescription>
                <p>
                  {c.detail ? `${c.detail.replace(/\.$/, "")}. ` : ""}Source: {c.source}
                  {c.when ? `, ${since(c.when)}` : ""}. Alerts like this always raise the overall result.
                  {c.url ? (
                    <>
                      {" "}
                      <a href={c.url} target="_blank" rel="noopener noreferrer" className="font-medium underline">
                        Official details
                      </a>
                    </>
                  ) : null}
                </p>
              </AlertDescription>
            </Alert>
          ))}
        </div>
      ) : null}

      <SummaryCards ov={ov} href={href} />

      <div className="mt-4 grid gap-4 xl:grid-cols-12">
        <div className="space-y-4 xl:col-span-8">
          <Card>
            <CardHeader>
              <CardTitle>Factor risk profile</CardTitle>
              <CardDescription>{ov.general.summary}</CardDescription>
            </CardHeader>
            <CardContent>
              <FactorProfile factors={ov.factors} personaName={ov.persona.name} />
              <p className="mt-3 text-xs text-muted-foreground">{ov.persona_explanation}</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Reported incidents over time</CardTitle>
              <CardDescription>Last 14 days. Repeated coverage of one incident is counted once.</CardDescription>
            </CardHeader>
            <CardContent>
              {ov.timeline.available ? (
                <>
                  <EventTimelineChart days={ov.timeline.days} />
                  <p className="mt-2 text-xs text-muted-foreground">{ov.timeline.reason}</p>
                </>
              ) : (
                <EmptyState title="No timeline yet">{ov.timeline.reason}</EmptyState>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Most relevant recent events</CardTitle>
              <CardDescription>Ranked by how much they affect the assessment.</CardDescription>
              <CardAction>
                <Button asChild variant="ghost" size="sm">
                  <Link href={href("/events")}>All events ({ov.total_reports})</Link>
                </Button>
              </CardAction>
            </CardHeader>
            <CardContent>
              {ov.recent_events.length ? (
                <EventList events={ov.recent_events} showSummary={false} />
              ) : (
                <EmptyState title="No counted incidents">
                  {ov.sources.find((s) => s.key === "news")?.message || "No recent reports name this city with an adverse event."}
                </EmptyState>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4 xl:col-span-4">
          <Card>
            <CardHeader>
              <CardTitle>What drives the result</CardTitle>
              <CardDescription>Share of the overall signal from each assessed factor.</CardDescription>
            </CardHeader>
            <CardContent>
              {anyConcern && contributions.length ? (
                <ContributionChart items={contributions} />
              ) : (
                <EmptyState title={ov.coverage.state === "insufficient" ? "Nothing to break down" : "No factor stands out"}>
                  {ov.coverage.state === "insufficient"
                    ? "There isn't enough evidence for an assessment."
                    : "Every assessed factor is low, so no breakdown is shown."}
                </EmptyState>
              )}
              {ov.key_factors.length ? (
                <ul className="mt-4 space-y-2 border-t pt-4">
                  {ov.key_factors.map((k) => (
                    <li key={k.category} className="flex items-start gap-2 text-[13px]">
                      <LevelBadge level={k.level} className="mt-px" />
                      <span className="text-secondary-foreground">{k.text}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Conditions now</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <Link href={href("/weather")} className="flex items-start gap-3 rounded-lg p-1 hover:bg-secondary">
                <CloudSun aria-hidden className="mt-0.5 size-5 text-brand" />
                <span className="min-w-0">
                  <span className="block text-sm font-medium">
                    {w.available ? `${num(w.temperature_c, " °C") ?? "n/a"}, ${w.condition?.toLowerCase() ?? ""}` : "Weather unavailable"}
                  </span>
                  <span className="block text-xs text-muted-foreground">
                    {w.available ? `${w.provider}${w.message ? `. ${w.message}` : ""}` : w.message}
                  </span>
                </span>
              </Link>
              <Link href={href("/environment")} className="flex items-start gap-3 rounded-lg p-1 hover:bg-secondary">
                <Wind aria-hidden className="mt-0.5 size-5 text-teal" />
                <span className="min-w-0">
                  <span className="block text-sm font-medium">
                    {a.measured ? `Air: ${a.category?.toLowerCase() ?? "uncategorised"}` : "Air quality not measured"}
                  </span>
                  <span className="block text-xs text-muted-foreground">
                    {a.measured
                      ? `${a.station}, ${num(a.distance_km, " km")} away${a.pm25 !== null ? `. PM2.5 ${a.pm25} µg/m³` : ""}`
                      : a.message}
                    {a.modelled_category ? ` Model estimate for the wider area: ${a.modelled_category.toLowerCase()}.` : ""}
                  </span>
                </span>
              </Link>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Sources</CardTitle>
              <CardDescription>{ov.coverage.reasons[0]}</CardDescription>
            </CardHeader>
            <CardContent>
              <SourceList sources={ov.sources} dense />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Precautions</CardTitle>
              <CardDescription>{ov.precautions.basis}</CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="list-disc space-y-1.5 pl-4 text-[13px] text-secondary-foreground marker:text-muted-foreground">
                {ov.precautions.dos.slice(0, 5).map((d) => (
                  <li key={d}>{d}</li>
                ))}
                {ov.precautions.donts.slice(0, 3).map((d) => (
                  <li key={d}>{d}</li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </div>
      </div>

      <p className="mt-6 text-xs text-muted-foreground">{ov.disclaimer}</p>
    </>
  );
}
