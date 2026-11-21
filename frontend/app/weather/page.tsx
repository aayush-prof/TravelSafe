import { CloudOff, Droplets, Eye, Gauge, Sunrise, Sunset, Thermometer, TriangleAlert, Wind } from "lucide-react";

import { WeatherForecastChart } from "@/components/charts/charts";
import { ErrorState, RetryButton } from "@/components/common/actions";
import { EmptyState, LevelBadge, PageHeader, SampleNotice, SourceState, Updated } from "@/components/common/page";
import { EventList } from "@/components/events/EventItem";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { getCities, getWeather } from "@/lib/api";
import { attempt } from "@/lib/attempt";
import { date, num, weekday } from "@/lib/format";
import { resolveSelection, type SearchParams } from "@/lib/selection";
import type { WeatherResponse } from "@/lib/types";

export const metadata = { title: "Weather" };

function compass(deg: number | null): string {
  if (deg === null) return "";
  return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][Math.round(deg / 45) % 8] ?? "";
}

function MetricTile({ icon: Icon, label, value, hint }: { icon: typeof Wind; label: string; value: string | null; hint?: string }) {
  return (
    <div className="rounded-lg border bg-card p-3">
      <dt className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Icon aria-hidden className="size-3.5" />
        {label}
      </dt>
      <dd className="mt-1 text-base font-semibold tabular">{value ?? <span className="font-normal text-muted-foreground">Not reported</span>}</dd>
      {hint ? <dd className="text-xs text-muted-foreground">{hint}</dd> : null}
    </div>
  );
}

function Unavailable({ w, city }: { w: WeatherResponse; city: string }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-start gap-3 py-2 sm:flex-row sm:items-center">
        <CloudOff aria-hidden className="size-8 shrink-0 text-unknown" />
        <div className="min-w-0 flex-1">
          <p className="font-semibold">Live weather is unavailable</p>
          <p className="mt-0.5 text-[15px] text-secondary-foreground">{w.reason}</p>
          <p className="mt-1 text-[13px] text-muted-foreground">
            Without live data the weather factor is marked &ldquo;not assessed&rdquo;, never &ldquo;low&rdquo;. Official alerts can&apos;t be checked either.
          </p>
        </div>
        <RetryButton city={city} />
      </CardContent>
    </Card>
  );
}

