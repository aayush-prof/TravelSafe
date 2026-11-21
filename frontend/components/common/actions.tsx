"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { CloudOff, RotateCw } from "lucide-react";

import { refreshCity } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** Clears the backend cache for the city, then re-renders with fresh data. */
export function RetryButton({ city, label = "Try again", variant = "outline" }: { city?: string; label?: string; variant?: "outline" | "default" }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [failed, setFailed] = useState(false);
  const run = () =>
    start(async () => {
      const r = city ? await refreshCity(city) : { ok: true };
      setFailed(!r.ok);
      router.refresh();
    });
  return (
    <span className="inline-flex items-center gap-2">
      <Button variant={variant} size="sm" onClick={run} disabled={pending} aria-busy={pending}>
        <RotateCw aria-hidden className={cn(pending && "animate-spin")} />
        {pending ? "Trying again…" : label}
      </Button>
      {failed && !pending ? (
        <span role="status" className="text-xs text-elevated">
          Couldn&apos;t reach the service.
        </span>
      ) : null}
    </span>
  );
}

export function ErrorState({ title, message, city }: { title: string; message: string; city?: string }) {
  return (
    <div role="alert" className="mx-auto mt-10 max-w-lg rounded-xl border bg-card p-8 text-center shadow-[var(--shadow-card)]">
      <CloudOff aria-hidden className="mx-auto size-7 text-unknown" />
      <h1 className="mt-3 text-lg font-semibold">{title}</h1>
      <p className="mt-1.5 text-[15px] text-secondary-foreground">{message}</p>
      <p className="mt-1 text-sm text-muted-foreground">No figures are shown while information is unavailable.</p>
      <div className="mt-5">
        <RetryButton city={city} variant="default" />
      </div>
    </div>
  );
}
