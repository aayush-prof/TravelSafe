import type { Metadata } from "next";
import { Suspense, type ReactNode } from "react";

import { Shell } from "@/components/shell/Shell";
import { getCities } from "@/lib/api";
import { attempt } from "@/lib/attempt";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "TravelSafe", template: "%s | TravelSafe" },
  description: "Travel conditions for city trip research: news, weather, air quality and natural hazards, with honest uncertainty.",
};

export const dynamic = "force-dynamic";

export default async function RootLayout({ children }: { children: ReactNode }) {
  const meta = await attempt(getCities);
  return (
    <html lang="en">
      <body>
        <a
          href="#main"
          className="sr-only z-50 rounded bg-card px-3 py-2 text-foreground focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
        >
          Skip to content
        </a>
        <Suspense fallback={<div className="min-h-screen" />}>
          <Shell meta={meta.ok ? meta.data : null}>{children}</Shell>
        </Suspense>
      </body>
    </html>
  );
}
