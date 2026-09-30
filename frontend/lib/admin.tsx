'use client';

/**
 * Admin console session context — deliberately separate from lib/providers.tsx's
 * useApp()/AppCtx (the user/app-side session). The two never share state: this hook
 * only ever reads /api/auth/admin/session, which is backed by the admin-scoped
 * cookie/token, not the app's user session.
 */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { createContext, useContext, useMemo } from 'react';
import { get } from './api';

export interface AdminInfo {
  id: string;
  name: string;
  email: string;
  role: string;
  last_login: string | null;
}

export type AdminSessionState =
  | { state: 'admin'; admin: AdminInfo }
  | { state: 'user_not_admin' | 'admin_login_required'; user: { name: string; email: string } }
  | { state: 'signed_out' };

type AdminCtx = {
  session: AdminSessionState | undefined;
  loading: boolean;
  admin: AdminInfo | null;
  refresh: () => void;
  clear: () => void;
};

const Ctx = createContext<AdminCtx | null>(null);

export function AdminProvider({ children }: { children: React.ReactNode }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ['admin-session'],
    queryFn: () => get<AdminSessionState>('/auth/admin/session'),
    retry: false,
    staleTime: 10_000,
  });
  const value = useMemo<AdminCtx>(
    () => ({
      session: q.data,
      loading: q.isLoading,
      admin: q.data?.state === 'admin' ? q.data.admin : null,
      refresh: () => qc.invalidateQueries({ queryKey: ['admin-session'] }),
      clear: () => qc.setQueryData(['admin-session'], { state: 'signed_out' }),
    }),
    [q.data, q.isLoading, qc]
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAdmin() {
  const c = useContext(Ctx);
  if (!c) throw new Error('useAdmin must be used inside the /admin layout (AdminProvider)');
  return c;
}
