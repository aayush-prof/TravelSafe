import { Activity, ExternalLink, Mountain } from "lucide-react";

import { AirTrendChart } from "@/components/charts/charts";
import { ErrorState } from "@/components/common/actions";
import { EmptyState, LevelBadge, PageHeader, SampleNotice, SourcesCard } from "@/components/common/page";
import { EventList } from "@/components/events/EventItem";
import { Badge } from "@/components/ui/badge";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getAirQuality, getCities, getDisasters } from "@/lib/api";
import { attempt } from "@/lib/attempt";
import { date, since } from "@/lib/format";
import { resolveSelection, type SearchParams } from "@/lib/selection";
import type { Hazard } from "@/lib/types";

export const metadata = { title: "Air & hazards" };

const AQ_VARIANT: Record<string, "low" | "guarded" | "elevated" | "high"> = {
  Good: "low",
  Moderate: "low",
  "Unhealthy for sensitive groups": "guarded",
  Unhealthy: "elevated",
  "Very unhealthy": "high",
  Hazardous: "high",
};

function HazardRow({ h }: { h: Hazard }) {
  const sev = h.severity === "none" ? null : h.severity;
  return (
    <li className="flex items-start justify-between gap-4 py-3">
      <div className="min-w-0">
        <p className="text-sm font-medium">
          {h.url ? (
            <a href={h.url} target="_blank" rel="noopener noreferrer" className="hover:underline">
              {h.title}
              <ExternalLink aria-hidden className="ml-1 inline size-3" />
              <span className="sr-only">(opens in a new tab)</span>
            </a>
          ) : (
            h.title
          )}
        </p>
        <p className="mt-0.5 text-[13px] text-muted-foreground">
          {h.hazard}, {h.source}, {since(h.when)}. {h.relevance}.
        </p>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1">
        {h.alert_level ? (
          <Badge variant={/red/i.test(h.alert_level) ? "high" : /orange/i.test(h.alert_level) ? "elevated" : "secondary"}>
            {h.alert_level} alert
          </Badge>
        ) : null}
        {sev ? <span className="text-xs text-muted-foreground capitalize">{sev}</span> : null}
      </div>
    </li>
  );
}

