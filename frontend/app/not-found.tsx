import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto mt-8 max-w-lg rounded-xl border border-border bg-card p-6 text-center">
      <h1 className="text-lg font-semibold text-foreground">Page not found</h1>
      <p className="mt-1.5 text-[15px] text-secondary-foreground">That address isn&apos;t part of TravelSafe.</p>
      <Link href="/" className="mt-4 inline-block text-sm font-medium text-accent-foreground hover:underline">
        Go to the overview
      </Link>
    </div>
  );
}
