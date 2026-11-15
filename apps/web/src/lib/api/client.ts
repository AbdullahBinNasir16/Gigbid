// Typed API client. `schema.d.ts` is generated from FastAPI's OpenAPI schema
// (npm run gen:api) — do not hand-edit it.
import createClient, { type Middleware } from "openapi-fetch";
import type { paths, components } from "./schema";

export type JobCard = components["schemas"]["JobCard"];
export type JobDetail = components["schemas"]["JobDetail"];
export type ApprovalItem = components["schemas"]["ApprovalItem"];
export type Settings = components["schemas"]["Settings"];
export type Health = components["schemas"]["Health"];
export type MemoryItem = components["schemas"]["MemoryItem"];

const TOKEN_KEY = "gigbid.token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(t: string | null) {
  try {
    if (t) localStorage.setItem(TOKEN_KEY, t);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage blocked: session lasts for this page only */
  }
}

const auth: Middleware = {
  onRequest({ request }) {
    const t = getToken();
    if (t) request.headers.set("Authorization", `Bearer ${t}`);
    return request;
  },
  onResponse({ response }) {
    if (response.status === 401 && !location.pathname.endsWith("/login")) {
      setToken(null);
      location.assign(`${import.meta.env.BASE_URL}login`);
    }
    return response;
  },
};

// Same origin by default; a static deploy (GitHub Pages) sets VITE_API_BASE to the API URL.
export const API_BASE: string = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");
export const api = createClient<paths>({ baseUrl: API_BASE });
api.use(auth);

export function streamUrl(threadId: string): string {
  return `${API_BASE}/api/runs/${encodeURIComponent(threadId)}/stream?token=${encodeURIComponent(getToken() ?? "")}`;
}
