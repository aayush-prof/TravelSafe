import type { Metadata } from "next";
import { FileDown, Printer } from "lucide-react";

import { ErrorState } from "@/components/common/actions";
import { LevelBadge, PageHeader, SampleNotice } from "@/components/common/page";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { getCities, getOverview } from "@/lib/api";
import { attempt } from "@/lib/attempt";
import { PUBLIC_API_BASE, date } from "@/lib/format";
import { resolveSelection, type SearchParams } from "@/lib/selection";

export const metadata: Metadata = { title: "Reports" };

export default async function ReportsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const meta = await attempt(getCities);
  const { city, persona } = resolveSelection(sp, meta.ok ? meta.data : null);
  const res = await attempt(() => getOverview(city, persona));
  if (!res.ok) return <ErrorState title="Reports unavailable" message={res.message} city={city} />;
  const ov = res.data;
  const base = `${PUBLIC_API_BASE}/api/cities/${encodeURIComponent(city)}/report?persona=${encodeURIComponent(persona)}`;

  return (
    <>
      <PageHeader
        title="Reports"
        updatedAt={ov.updated_at}
        description="A printable travel briefing built from exactly the assessment shown in the app."
      />
      <SampleNotice mode={ov.data_mode} />
      <div className="grid gap-4 xl:grid-cols-12">
        <Card className="xl:col-span-8">
          <CardHeader>
            <CardDescription>Travel briefing preview</CardDescription>
            <CardTitle className="text-2xl tracking-tight">{ov.city.name}</CardTitle>
            <CardDescription>
              For {ov.persona.name.toLowerCase()} travellers. Covers {date(ov.period.start)} to {date(ov.period.end)}.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap items-center gap-2">
              <LevelBadge level={ov.general.level} label={ov.general.label} />
              <span className="text-[13px] text-muted-foreground">
                {ov.coverage.label}, {ov.coverage.factors_assessed} of {ov.coverage.factors_total} factors assessed
              </span>
            </div>
            <p className="mt-3 text-sm text-secondary-foreground">{ov.general.summary}</p>
            {ov.critical_alerts.length ? (
              <ul className="mt-3 space-y-1 text-[13px]">
                {ov.critical_alerts.map((c, i) => (
                  <li key={i} className="font-medium text-high">
                    {c.title}
                  </li>
                ))}
              </ul>
            ) : null}
            <Table className="mt-4">
              <TableHeader>
                <TableRow>
                  <TableHead>Factor</TableHead>
                  <TableHead>Level</TableHead>
                  <TableHead>Summary</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {ov.factors.map((f) => (
                  <TableRow key={f.key}>
                    <TableCell className="font-medium whitespace-nowrap">{f.label}</TableCell>
                    <TableCell>
                      <LevelBadge level={f.level} />
                    </TableCell>
                    <TableCell className="text-[13px] text-muted-foreground">{f.summary}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <div className="mt-6 flex flex-wrap gap-2">
              <Button asChild variant="brand">
                <a href={base}>
                  <FileDown aria-hidden />
                  Download PDF
                </a>
              </Button>
              <Button asChild variant="outline">
                <a href={`${base}&format=html&download=false`} target="_blank" rel="noopener noreferrer">
                  <Printer aria-hidden />
                  Open printable version
                  <span className="sr-only">(opens in a new tab)</span>
                </a>
              </Button>
            </div>
          </CardContent>
        </Card>
        <Card className="xl:col-span-4">
          <CardHeader>
            <CardTitle>What the briefing contains</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-disc space-y-2 pl-4 text-[13px] text-secondary-foreground marker:text-muted-foreground">
              <li>The overall result, the result for your traveller profile, data coverage and key takeaways.</li>
              <li>Any active alerts, and every factor with its level, including the ones that couldn&apos;t be assessed.</li>
              <li>The most relevant recent events, with how reliable each report is.</li>
              <li>Weather, air quality and natural hazards, precautions, sources with attribution, and the method&apos;s limits.</li>
            </ul>
            <p className="mt-4 text-[13px] text-muted-foreground">To prepare a briefing for another city or profile, change it in the top bar.</p>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