export default async function EnvironmentPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const meta = await attempt(getCities);
  const { city, persona } = resolveSelection(sp, meta.ok ? meta.data : null);
  const [air, hz] = await Promise.all([attempt(() => getAirQuality(city, persona)), attempt(() => getDisasters(city, persona))]);
  if (!air.ok && !hz.ok) return <ErrorState title="Air quality and hazards unavailable" message={air.message} city={city} />;
  const mode = air.ok ? air.data.data_mode : hz.ok ? hz.data.data_mode : "none";
  const updated = air.ok ? (air.data.measured?.observed_at ?? air.data.sources[0]?.updated_at ?? null) : null;

  return (
    <>
      <PageHeader title={`Air quality and natural hazards in ${city}`} updatedAt={updated} description="Measured air pollution near the city, and earthquakes or disaster alerts close enough to matter." />
      <SampleNotice mode={mode} />

      <div className="grid gap-4 xl:grid-cols-12">
        <div className="space-y-4 xl:col-span-8">
          {air.ok ? (
            <Card>
              <CardHeader>
                <CardTitle>Measured air quality</CardTitle>
                <CardDescription>Nearest monitoring station with a reading in the last 48 hours.</CardDescription>
                <CardAction>
                  <LevelBadge level={air.data.factor.level} />
                </CardAction>
              </CardHeader>
              <CardContent>
                {air.data.measured ? (
                  <>
                    <div className="flex flex-wrap items-end gap-x-8 gap-y-3">
                      <div>
                        <p className="text-xs text-muted-foreground">Indicative category</p>
                        <p className="mt-0.5 flex items-center gap-2 text-xl font-semibold">
                          {air.data.measured.category ?? "Not categorised"}
                          {air.data.measured.category ? <Badge variant={AQ_VARIANT[air.data.measured.category] ?? "secondary"}>US EPA scale</Badge> : null}
                        </p>
                      </div>
                      <dl className="flex flex-wrap gap-x-6 gap-y-2">
                        {air.data.measured.readings.map((r) => (
                          <div key={r.parameter}>
                            <dt className="text-xs text-muted-foreground">{r.label}</dt>
                            <dd className="text-base font-semibold tabular">
                              {r.value} <span className="text-xs font-normal text-muted-foreground">{r.unit}</span>
                            </dd>
                          </div>
                        ))}
                      </dl>
                    </div>
                    <p className="mt-2 text-[13px] text-muted-foreground">
                      {air.data.measured.station}, {air.data.measured.distance_km} km from the city centre.
                      {air.data.measured.observed_at ? ` Reading from ${date(air.data.measured.observed_at, { time: true })}.` : ""}
                    </p>
                    <div className="mt-4">
                      <p className="mb-1 text-sm font-medium">PM2.5 over the last 72 hours</p>
                      {air.data.measured.trend.length >= 6 ? (
                        <AirTrendChart points={air.data.measured.trend} />
                      ) : (
                        <EmptyState title="No trend available">The station didn&apos;t return enough hourly values for a trend.</EmptyState>
                      )}
                    </div>
                  </>
                ) : (
                  <EmptyState icon={<Activity className="size-6" />} title="Not assessed">
                    {air.data.sources.find((s) => s.key === "air")?.message} A missing measurement is not treated as clean air.
                  </EmptyState>
                )}
              </CardContent>
            </Card>
          ) : (
            <ErrorState title="Air quality unavailable" message={air.message} city={city} />
          )}

          {air.ok && air.data.modelled ? (
            <Card>
              <CardHeader>
                <CardTitle>Modelled estimate for the wider area</CardTitle>
                <CardDescription>Context only. A ~45 km model grid can&apos;t show local hot spots, so it never changes the assessment.</CardDescription>
              </CardHeader>
              <CardContent>
                <dl className="mb-3 flex flex-wrap gap-x-8 gap-y-2">
                  <div>
                    <dt className="text-xs text-muted-foreground">Category</dt>
                    <dd className="font-semibold">{air.data.modelled.category ?? "n/a"}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-foreground">PM2.5</dt>
                    <dd className="font-semibold tabular">{air.data.modelled.pm25 ?? "n/a"} µg/m³</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-foreground">PM10</dt>
                    <dd className="font-semibold tabular">{air.data.modelled.pm10 ?? "n/a"} µg/m³</dd>
                  </div>
                </dl>
                {air.data.modelled.trend.length >= 6 ? <AirTrendChart points={air.data.modelled.trend} modelled /> : null}
                <p className="mt-2 text-xs text-muted-foreground">{air.data.modelled.attribution}.</p>
              </CardContent>
            </Card>
          ) : null}

          {hz.ok ? (
            <Card>
              <CardHeader>
                <CardTitle>Natural hazards near the city</CardTitle>
                <CardDescription>{hz.data.note}</CardDescription>
                <CardAction>
                  <LevelBadge level={hz.data.factor.level} />
                </CardAction>
              </CardHeader>
              <CardContent>
                <p className="mb-2 text-[13px] text-secondary-foreground">{hz.data.factor.summary}</p>
                {hz.data.events.length ? (
                  <ul className="divide-y">
                    {hz.data.events.map((h, i) => (
                      <HazardRow key={i} h={h} />
                    ))}
                  </ul>
                ) : (
                  <EmptyState icon={<Mountain className="size-6" />} title="No hazard events near the city">
                    {hz.data.sources.some((s) => s.state === "available")
                      ? "Nothing in the earthquake or disaster-alert feeds is close enough to affect the city."
                      : "The hazard feeds couldn't be checked, so this isn't confirmation that there are none."}
                  </EmptyState>
                )}
                {hz.data.context.length ? (
                  <div className="mt-4 border-t pt-3">
                    <p className="text-sm font-medium">Elsewhere in the region</p>
                    <p className="text-xs text-muted-foreground">Listed for context; not attributed to the city.</p>
                    <ul className="divide-y">
                      {hz.data.context.map((h, i) => (
                        <HazardRow key={i} h={h} />
                      ))}
                    </ul>
                  </div>
                ) : null}
              </CardContent>
            </Card>
          ) : (
            <ErrorState title="Hazard data unavailable" message={hz.message} city={city} />
          )}

          {hz.ok && hz.data.news_events.length ? (
            <Card>
              <CardHeader>
                <CardTitle>Disasters in the news</CardTitle>
                <CardDescription>Reports already covered by the feeds above are not counted twice.</CardDescription>
              </CardHeader>
              <CardContent>
                <EventList events={hz.data.news_events} showCategory={false} />
              </CardContent>
            </Card>
          ) : null}
        </div>

        <div className="space-y-4 xl:col-span-4">
          {air.ok ? <SourcesCard title="Air-quality sources" sources={air.data.sources} description={air.data.note} /> : null}
          {hz.ok ? <SourcesCard title="Hazard sources" sources={hz.data.sources} /> : null}
        </div>
      </div>
    </>
  );
}
