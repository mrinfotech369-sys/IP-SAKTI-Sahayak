'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Badge, ErrorState, Field, PageHeader, Spinner, fmtDateTime } from '@/components/ui';
import { get, patch } from '@/lib/api';
import { useAdmin } from '@/lib/admin';

export default function AdminUsers() {
  const qc = useQueryClient();
  const { admin } = useAdmin();
  const [q, setQ] = useState('');
  const [role, setRole] = useState('');
  const [status, setStatus] = useState('');
  const query = new URLSearchParams({ ...(q && { q }), ...(role && { role }), ...(status && { status }) }).toString();
  const rows = useQuery({ queryKey: ['admin-users', q, role, status], queryFn: () => get<any[]>(`/admin/users${query ? `?${query}` : ''}`) });
  const upd = useMutation({ mutationFn: ({ id, body }: any) => patch(`/admin/users/${id}`, body), onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-users'] }) });

  return (
    <div>
      <PageHeader eyebrow="Admin console" title="Users" subtitle="View, search, activate/deactivate and manage roles across all workspaces." />
      <div className="mb-4 flex flex-wrap gap-2 text-sm">
        <Field label=""><input placeholder="Search name or email…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search users" /></Field>
        <Field label=""><select value={role} onChange={(e) => setRole(e.target.value)} aria-label="Role filter"><option value="">All roles</option><option value="ADMIN">ADMIN</option><option value="USER">USER</option></select></Field>
        <Field label=""><select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status filter"><option value="">All statuses</option><option value="active">Active</option><option value="disabled">Disabled</option></select></Field>
      </div>
      {rows.isLoading && <Spinner />}
      {rows.isError && <ErrorState error={rows.error} onRetry={() => rows.refetch()} />}
      {upd.isError && <ErrorState error={upd.error} />}
      <div className="overflow-x-auto rounded-lg border border-surface-border bg-surface-elevated">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface-muted text-xs text-text-secondary"><tr><th className="px-3 py-2">User</th><th>Role</th><th>Workspaces</th><th>Last login</th><th>Status</th></tr></thead>
          <tbody>{rows.data?.map((u) => (
            <tr key={u.id} className="border-t border-surface-border align-top">
              <td className="px-3 py-2"><div className="font-medium">{u.name}</div><div className="text-xs text-text-muted">{u.email}</div></td>
              <td>
                <select className="py-0.5 text-xs" value={u.role} disabled={u.id === admin?.id}
                  onChange={(e) => upd.mutate({ id: u.id, body: { role: e.target.value } })} aria-label="Role" title={u.id === admin?.id ? 'You cannot change your own role' : undefined}>
                  <option>USER</option><option>ADMIN</option>
                </select>
              </td>
              <td className="text-xs">{u.workspaces?.map((w: any) => `${w.workspace} (${w.role.toLowerCase()})`).join(', ') || (typeof u.workspaces === 'number' ? u.workspaces : '—')}</td>
              <td className="text-xs">{fmtDateTime(u.last_login)}</td>
              <td>
                <button disabled={u.id === admin?.id} onClick={() => upd.mutate({ id: u.id, body: { is_active: !u.is_active } })} title={u.id === admin?.id ? 'You cannot disable your own account' : undefined}>
                  <Badge tone={u.is_active ? 'ok' : 'danger'}>{u.is_active ? 'active — click to disable' : 'disabled — click to enable'}</Badge>
                </button>
              </td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}
