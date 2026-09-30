'use client';

import { useQuery } from '@tanstack/react-query';
import { Badge, ErrorState, PageHeader, Spinner, fmtDate } from '@/components/ui';
import { get } from '@/lib/api';

export default function AdminWorkspaces() {
  const q = useQuery({ queryKey: ['admin-ws'], queryFn: () => get<any[]>('/admin/workspaces') });
  return (
    <div>
      <PageHeader eyebrow="Admin" title="Workspaces" />
      {q.isLoading && <Spinner />}
      {q.isError && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      <div className="overflow-x-auto rounded-lg border border-surface-border bg-surface-elevated">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface-muted text-xs text-text-secondary"><tr><th className="px-3 py-2">Workspace</th><th>Mode</th><th>Retention</th><th>Members</th><th>Innovations</th><th>Created</th></tr></thead>
          <tbody>{q.data?.map((w) => (
            <tr key={w.id} className="border-t border-surface-border"><td className="px-3 py-2 font-medium">{w.name}</td>
              <td>{w.confidential_mode ? <Badge tone="danger">confidential</Badge> : <Badge>standard</Badge>}</td><td className="text-xs">{w.retention_policy}</td>
              <td>{w.members}</td><td>{w.innovations}</td><td className="text-xs">{fmtDate(w.created_at)}</td></tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}
