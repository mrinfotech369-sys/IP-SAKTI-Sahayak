'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Badge, ErrorState, PageHeader, Spinner, fmtDateTime } from '@/components/ui';
import { get, patch } from '@/lib/api';

export default function AdminUsers() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['admin-users'], queryFn: () => get<any[]>('/admin/users') });
  const upd = useMutation({ mutationFn: ({ id, body }: any) => patch(`/admin/users/${id}`, body), onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-users'] }) });
  return (
    <div>
      <PageHeader eyebrow="Admin" title="Users" />
      {q.isLoading && <Spinner />}
      {q.isError && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {upd.isError && <ErrorState error={upd.error} />}
      <div className="overflow-x-auto rounded-lg border border-surface-border bg-surface-elevated">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface-muted text-xs text-text-secondary"><tr><th className="px-3 py-2">User</th><th>Role</th><th>Workspaces</th><th>Last login</th><th>Status</th></tr></thead>
          <tbody>{q.data?.map((u) => (
            <tr key={u.id} className="border-t border-surface-border">
              <td className="px-3 py-2"><div className="font-medium">{u.name}</div><div className="text-xs text-text-muted">{u.email}</div></td>
              <td><select className="py-0.5 text-xs" value={u.role} onChange={(e) => upd.mutate({ id: u.id, body: { role: e.target.value } })} aria-label="Role"><option>USER</option><option>ADMIN</option></select></td>
              <td>{u.workspaces}</td><td className="text-xs">{fmtDateTime(u.last_login)}</td>
              <td><button onClick={() => upd.mutate({ id: u.id, body: { is_active: !u.is_active } })}><Badge tone={u.is_active ? 'ok' : 'danger'}>{u.is_active ? 'active — click to disable' : 'disabled — click to enable'}</Badge></button></td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}
