import type { Metadata } from "next";
import Image from "next/image";
import { Bus, CloudSun, ExternalLink, Info, Phone, UserRound } from "lucide-react";

import { ErrorState, RetryButton } from "@/components/common/actions";
import { PageHeader, SourceList } from "@/components/common/page";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { getCities, getInsights } from "@/lib/api";
import { attempt } from "@/lib/attempt";
import { placeLine } from "@/lib/format";
import { resolveSelection, type SearchParams } from "@/lib/selection";

export const metadata: Metadata = { title: "City insights" };

function Essential({ icon: Icon, title, children }: { icon: typeof Bus; title: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Icon aria-hidden className="size-[18px] text-brand" strokeWidth={1.9} />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="text-[14px] leading-relaxed text-secondary-foreground">{children}</CardContent>
    </Card>
  );
}

function BulletList({ items }: { items: string[] }) {
  return (
    <ul className="list-disc space-y-1 pl-4 marker:text-muted-foreground">
      {items.map((i) => (
        <li key={i}>{i}</li>
      ))}
    </ul>
  );
}

export default async function InsightsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const meta = await attempt(getCities);
  const { city, persona } = resolveSelection(sp, meta.ok ? meta.data : null);
  const res = await attempt(() => getInsights(city, persona));
  if (!res.ok) return <ErrorState title="City Insights unavailable" message={res.message} city={city} />;
  const d = res.data;
  const available = d.status === "available";
  const place = placeLine(d.city.region, d.city.area, d.city.country);

  return (
    <>
      <PageHeader
        title={d.city.name}
        updatedAt={d.source.updated_at}
        description={d.description ? `${d.description[0]?.toUpperCase()}${d.description.slice(1)}.` : `${place}.`}
      />
      <div className="space-y-6">
        <p className="text-sm text-muted-foreground">
          Background for planning your trip. For current conditions and concerns, see the Overview.
        </p>

        {!available || d.source.state === "stale" ? (
          <Alert variant={available ? "info" : "warning"}>
            <Info aria-hidden />
            <AlertTitle>{available ? "Showing the last saved city information" : "City information is unavailable"}</AlertTitle>
            <AlertDescription>
              <p>{d.message}</p>
              <RetryButton city={city} />
            </AlertDescription>
          </Alert>
        ) : null}

        <div className="grid items-start gap-6 lg:grid-cols-12">
          <div className="lg:col-span-8 lg:row-start-1">
            {/* A + D: introduction and about */}
            <Card className="py-0">
              <div className="flex flex-col gap-5 p-5 sm:flex-row sm:p-6">
                {d.image_url ? (
                  <div className="relative aspect-[4/3] w-full shrink-0 overflow-hidden rounded-md bg-border sm:w-44">
                    <Image
                      src={d.image_url}
                      alt={`${d.city.name}, from the Wikipedia article`}
                      fill
                      unoptimized
                      sizes="(min-width: 640px) 176px, 100vw"
                      className="object-cover"
                    />
                  </div>
                ) : null}
                <div className="min-w-0">
                  <h2 className="text-base font-semibold text-foreground">About {d.city.name}</h2>
                  {d.summary ? (
                    <p className="mt-2 max-w-prose text-[15px] leading-relaxed text-secondary-foreground">{d.summary}</p>
                  ) : (
                    <p className="mt-2 text-[15px] text-muted-foreground">
                      A description isn&apos;t available right now. TravelSafe doesn&apos;t fill gaps with its own text.
                    </p>
                  )}
                  <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2">
                    {d.about.length > 1 ? (
                      <Collapsible className="w-full">
                        <CollapsibleTrigger className="text-sm font-medium text-accent-foreground hover:underline">Read more</CollapsibleTrigger>
                        <CollapsibleContent className="mt-3 max-w-prose space-y-3 text-[15px] leading-relaxed text-secondary-foreground">
                          {d.about.slice(1).map((p) => (
                            <p key={p.slice(0, 40)}>{p}</p>
                          ))}
                        </CollapsibleContent>
                      </Collapsible>
                    ) : null}
                    {d.article_url ? (
                      <a
                        href={d.article_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 self-start text-sm font-medium text-accent-foreground hover:underline"
                      >
                        Full article on Wikipedia
                        <ExternalLink aria-hidden className="size-3.5" />
                        <span className="sr-only">(opens in a new tab)</span>
                      </a>
                    ) : null}
                  </div>
                </div>
              </div>
            </Card>

          </div>

          <div className="space-y-6 lg:col-span-4 lg:col-start-9 lg:row-span-2 lg:row-start-1">
            {/* B: at a glance */}
            <Card>
              <CardHeader>
                <CardTitle>At a glance</CardTitle>
              </CardHeader>
              <CardContent>
                <dl className="divide-y">
                  {d.facts.map((f) => (
                    <div key={f.label} className="flex justify-between gap-4 py-2 text-sm">
                      <dt className="text-muted-foreground">{f.label}</dt>
                      <dd className="min-w-0 text-right font-medium">
                        {f.label === "Official website" ? (
                          <a href={f.value} target="_blank" rel="noopener noreferrer" className="break-all text-accent-foreground hover:underline">
                            {f.value.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "")}
                          </a>
                        ) : (
                          f.value
                        )}
                        {f.note ? <span className="block text-xs font-normal text-muted-foreground">{f.note}</span> : null}
                      </dd>
                    </div>
                  ))}
                </dl>
                <p className="mt-3 text-[13px] text-muted-foreground">Source: {d.facts_source}.</p>
              </CardContent>
            </Card>
            <Essential icon={Phone} title="Emergency numbers">
              {d.emergency.length ? (
                <dl className="space-y-1.5">
                  {d.emergency.map((e) => (
                    <div key={e.service} className="flex justify-between gap-3">
                      <dt>{e.service}</dt>
                      <dd className="font-semibold text-foreground tabular">{e.number}</dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p>Not available for this country.</p>
              )}
              <p className="mt-2 text-[13px] text-muted-foreground">{d.emergency_note}</p>
            </Essential>
          </div>
          <div className="lg:col-span-8 lg:row-start-2">
            {/* C: travel essentials */}
            <section aria-labelledby="essentials">
              <h2 id="essentials" className="mb-3 text-lg font-semibold text-foreground">
                Travel essentials
              </h2>
              <div className="grid gap-6 md:grid-cols-2">
                {d.climate ? (
                  <Essential icon={CloudSun} title="Climate">
                    <p>{d.climate}</p>
                    <p className="mt-2 text-[13px] text-muted-foreground">From Wikipedia. Long-term averages for planning, not current weather.</p>
                  </Essential>
                ) : null}
                {d.transport ? (
                  <Essential icon={Bus} title="Getting around">
                    <p>{d.transport}</p>
                    <p className="mt-2 text-[13px] text-muted-foreground">From Wikipedia.</p>
                  </Essential>
                ) : null}
                <div className={d.climate && d.transport ? "md:col-span-2" : ""}>
                  <Essential icon={UserRound} title={`Tips for ${d.persona.name.toLowerCase()} travellers`}>
                    <BulletList items={d.persona_tips.slice(0, 4)} />
                    <p className="mt-2 text-[13px] text-muted-foreground">General guidance, not specific to this city.</p>
                  </Essential>
                </div>
              </div>
              {available && !d.climate && !d.transport ? (
                <p className="mt-3 text-sm text-muted-foreground">Climate and transport summaries aren&apos;t available for this city.</p>
              ) : null}
            </section>
          </div>
        </div>

        {/* E: source and freshness */}
        <Card className="py-3">
          <CardContent className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-64 flex-1">
              <SourceList sources={[{ ...d.source, message: "" }]} dense />
            </div>
            {available ? <RetryButton city={city} label="Refresh city information" /> : null}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
