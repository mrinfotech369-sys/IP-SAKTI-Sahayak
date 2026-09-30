/**
 * API client. The browser only talks to this origin; Next.js rewrites /api/* to FastAPI.
 * Auth is an httpOnly cookie; writes carry X-Requested-With (CSRF defence).
 */
const API = process.env.NEXT_PUBLIC_API_BASE_URL || '/api';
const WS_KEY = 'ipsakti.workspace';

export class ApiError extends Error {
  code: string;
  status: number;
  details?: unknown;
  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function getWorkspaceId(): string | null {
  try {
    return window.localStorage.getItem(WS_KEY);
  } catch {
    return null;
  }
}

export function setWorkspaceId(id: string | null) {
  try {
    if (id) window.localStorage.setItem(WS_KEY, id);
    else window.localStorage.removeItem(WS_KEY);
  } catch {
    /* storage unavailable: server falls back to the first workspace */
  }
}

type Opts = { method?: string; body?: unknown; form?: FormData; raw?: boolean };

export async function api<T = any>(path: string, opts: Opts = {}): Promise<T> {
  const headers: Record<string, string> = { 'X-Requested-With': 'ipsakti' };
  const ws = typeof window !== 'undefined' ? getWorkspaceId() : null;
  if (ws) headers['X-Workspace-Id'] = ws;
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json';
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, {
      method: opts.method || (opts.body !== undefined || opts.form ? 'POST' : 'GET'),
      headers,
      credentials: 'include',
      body: opts.form ?? (opts.body !== undefined ? JSON.stringify(opts.body) : undefined),
      cache: 'no-store',
    });
  } catch {
    throw new ApiError(0, 'NETWORK_ERROR', 'Cannot reach the IP-SAKTI API. Check that the backend is running and try again.');
  }
  if (opts.raw) {
    if (!res.ok) throw new ApiError(res.status, 'HTTP_ERROR', `Request failed (${res.status}).`);
    return (await res.text()) as T;
  }
  let body: any = null;
  try {
    body = await res.json();
  } catch {
    throw new ApiError(res.status, 'BAD_RESPONSE', `The server returned an unexpected response (HTTP ${res.status}).`);
  }
  if (!res.ok || body?.success === false) {
    const e = body?.error || {};
    // A 401 from an /admin/* call (or while on an /admin page) means the *admin* session is
    // missing/expired — send back to the separate admin login, never the app's user login.
    if (res.status === 401 && typeof window !== 'undefined' && !path.startsWith('/auth/')) {
      const inAdminArea = path.startsWith('/admin/') || window.location.pathname.startsWith('/admin');
      const loginPath = inAdminArea ? '/admin/login' : '/login';
      const next = encodeURIComponent(window.location.pathname + window.location.search);
      const expired = e.code === 'SESSION_EXPIRED' || e.code === 'ADMIN_SESSION_EXPIRED';
      window.location.href = `${loginPath}?next=${next}&reason=${expired ? 'expired' : 'auth'}`;
    }
    throw new ApiError(res.status, e.code || 'HTTP_ERROR', e.message || `Request failed (HTTP ${res.status}).`, e.details);
  }
  return body.data as T;
}

export const get = <T = any>(p: string) => api<T>(p);
export const post = <T = any>(p: string, body: unknown = {}) => api<T>(p, { method: 'POST', body });
export const patch = <T = any>(p: string, body: unknown) => api<T>(p, { method: 'PATCH', body });
export const del = <T = any>(p: string) => api<T>(p, { method: 'DELETE' });
