import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { EventList } from "@/components/events/EventItem";
import { FilterToolbar, SortSelect } from "@/components/events/FilterToolbar";
import { ErrorState } from "@/components/common/actions";
import { EmptyState, PageHeader, SampleNotice, SourceList } from "@/components/common/page";
import { Card, CardContent } from "@/components/ui/card";
import { getCities, getEvents } from "@/lib/api";
import { attempt } from "@/lib/attempt";
import { plural } from "@/lib/format";
import { first, list, resolveSelection, type SearchParams } from "@/lib/selection";

export const metadata: Metadata = { title: "Events" };

export default async function EventsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const meta = await attempt(getCities);
  const { city, persona } = resolveSelection(sp, meta.ok ? meta.data : null);
  const page = Math.max(1, Number(first(sp.page) ?? "1") || 1);
  const res = await attempt(() =>
    getEvents(city, persona, {
      category: first(sp.category),
      q: first(sp.q),
      severity: first(sp.severity),
      days: first(sp.days),
      status: first(sp.status),
      sort: first(sp.sort),
      page: String(page),
    }),
  );
  if (!res.ok) return <ErrorState title="Events unavailable" message={res.message} city={city} />;
  const ev = res.data;
  const pages = Math.max(1, Math.ceil(ev.total / ev.page_size));
  const news = ev.sources.find((s) => s.kind === "news");
  const pageHref = (n: number) => {
    const p = new URLSearchParams();
    for (const [k, v] of Object.entries(sp)) list(v).forEach((x) => p.append(k, x));
    p.set("city", city);
    p.set("persona", persona);
    p.set("page", String(n));
    return `/events?${p.toString()}`;
  };
  const filtered = ["q", "category", "severity", "days", "status"].some((k) => first(sp[k]));

  return (
    <>
      <PageHeader
        title="Events"
        updatedAt={news?.updated_at ?? null}
        description={`News reports about ${ev.city}, most relevant first. Open “Details” to see how each one was treated.`}
      />
      <div className="space-y-6">
        <SampleNotice mode={ev.data_mode} />
        <Card className="gap-0 py-0">
          <div className="border-b p-5">
            <Suspense>
              <FilterToolbar counts={ev.category_counts} />
            </Suspense>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-4">
            <p className="text-sm text-muted-foreground" aria-live="polite">
              {filtered || first(sp.status)
                ? `${plural(ev.total, "report")} match`
                : `${plural(ev.total, "report")} counted in the assessment, out of ${ev.total_reports} analysed`}
            </p>
            <Suspense>
              <SortSelect />
            </Suspense>
          </div>
          <div className="p-5">
            {ev.items.length ? (
              <EventList events={ev.items} />
            ) : ev.total_reports === 0 ? (
              <EmptyState title="No reports for this city">
                No recent news could be retrieved for {ev.city}. That is a gap in the information, not a sign that
                nothing is happening.
              </EmptyState>
            ) : (
              <EmptyState title="No reports match these filters">
                Try a wider period, another topic or “All reports”.
              </EmptyState>
            )}
            {pages > 1 ? (
              <nav aria-label="Pagination" className="mt-5 flex items-center justify-between border-t border-border pt-4 text-sm">
                {page > 1 ? (
                  <Link href={pageHref(page - 1)} className="font-medium text-accent-foreground hover:underline">
                    Previous
                  </Link>
                ) : (
                  <span />
                )}
                <span className="text-muted-foreground">
                  Page {page} of {pages}
                </span>
                {page < pages ? (
                  <Link href={pageHref(page + 1)} className="font-medium text-accent-foreground hover:underline">
                    Next
                  </Link>
                ) : (
                  <span />
                )}
              </nav>
            ) : null}
          </div>
        </Card>
        {news ? (
          <Card className="py-3">
            <CardContent>
              <SourceList sources={[news]} dense />
            </CardContent>
          </Card>
        ) : null}
      </div>
    </>
  );
}
