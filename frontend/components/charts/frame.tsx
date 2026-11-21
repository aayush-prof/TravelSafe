"use client";

import { useState, type ReactNode } from "react";
import { BarChart3, Table2 } from "lucide-react";

import { Button } from "@/components/ui/button";

/** Chart with a table view: colour is never the only way to read a value. */
export function ChartFrame({ chart, table, label }: { chart: ReactNode; table: ReactNode; label: string }) {
  const [asTable, setAsTable] = useState(false);
  return (
    <div>
      <div className="mb-2 flex justify-end">
        <Button variant="ghost" size="sm" onClick={() => setAsTable((v) => !v)} aria-pressed={asTable} className="h-7 text-xs text-muted-foreground">
          {asTable ? <BarChart3 aria-hidden /> : <Table2 aria-hidden />}
          {asTable ? "Show chart" : "Show table"}
        </Button>
      </div>
      {asTable ? <div className="overflow-x-auto">{table}</div> : <figure aria-label={label}>{chart}</figure>}
    </div>
  );
}

export function TooltipBox({ title, rows }: { title: string; rows: { label: string; value: string; color?: string }[] }) {
  return (
    <div className="rounded-md border bg-popover px-3 py-2 text-xs shadow-[var(--shadow-pop)]">
      <p className="mb-1 font-medium text-foreground">{title}</p>
      {rows.map((r) => (
        <p key={r.label} className="flex items-center gap-2 text-muted-foreground">
          {r.color ? <span aria-hidden className="size-2 rounded-[2px]" style={{ background: r.color }} /> : null}
          <span className="flex-1">{r.label}</span>
          <span className="font-medium text-foreground tabular">{r.value}</span>
        </p>
      ))}
    </div>
  );
}

export const AXIS = { stroke: "var(--muted-foreground)", fontSize: 11, tickLine: false, axisLine: false } as const;
export const GRID = "var(--border)";
