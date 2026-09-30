'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { Badge, Button, EmptyState, ErrorState, PageHeader, Spinner, fmtDate } from '@/components/ui';
import { get, patch } from '@/lib/api';

export default function UpdateQueue() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['update-queue'], queryFn: () => get<any[]>('/admin/update-queue') });
  const act = useMutation({ mutationFn: ({ id, action }: any) => patch(`/documents/${id}/review`, { action }), onSuccess: () => qc.invalidateQueries({ queryKey: ['update-queue'] }) });
  return (
    <div>
      <PageHeader eyebrow="Admin" title="Corpus Update Queue" subtitle="Documents whose last check is older than their source's update frequency. The named curator re-verifies against the official text, then marks it checked, approves it, or records supersession." />
      {q.isLoading && <Spinner />}
      {q.isError && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {act.isError && <ErrorState error={act.error} />}
      {q.data?.length === 0 && <EmptyState title="Everything is up to date" />}
      <div className="overflow-x-auto rounded-lg border border-surface-border bg-surface-elevated">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface-muted text-xs text-text-secondary"><tr><th className="px-3 py-2">Document</th><th>Status</th><th>Last checked</th><th>Frequency</th><th>Curator</th><th>Actions</th></tr></thead>
          <tbody>{q.data?.map((d) => (
            <tr key={d.document_id} className="border-t border-surface-border align-top">
              <td className="px-3 py-2"><Link className="font-medium hover:underline" href={`/app/documents/${d.document_id}`}>{d.title}</Link><div className="text-xs text-text-muted">{d.source} · {d.jurisdiction} · version {d.version || '—'}</div></td>
              <td><Badge tone={d.update_status === 'Overdue' ? 'danger' : d.update_status === 'Superseded' ? 'neutral' : 'warn'}>{d.update_status}</Badge></td>
              <td className="text-xs">{fmtDate(d.last_checked)}{d.age_days != null && <div className="text-text-muted">{d.age_days} days ago</div>}</td>
              <td className="text-xs">every {d.frequency_days} days</td>
              <td className="text-xs">{d.curator}</td>
              <td className="space-x-1 whitespace-nowrap">
                {d.update_status !== 'Superseded' && <Button size="sm" variant="secondary" onClick={() => act.mutate({ id: d.document_id, action: 'mark_checked' })}>Mark checked</Button>}
                {d.review_status !== 'DEMO_FICTIONAL' && d.update_status !== 'Superseded' && <Button size="sm" variant="ghost" onClick={() => act.mutate({ id: d.document_id, action: 'approve' })}>Approve (verified)</Button>}
              </td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}
