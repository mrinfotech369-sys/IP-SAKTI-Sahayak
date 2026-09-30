'use client';

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { useState } from 'react';
import { Badge, EmptyState, ErrorState, PageHeader, Spinner, fmtDateTime } from '@/components/ui';
import { get } from '@/lib/api';

export default function AdminEscalations() {
  const [status, setStatus] = useState('');
  const q = useQuery({ queryKey: ['admin-escalations', status], queryFn: () => get<any[]>(`/admin/escalations${status ? `?status=${status}` : ''}`) });
  return (
    <div>
      <PageHeader eyebrow="Admin console" title="Escalations" subtitle="Pending human-review requests across every workspace. Assign a reviewer, track status and leave notes."
        actions={<select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status filter">
          <option value="">All statuses</option>{['OPEN', 'IN_REVIEW', 'RESOLVED', 'CLOSED'].map((s) => <option key={s}>{s}</option>)}
        </select>} />
      {q.isLoading && <Spinner />}
      {q.isError && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.data?.length === 0 && <EmptyState title="No escalations" />}
      <div className="overflow-x-auto rounded-lg border border-surface-border bg-surface-elevated">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface-muted text-xs text-text-secondary"><tr><th className="px-3 py-2">Type</th><th>Innovation</th><th>Workspace</th><th>Assigned to</th><th>Status</th><th>Created</th></tr></thead>
          <tbody>{q.data?.map((e) => (
            <tr key={e.id} className="border-t border-surface-border">
              <td className="px-3 py-2"><Link className="font-medium hover:underline" href={`/admin/escalations/${e.id}`}>{e.type.replace(/_/g, ' ')}</Link></td>
              <td>{e.innovation_name}</td><td className="text-xs">{e.workspace}</td>
              <td className="text-xs">{e.assigned_to ? e.assigned_to.name : <span className="text-text-muted">Unassigned</span>}</td>
              <td><Badge tone={e.status === 'OPEN' ? 'warn' : e.status === 'IN_REVIEW' ? 'info' : 'ok'}>{e.status}</Badge></td>
              <td className="text-xs text-text-muted">{fmtDateTime(e.created_at)}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}
