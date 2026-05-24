import { useAuthStore } from "@/stores/auth";

const BASE = "/api";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

/** Attempt a single silent token refresh. Returns the new access token or null. */
let _refreshPromise: Promise<string | null> | null = null;
async function tryRefresh(): Promise<string | null> {
  // Deduplicate concurrent refresh attempts
  if (_refreshPromise) return _refreshPromise;
  _refreshPromise = (async () => {
    const refreshToken = useAuthStore.getState().refreshToken;
    if (!refreshToken) return null;
    try {
      const res = await fetch(`${BASE}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!res.ok) {
        useAuthStore.getState().logout();
        return null;
      }
      const data = await res.json();
      useAuthStore.getState().setTokens(data.access_token, data.refresh_token);
      return data.access_token as string;
    } catch {
      useAuthStore.getState().logout();
      return null;
    } finally {
      _refreshPromise = null;
    }
  })();
  return _refreshPromise;
}

export async function api<T>(
  path: string,
  init: RequestInit & { auth?: boolean } = {},
): Promise<T> {
  const { auth = true, headers, ...rest } = init;
  const h = new Headers(headers);
  if (!h.has("Content-Type") && rest.body) h.set("Content-Type", "application/json");

  if (auth) {
    const token = useAuthStore.getState().accessToken;
    if (token) h.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(`${BASE}${path}`, { ...rest, headers: h });

  // Auto-refresh on 401 (expired access token)
  if (res.status === 401 && auth) {
    const newToken = await tryRefresh();
    if (newToken) {
      const h2 = new Headers(headers);
      if (!h2.has("Content-Type") && rest.body) h2.set("Content-Type", "application/json");
      h2.set("Authorization", `Bearer ${newToken}`);
      const retry = await fetch(`${BASE}${path}`, { ...rest, headers: h2 });
      if (retry.status === 204) return undefined as T;
      const retryBody = await retry.json().catch(() => null);
      if (!retry.ok) throw new ApiError(retry.status, retryBody?.detail ?? retryBody ?? retry.statusText);
      return retryBody as T;
    }
    // Refresh failed → already logged out in tryRefresh(), fall through to throw
  }

  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, body?.detail ?? body ?? res.statusText);
  return body as T;
}