export default async function WeatherPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const meta = await attempt(getCities);
  const { city, persona } = resolveSelection(sp, meta.ok ? meta.data : null);
  const res = await attempt(() => getWeather(city, persona));
  if (!res.ok) return <ErrorState title="Weather unavailable" message={res.message} city={city} />;
  const w = res.data;
  const c = w.current;

  return (
    <>
      <PageHeader title={`Weather in ${w.city}`} updatedAt={w.updated_at} description="Current conditions, the next 48 hours and official alerts, with hazards that matter for travel." />
      <SampleNotice mode={w.data_mode} />

      {w.status === "unavailable" || !c ? (
        <Unavailable w={w} city={city} />
      ) : (
        <>
          {w.status === "stale" ? (
            <Alert variant="warning" className="mb-4">
              <TriangleAlert aria-hidden />
              <AlertTitle>Showing the last available update</AlertTitle>
              <AlertDescription>The latest refresh failed. These conditions were retrieved {date(w.updated_at, { time: true })}.</AlertDescription>
            </Alert>
          ) : null}
          <div className="grid gap-4 xl:grid-cols-12">
            <Card className="xl:col-span-4">
              <CardHeader>
                <CardDescription>Now</CardDescription>
                <CardAction>
                  <LevelBadge level={w.conditions.level} />
                </CardAction>
              </CardHeader>
              <CardContent>
                <p className="text-5xl font-semibold tracking-tight tabular">{num(c.temperature_c, "°") ?? "n/a"}</p>
                <p className="mt-1 text-lg">{c.condition}</p>
                <p className="text-sm text-muted-foreground">Feels like {num(c.feels_like_c, " °C") ?? "n/a"}</p>
                {w.conditions.factors.length ? (
                  <ul className="mt-4 flex flex-wrap gap-1.5">
                    {w.conditions.factors.map((f) => (
                      <li key={f} className="rounded-md bg-elevated-soft px-2 py-0.5 text-xs font-medium text-elevated">{f}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-4 text-[13px] text-muted-foreground">Nothing in the current conditions affects travel.</p>
                )}
                <p className="mt-4 border-t pt-3 text-xs text-muted-foreground">
                  {w.attribution}. {c.observed_at ? `Observed ${date(c.observed_at, { time: true })}.` : ""}
                  {w.fallback_used ? " The primary provider failed, so this fallback source is used." : ""}
                </p>
              </CardContent>
            </Card>

            <div className="xl:col-span-8">
              <dl className="grid grid-cols-2 gap-3 md:grid-cols-3">
                <MetricTile icon={Droplets} label="Humidity" value={num(c.humidity_pct, "%")} />
                <MetricTile icon={Wind} label="Wind" value={num(c.wind_kmh, " km/h")} hint={[compass(c.wind_dir_deg), c.wind_gust_kmh !== null ? `gusts ${num(c.wind_gust_kmh, " km/h")}` : ""].filter(Boolean).join(", ")} />
                <MetricTile icon={Eye} label="Visibility" value={num(c.visibility_km, " km", c.visibility_km !== null && c.visibility_km < 10 ? 1 : 0)} />
                <MetricTile icon={Gauge} label="Pressure" value={num(c.pressure_hpa, " hPa")} />
                <MetricTile icon={Sunrise} label="Sunrise" value={c.sunrise_local} hint="Local time" />
                <MetricTile icon={Sunset} label="Sunset" value={c.sunset_local} hint="Local time" />
              </dl>

              <Card className="mt-4">
                <CardHeader>
                  <CardTitle>Official weather alerts</CardTitle>
                  <CardAction>
                    <SourceState state={w.alerts_source.state} />
                  </CardAction>
                </CardHeader>
                <CardContent>
                  {w.alerts && w.alerts.length ? (
                    <ul className="space-y-3">
                      {w.alerts.map((a, i) => (
                        <li key={i}>
                          <Alert variant="destructive">
                            <TriangleAlert aria-hidden />
                            <AlertTitle>{a.event}</AlertTitle>
                            <AlertDescription>
                              <p>{a.description}</p>
                              <p className="text-xs">
                                {a.issued_by ? `${a.issued_by}. ` : ""}
                                {a.start ? `From ${date(a.start, { time: true })}` : ""}
                                {a.end ? ` until ${date(a.end, { time: true })}` : ""}
                              </p>
                            </AlertDescription>
                          </Alert>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-secondary-foreground">{w.alerts_message}</p>
                  )}
                </CardContent>
              </Card>
            </div>
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-12">
            <Card className="xl:col-span-8">
              <CardHeader>
                <CardTitle>Next 48 hours</CardTitle>
                <CardDescription>
                  {w.provider} forecast in {w.hourly_step_hours === 1 ? "hourly" : `${w.hourly_step_hours}-hour`} steps, local time.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {w.hourly.length ? <WeatherForecastChart hours={w.hourly} stepHours={w.hourly_step_hours} timeZone={w.timezone} /> : <EmptyState title="No hourly forecast">The provider returned current conditions only.</EmptyState>}
                {w.conditions.forecast_hazards.length ? (
                  <ul className="mt-4 space-y-1 border-t pt-3 text-[13px]">
                    {w.conditions.forecast_hazards.map((h) => (
                      <li key={h} className="flex items-center gap-2">
                        <TriangleAlert aria-hidden className="size-3.5 text-elevated" />
                        {h}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </CardContent>
            </Card>

            <Card className="xl:col-span-4">
              <CardHeader>
                <CardTitle>Daily outlook</CardTitle>
              </CardHeader>
              <CardContent>
                {w.daily.length ? (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Day</TableHead>
                        <TableHead className="text-right">Low / high</TableHead>
                        <TableHead className="text-right">Rain</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {w.daily.map((d) => (
                        <TableRow key={d.date}>
                          <TableCell>
                            <span className="block font-medium">{weekday(d.date)}</span>
                            <span className="text-xs text-muted-foreground">{d.condition}</span>
                          </TableCell>
                          <TableCell className="text-right tabular">
                            {num(d.temp_min_c, "°") ?? "n/a"} / {num(d.temp_max_c, "°") ?? "n/a"}
                          </TableCell>
                          <TableCell className="text-right tabular">
                            {num(d.precip_mm, " mm", 1) ?? "n/a"}
                            {d.precip_prob !== null ? <span className="block text-xs text-muted-foreground">{Math.round(d.precip_prob * 100)}%</span> : null}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : (
                  <EmptyState title="No daily forecast" />
                )}
              </CardContent>
            </Card>
          </div>
        </>
      )}

      <div className="mt-4 grid gap-4 xl:grid-cols-12">
        <Card className="xl:col-span-8">
          <CardHeader>
            <CardTitle>Weather in the news</CardTitle>
            <CardDescription>{w.note || "Recent reports that name the city. They corroborate live data at half weight."}</CardDescription>
          </CardHeader>
          <CardContent>
            {w.news_events.length ? <EventList events={w.news_events} showCategory={false} /> : <EmptyState title="No weather reports">No recent news reports about weather in this city.</EmptyState>}
          </CardContent>
        </Card>
        <div className="space-y-4 xl:col-span-4">
          <Card>
            <CardHeader>
              <CardTitle>Weather factor</CardTitle>
              <CardAction>
                <LevelBadge level={w.factor.level} />
              </CardAction>
            </CardHeader>
            <CardContent>
              <p className="text-[13px] text-secondary-foreground">{w.factor.summary}</p>
              {w.advice.length ? (
                <ul className="mt-3 list-disc space-y-1 pl-4 text-[13px] marker:text-muted-foreground">
                  {w.advice.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
              ) : null}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Source</CardTitle>
              <CardAction>
                <SourceState state={w.source.state} />
              </CardAction>
            </CardHeader>
            <CardContent className="space-y-1 text-[13px]">
              <p>{w.source.provider ?? "No provider answered"}</p>
              {w.source.message ? <p className="text-muted-foreground">{w.source.message}</p> : null}
              <Updated at={w.updated_at} />
              <p className="flex items-center gap-1.5 pt-2 text-xs text-muted-foreground">
                <Thermometer aria-hidden className="size-3.5" />
                Climate averages appear on City insights; they are never used as current weather.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
