'use client';

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { useState } from 'react';
import { Badge, EmptyState, ErrorState, PageHeader, Spinner, fmtDateTime } from '@/components/ui';
import { get } from '@/lib/api';

export default function Escalations() {
  const q = useQuery({ queryKey: ['escalations'], queryFn: () => get<any[]>('/escalations') });
  const [status, setStatus] = useState('');
  const rows = (q.data || []).filter((e) => !status || e.status === status);
  return (
    <div>
      <PageHeader title="Escalation Packets" subtitle="Human review requests with full evidence packets." actions={
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status filter">
          <option value="">All statuses</option>{['OPEN', 'IN_REVIEW', 'RESOLVED', 'CLOSED'].map((s) => <option key={s}>{s}</option>)}
        </select>} />
      {q.isLoading && <Spinner />}
      {q.isError && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.data && rows.length === 0 && <EmptyState title="No escalations">Open an innovation → Escalation & Report to request IP, regulatory or domain review.</EmptyState>}
      <div className="overflow-x-auto rounded-lg border border-surface-border bg-surface-elevated">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface-muted text-xs text-text-secondary"><tr><th className="px-3 py-2">Type</th><th>Innovation</th><th>Professional</th><th>Status</th><th>Created</th></tr></thead>
          <tbody>
            {rows.map((e) => (
              <tr key={e.id} className="border-t border-surface-border">
                <td className="px-3 py-2"><Link className="font-medium hover:underline" href={`/app/escalations/${e.id}`}>{e.type.replace('_', ' ')}</Link></td>
                <td>{e.innovation_name}</td><td className="text-xs">{e.recommended_professional}</td>
                <td><Badge tone={e.status === 'OPEN' ? 'warn' : e.status === 'IN_REVIEW' ? 'info' : 'ok'}>{e.status}</Badge></td>
                <td className="text-xs text-text-muted">{fmtDateTime(e.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
