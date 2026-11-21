"use server";

import { refreshCityData } from "@/lib/api";

/** Server action used by Refresh and Try again buttons. Runs on the Next.js server, so no CORS is involved. */
export async function refreshCity(city: string): Promise<{ ok: boolean }> {
  return { ok: await refreshCityData(city) };
}
