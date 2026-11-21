import type { Metadata } from "next";
import { Info } from "lucide-react";

import { CountBarChart } from "@/components/charts/charts";
import { ErrorState } from "@/components/common/actions";
import { EmptyState, LevelBadge, Metric, PageHeader, SampleNotice, SourceList } from "@/components/common/page";
import { EventList } from "@/components/events/EventItem";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { getCities, getCrime } from "@/lib/api";
import { attempt } from "@/lib/attempt";
import { date, plural } from "@/lib/format";
import { resolveSelection, type SearchParams } from "@/lib/selection";

export const metadata: Metadata = { title: "Crime watch" };

function More({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Collapsible className="border-t pt-3 first:border-t-0 first:pt-0">
      <CollapsibleTrigger className="text-sm font-medium text-accent-foreground hover:underline">{title}</CollapsibleTrigger>
      <CollapsibleContent className="mt-3">{children}</CollapsibleContent>
    </Collapsible>
  );
}

export default async function CrimePage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const meta = await attempt(getCities);
  const { city, persona } = resolveSelection(sp, meta.ok ? meta.data : null);
  const res = await attempt(() => getCrime(city, persona));
  if (!res.ok) return <ErrorState title="Crime watch unavailable" message={res.message} city={city} />;
  const cr = res.data;
  const f = cr.factor;
  const news = cr.sources.find((s) => s.key === "news");

  return (
    <>
      <PageHeader title="Crime watch" updatedAt={news?.updated_at ?? null} description={`Crime and security reports about ${cr.city} from the last 30 days.`} />
      <SampleNotice mode={cr.data_mode} />
      <Alert variant="info" className="mb-4">
        <Info aria-hidden />
        <AlertTitle>News coverage, not crime statistics</AlertTitle>
        <AlertDescription>{cr.explanation}</AlertDescription>
      </Alert>

      <div className="grid gap-4 xl:grid-cols-12">
        <div className="space-y-4 xl:col-span-4">
          <Card>
            <CardHeader>
              <CardTitle>Crime and security</CardTitle>
              <CardAction>
                <LevelBadge level={f.level} />
              </CardAction>
            </CardHeader>
            <CardContent>
              <p className="text-[13px] text-secondary-foreground">{f.summary}</p>
              {f.assessed && f.persona_level !== f.level ? (
                <p className="mt-2 flex items-center gap-2 text-[13px]">
                  <LevelBadge level={f.persona_level} />
                  <span className="text-muted-foreground">{f.persona_note}</span>
                </p>
              ) : null}
              <dl className="mt-4 grid grid-cols-2 gap-4 border-t pt-4">
                <Metric label="Incidents counted" value={cr.incidents_counted} />
                <Metric label="News reports" value={cr.articles_counted} hint={cr.articles_counted > cr.incidents_counted ? "repeated coverage merged" : undefined} />
              </dl>
            </CardContent>
          </Card>
          {cr.breakdown.available ? (
            <Card>
              <CardHeader>
                <CardTitle>Types of incident</CardTitle>
                <CardDescription>Counted incidents, repeated coverage merged.</CardDescription>
              </CardHeader>
              <CardContent>
                <CountBarChart items={cr.breakdown.items} label="Type" valueLabel="Incidents" />
              </CardContent>
            </Card>
          ) : null}
          {cr.trend.available ? (
            <Card>
              <CardHeader>
                <CardTitle>Reports per week</CardTitle>
                <CardDescription>{cr.trend.reason}</CardDescription>
              </CardHeader>
              <CardContent>
                <CountBarChart
                  items={cr.trend.weeks.map((w) => ({ label: date(w.week_start, { year: false }), count: w.count }))}
                  label="Week starting"
                  valueLabel="Reports"
                />
              </CardContent>
            </Card>
          ) : null}
          {news ? (
            <Card className="py-3">
              <CardContent>
                <SourceList sources={[news]} dense />
              </CardContent>
            </Card>
          ) : null}
        </div>

        <div className="space-y-4 xl:col-span-8">
          <Card>
            <CardHeader>
              <CardTitle>Recent incidents</CardTitle>
              <CardDescription>Ordered by how much they affect the assessment.</CardDescription>
            </CardHeader>
            <CardContent>
              {cr.events.length ? (
                <EventList events={cr.events} showCategory={false} />
              ) : (
                <EmptyState title={f.assessed ? "No crime incidents counted" : "Not assessed"}>
                  {f.assessed
                    ? "None of the reports analysed describe a crime in this city. That isn't proof that none occurred."
                    : f.summary}
                </EmptyState>
              )}
            </CardContent>
          </Card>

          {!cr.breakdown.available || !cr.trend.available || cr.not_counted.length || cr.supplementary.length ? (
            <Card>
              <CardHeader>
                <CardTitle>More detail</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {!cr.breakdown.available || !cr.trend.available ? (
                  <More title="Why some charts aren't shown">
                    <p className="text-[13px] text-secondary-foreground">
                      {!cr.breakdown.available ? `${cr.breakdown.reason} ` : ""}
                      {!cr.trend.available ? cr.trend.reason : ""} Charts built from very few reports would suggest patterns that aren&apos;t there.
                    </p>
                  </More>
                ) : null}
                {cr.not_counted.length ? (
                  <More title={`Reports not counted (${cr.not_counted.length})`}>
                    <EventList events={cr.not_counted} showCategory={false} />
                  </More>
                ) : null}
                {cr.supplementary.length ? (
                  <More title={`Additional crime coverage (${plural(cr.supplementary.length, "report")})`}>
                    <p className="mb-3 text-[13px] text-muted-foreground">{cr.supplementary_note}</p>
                    <EventList events={cr.supplementary} showCategory={false} />
                  </More>
                ) : null}
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
    </>
  );
}
