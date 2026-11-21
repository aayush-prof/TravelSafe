import { ApiError } from "./api";

export type Attempt<T> = { ok: true; data: T } | { ok: false; message: string; status: number | null };

/** Run an API call and turn failures into a renderable result instead of throwing. */
export async function attempt<T>(fn: () => Promise<T>): Promise<Attempt<T>> {
  try {
    return { ok: true, data: await fn() };
  } catch (e) {
    if (e instanceof ApiError) return { ok: false, message: e.message, status: e.status };
    console.error(e);
    return { ok: false, message: "Unexpected error while loading data.", status: null };
  }
}
