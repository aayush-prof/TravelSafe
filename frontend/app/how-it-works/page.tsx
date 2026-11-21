import type { Metadata } from "next";

import { ErrorState } from "@/components/common/actions";
import { LevelBadge, PageHeader } from "@/components/common/page";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { getMethodology } from "@/lib/api";
import { attempt } from "@/lib/attempt";
import type { FactorLevel } from "@/lib/types";

export const metadata: Metadata = { title: "How it works" };

const LEVELS: { level: FactorLevel; text: string }[] = [
  { level: "low", text: "No major concerns in the evidence that could be checked." },
  { level: "guarded", text: "Some current concerns worth being aware of." },
  { level: "elevated", text: "Serious or several concerns. Take extra care and check local advice." },
  { level: "high", text: "Severe concerns or an official red alert. Check official advice before travelling." },
  { level: "unknown", text: "No usable data. Never counted as safe, and shown hatched in charts." },
];

const SOURCES = [
  ["News", "Google News RSS; optional NewsAPI and GNews", "Crime, civil, transport, hazards, weather", "No (optional keys)"],
  ["Weather", "OpenWeatherMap, with Open-Meteo as fallback", "Weather", "Optional"],
  ["Weather alerts", "OpenWeatherMap One Call 3.0", "Weather", "Subscription"],
  ["Air quality (measured)", "OpenAQ stations within 25 km", "Air quality", "Free key"],
  ["Air quality (modelled)", "Open-Meteo / CAMS, ~45 km grid", "Context only", "No"],
  ["Earthquakes", "USGS, within 500 km, last 7 days", "Natural hazards", "No"],
  ["Disaster alerts", "GDACS (UN / European Commission), last 14 days", "Natural hazards", "No"],
  ["City information", "Wikipedia and Wikidata", "Context only", "No"],
];

export default async function HowItWorksPage() {
  const res = await attempt(getMethodology);
  if (!res.ok) return <ErrorState title="This page couldn't load" message={res.message} />;
  const m = res.data;
  const factors = (m.parameters.factors ?? {}) as Record<string, { label: string; definition: string }>;
  const relevance = (m.parameters.factor_relevance ?? {}) as Record<string, number>;
  return (
    <>
      <PageHeader
        title="How it works"
        description="TravelSafe checks six factors separately, shows the evidence behind each one, and says plainly when something couldn't be checked."
      />
      <div className="grid gap-4 xl:grid-cols-12">
        <div className="space-y-4 xl:col-span-7">
          <Card>
            <CardHeader>
              <CardTitle>The method in brief</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="list-disc space-y-2.5 pl-4 text-[14px] leading-relaxed text-secondary-foreground marker:text-muted-foreground">
                {m.summary.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Factors</CardTitle>
              <CardDescription>Relevance sets how much each factor counts towards the overall result.</CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Factor</TableHead>
                    <TableHead>What it covers</TableHead>
                    <TableHead className="text-right">Relevance</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {Object.entries(factors).map(([k, f]) => (
                    <TableRow key={k}>
                      <TableCell className="font-medium whitespace-nowrap">{f.label}</TableCell>
                      <TableCell className="text-[13px] text-muted-foreground">{f.definition}</TableCell>
                      <TableCell className="text-right tabular">{relevance[k]?.toFixed(1) ?? ""}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Data sources</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Source</TableHead>
                    <TableHead>Provider and scope</TableHead>
                    <TableHead>Used for</TableHead>
                    <TableHead>Key needed</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {SOURCES.map(([a, b, c, d]) => (
                    <TableRow key={a}>
                      <TableCell className="font-medium whitespace-nowrap">{a}</TableCell>
                      <TableCell className="text-[13px] text-muted-foreground">{b}</TableCell>
                      <TableCell className="text-[13px]">{c}</TableCell>
                      <TableCell className="text-[13px] whitespace-nowrap">{d}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </div>
        <div className="space-y-4 xl:col-span-5">
          <Card>
            <CardHeader>
              <CardTitle>What the levels mean</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-3">
                {LEVELS.map((l) => (
                  <li key={l.level} className="flex items-start gap-3">
                    <span className="w-28 shrink-0">
                      <LevelBadge level={l.level} />
                    </span>
                    <span className="text-[13px] text-secondary-foreground">{l.text}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Limits to keep in mind</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="list-disc space-y-2 pl-4 text-[13px] text-secondary-foreground marker:text-muted-foreground">
                {m.limitations.map((l) => (
                  <li key={l}>{l}</li>
                ))}
              </ul>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Formulas</CardTitle>
              <CardDescription>Methodology version {m.version}. Parameters are reasoned heuristics, not calibrated probabilities.</CardDescription>
            </CardHeader>
            <CardContent>
              <Collapsible>
                <CollapsibleTrigger className="text-sm font-medium text-accent-foreground hover:underline">Show the formulas</CollapsibleTrigger>
                <CollapsibleContent>
                  <dl className="mt-3 space-y-3">
                    {Object.entries(m.formulas).map(([k, v]) => (
                      <div key={k}>
                        <dt className="text-xs text-muted-foreground">{k.replaceAll("_", " ")}</dt>
                        <dd className="mt-0.5 rounded-md bg-secondary px-3 py-2 text-[13px] leading-relaxed">{v}</dd>
                      </div>
                    ))}
                  </dl>
                </CollapsibleContent>
              </Collapsible>
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
