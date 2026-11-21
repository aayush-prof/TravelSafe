"use client";

import { RotateCw, ServerCrash } from "lucide-react";
import { useEffect } from "react";

/** Last-resort error boundary. Details go to the console/server log, not the page. */
export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <div role="alert" className="mx-auto mt-8 max-w-lg rounded-xl border border-border bg-card p-6 text-center">
      <ServerCrash aria-hidden className="mx-auto size-7 text-unknown" />
      <h1 className="mt-3 text-lg font-semibold text-foreground">Something went wrong</h1>
      <p className="mt-1.5 text-[15px] text-secondary-foreground">This page couldn&apos;t be shown. Please try again.</p>
      <button
        type="button"
        onClick={reset}
        className="mt-5 inline-flex min-h-9 items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-white hover:bg-primary/90"
      >
        <RotateCw aria-hidden className="size-4" />
        Try again
      </button>
    </div>
  );
}
