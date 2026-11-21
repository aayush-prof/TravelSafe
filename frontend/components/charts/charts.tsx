"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { FACTOR_COLOR, FACTOR_SHORT } from "@/lib/factors";
import type { AirTrendPoint, FactorKey, TimelineDay, WeatherHour } from "@/lib/types";

import { AXIS, ChartFrame, GRID, TooltipBox } from "./frame";

type TipProps = { active?: boolean; payload?: ReadonlyArray<{ payload?: Record<string, unknown> }> };

const pl = (p: TipProps["payload"]): Record<string, unknown> => p?.[0]?.payload ?? {};

const dayLabel = (d: string) =>
  new Date(`${d}T12:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });

// ---------------------------------------------------------------------------
// Event timeline: distinct incidents per day, stacked by factor
// ---------------------------------------------------------------------------
const TL_KEYS: FactorKey[] = ["crime", "civil", "transport", "disaster", "weather"];

export function EventTimelineChart({ days }: { days: TimelineDay[] }) {
  const present = TL_KEYS.filter((k) => days.some((d) => d[k as keyof TimelineDay] as number));
  const data = days.map((d) => ({ ...d, label: dayLabel(d.date) }));
  const chart = (
    <>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -8 }} barCategoryGap="22%">
            <CartesianGrid vertical={false} stroke={GRID} />
            <XAxis dataKey="label" {...AXIS} interval="preserveStartEnd" minTickGap={16} />
            <YAxis allowDecimals={false} {...AXIS} width={44} />
            <Tooltip
              cursor={{ fill: "var(--secondary)" }}
              content={({ active, payload }: TipProps) =>
                active && payload?.[0]?.payload ? (
                  <TooltipBox
                    title={String(pl(payload).label)}
                    rows={present.map((k) => ({ label: FACTOR_SHORT[k], value: String(pl(payload)[k] ?? 0), color: FACTOR_COLOR[k] }))}
                  />
                ) : null
              }
            />
            {present.map((k, i) => (
              <Bar key={k} dataKey={k} stackId="a" fill={FACTOR_COLOR[k]} stroke="var(--card)" strokeWidth={1}
                radius={i === present.length - 1 ? [3, 3, 0, 0] : 0} isAnimationActive={false} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground" aria-label="Legend">
        {present.map((k) => (
          <li key={k} className="flex items-center gap-1.5">
            <span aria-hidden className="size-2.5 rounded-[2px]" style={{ background: FACTOR_COLOR[k] }} />
            {FACTOR_SHORT[k]}
          </li>
        ))}
      </ul>
    </>
  );
  const table = (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Day</TableHead>
          {present.map((k) => (
            <TableHead key={k} className="text-right">{FACTOR_SHORT[k]}</TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {data.filter((d) => present.some((k) => d[k as keyof TimelineDay])).map((d) => (
          <TableRow key={d.date}>
            <TableCell>{d.label}</TableCell>
            {present.map((k) => (
              <TableCell key={k} className="text-right tabular">{d[k as keyof TimelineDay]}</TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
  return <ChartFrame label="Distinct incidents per day by factor" chart={chart} table={table} />;
}

// ---------------------------------------------------------------------------
// Contribution: share of the overall signal per assessed factor
// ---------------------------------------------------------------------------
export function ContributionChart({ items }: { items: { key: FactorKey; label: string; share: number }[] }) {
  const data = items.map((i) => ({ ...i, pct: Math.round(i.share * 100) }));
  const chart = (
    <div style={{ height: 36 * data.length + 12 }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 40, bottom: 0, left: 0 }} barCategoryGap={8}>
          <XAxis type="number" domain={[0, 100]} hide />
          <YAxis type="category" dataKey="label" {...AXIS} width={128} tick={{ fill: "var(--foreground)", fontSize: 12 }} />
          <Tooltip
            cursor={{ fill: "var(--secondary)" }}
            content={({ active, payload }: TipProps) =>
              active && payload?.[0]?.payload ? (
                <TooltipBox title={String(pl(payload).label)} rows={[{ label: "Share of overall signal", value: `${pl(payload).pct}%` }]} />
              ) : null
            }
          />
          <Bar dataKey="pct" radius={[0, 4, 4, 0]} isAnimationActive={false}
            label={{ position: "right", fill: "var(--foreground)", fontSize: 12, formatter: (v: unknown) => `${v}%` }}>
            {data.map((d) => (
              <Cell key={d.key} fill={FACTOR_COLOR[d.key]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
  const table = (
    <Table>
      <TableHeader><TableRow><TableHead>Factor</TableHead><TableHead className="text-right">Share</TableHead></TableRow></TableHeader>
      <TableBody>
        {data.map((d) => (
          <TableRow key={d.key}><TableCell>{d.label}</TableCell><TableCell className="text-right tabular">{d.pct}%</TableCell></TableRow>
        ))}
      </TableBody>
    </Table>
  );
  return <ChartFrame label="Share of the overall signal by factor" chart={chart} table={table} />;
}

// ---------------------------------------------------------------------------
// Weather: temperature (line) and precipitation (bars) as two aligned charts
// ---------------------------------------------------------------------------
function hourLabel(iso: string, timeZone?: string) {
  return new Date(iso).toLocaleString("en-GB", { weekday: "short", hour: "2-digit", minute: "2-digit", timeZone });
}

export function WeatherForecastChart({ hours, stepHours, timeZone }: { hours: WeatherHour[]; stepHours: number; timeZone: string }) {
  const data = hours.map((h) => ({
    ...h,
    label: hourLabel(h.time, timeZone),
    tick: new Date(h.time).toLocaleString("en-GB", { weekday: "short", hour: "2-digit", timeZone }),
  }));
  const hasPrecip = data.some((d) => typeof d.precip_mm === "number");
  const tip = ({ active, payload }: TipProps) =>
    active && payload?.[0]?.payload ? (
      <TooltipBox
        title={String(pl(payload).label)}
        rows={[
          { label: "Temperature", value: typeof pl(payload).temp_c === "number" ? `${(pl(payload).temp_c as number).toFixed(1)} °C` : "n/a" },
          { label: `Precipitation (${stepHours} h)`, value: typeof pl(payload).precip_mm === "number" ? `${pl(payload).precip_mm} mm` : "n/a" },
          ...(typeof pl(payload).precip_prob === "number" ? [{ label: "Chance", value: `${Math.round((pl(payload).precip_prob as number) * 100)}%` }] : []),
        ]}
      />
    ) : null;
  const chart = (
    <div className="space-y-1">
      <p className="text-xs text-muted-foreground">Temperature, °C</p>
      <div className="h-44">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} syncId="wx" margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke={GRID} />
            <XAxis dataKey="tick" {...AXIS} interval="preserveStartEnd" minTickGap={28} />
            <YAxis {...AXIS} width={40} domain={["dataMin - 2", "dataMax + 2"]} tickFormatter={(v: number) => `${Math.round(v)}°`} />
            <Tooltip content={tip} cursor={{ stroke: "var(--muted-foreground)", strokeDasharray: "3 3" }} />
            <Line type="monotone" dataKey="temp_c" stroke="var(--brand)" strokeWidth={2} dot={false} activeDot={{ r: 4 }} isAnimationActive={false} connectNulls={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      {hasPrecip ? (
        <>
          <p className="pt-2 text-xs text-muted-foreground">Precipitation, mm per {stepHours === 1 ? "hour" : `${stepHours} hours`}</p>
          <div className="h-24">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} syncId="wx" margin={{ top: 2, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid vertical={false} stroke={GRID} />
                <XAxis dataKey="tick" hide />
                <YAxis {...AXIS} width={40} allowDecimals />
                <Tooltip content={tip} cursor={{ fill: "var(--secondary)" }} />
                <Bar dataKey="precip_mm" fill="var(--teal)" radius={[2, 2, 0, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      ) : null}
    </div>
  );
  const table = (
    <Table>
      <TableHeader><TableRow><TableHead>Time</TableHead><TableHead className="text-right">°C</TableHead><TableHead className="text-right">mm</TableHead><TableHead className="text-right">Chance</TableHead></TableRow></TableHeader>
      <TableBody>
        {data.map((d) => (
          <TableRow key={d.time}>
            <TableCell>{d.label}</TableCell>
            <TableCell className="text-right tabular">{d.temp_c ?? "n/a"}</TableCell>
            <TableCell className="text-right tabular">{d.precip_mm ?? "n/a"}</TableCell>
            <TableCell className="text-right tabular">{typeof d.precip_prob === "number" ? `${Math.round(d.precip_prob * 100)}%` : "n/a"}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
  return <ChartFrame label="Forecast for the next 48 hours" chart={chart} table={table} />;
}


// ---------------------------------------------------------------------------
// Air quality trend (measured PM2.5, or modelled for context)
// ---------------------------------------------------------------------------
const PM25_BANDS = [
  { y1: 0, y2: 9, label: "Good" },
  { y1: 9, y2: 35.4, label: "Moderate" },
  { y1: 35.4, y2: 55.4, label: "Unhealthy for sensitive groups" },
  { y1: 55.4, y2: 125.4, label: "Unhealthy" },
];

export function AirTrendChart({ points, modelled = false }: { points: AirTrendPoint[]; modelled?: boolean }) {
  const data = points.filter((p) => typeof p.pm25 === "number").map((p) => ({ ...p, label: hourLabel(p.time),
    tick: new Date(p.time).toLocaleDateString("en-GB", { day: "numeric", month: "short" }) }));
  const max = Math.max(...data.map((d) => d.pm25 as number), 10);
  const chart = (
    <div className="h-48">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
          {PM25_BANDS.filter((b) => b.y1 < max * 1.15).map((b, i) => (
            <ReferenceArea key={b.label} y1={b.y1} y2={Math.min(b.y2, max * 1.15)} fill="var(--secondary)" fillOpacity={i % 2 ? 0.9 : 0} ifOverflow="hidden" />
          ))}
          <CartesianGrid vertical={false} stroke={GRID} />
          <XAxis dataKey="tick" {...AXIS} interval="preserveStartEnd" minTickGap={40} />
          <YAxis {...AXIS} width={40} domain={[0, Math.ceil(max * 1.15)]} />
          <Tooltip
            cursor={{ stroke: "var(--muted-foreground)", strokeDasharray: "3 3" }}
            content={({ active, payload }: TipProps) =>
              active && payload?.[0]?.payload ? (
                <TooltipBox title={String(pl(payload).label)} rows={[{ label: modelled ? "PM2.5 (modelled)" : "PM2.5 (measured)", value: `${pl(payload).pm25} µg/m³` }]} />
              ) : null
            }
          />
          <Line type="monotone" dataKey="pm25" stroke={modelled ? "var(--muted-foreground)" : "var(--teal)"} strokeWidth={2}
            strokeDasharray={modelled ? "5 4" : undefined} dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
  const table = (
    <Table>
      <TableHeader><TableRow><TableHead>Hour</TableHead><TableHead className="text-right">PM2.5 µg/m³</TableHead></TableRow></TableHeader>
      <TableBody>
        {data.map((d) => (
          <TableRow key={d.time}><TableCell>{d.label}</TableCell><TableCell className="text-right tabular">{d.pm25}</TableCell></TableRow>
        ))}
      </TableBody>
    </Table>
  );
  return <ChartFrame label={modelled ? "Modelled PM2.5 trend" : "Measured PM2.5 trend"} chart={chart} table={table} />;
}

// ---------------------------------------------------------------------------
// Simple counts (crime breakdown, weekly reports)
// ---------------------------------------------------------------------------
export function CountBarChart({ items, label, valueLabel }: { items: { label: string; count: number }[]; label: string; valueLabel: string }) {
  const chart = (
    <div className="h-52">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={items} margin={{ top: 16, right: 4, bottom: 0, left: -8 }} barCategoryGap="28%">
          <CartesianGrid vertical={false} stroke={GRID} />
          <XAxis dataKey="label" {...AXIS} interval={0} tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} />
          <YAxis allowDecimals={false} {...AXIS} width={44} />
          <Tooltip
            cursor={{ fill: "var(--secondary)" }}
            content={({ active, payload }: TipProps) =>
              active && payload?.[0]?.payload ? <TooltipBox title={String(pl(payload).label)} rows={[{ label: valueLabel, value: String(pl(payload).count) }]} /> : null
            }
          />
          <Bar dataKey="count" fill="var(--brand)" radius={[4, 4, 0, 0]} isAnimationActive={false}
            label={{ position: "top", fill: "var(--foreground)", fontSize: 11 }} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
  const table = (
    <Table>
      <TableHeader><TableRow><TableHead>{label}</TableHead><TableHead className="text-right">{valueLabel}</TableHead></TableRow></TableHeader>
      <TableBody>
        {items.map((d) => (
          <TableRow key={d.label}><TableCell>{d.label}</TableCell><TableCell className="text-right tabular">{d.count}</TableCell></TableRow>
        ))}
      </TableBody>
    </Table>
  );
  return <ChartFrame label={label} chart={chart} table={table} />;
}
