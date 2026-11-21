import { Skeleton } from "@/components/ui/skeleton";

/** Mirrors the dashboard grid so content doesn't jump when it arrives. */
export default function Loading() {
  return (
    <div aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading…</span>
      <Skeleton className="h-8 w-56" />
      <Skeleton className="mt-2 mb-6 h-4 w-96 max-w-full" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-32 rounded-xl" />
        ))}
      </div>
      <div className="mt-4 grid gap-4 xl:grid-cols-12">
        <Skeleton className="h-96 rounded-xl xl:col-span-8" />
        <Skeleton className="h-96 rounded-xl xl:col-span-4" />
      </div>
    </div>
  );
}
