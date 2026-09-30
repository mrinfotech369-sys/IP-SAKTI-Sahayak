'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Badge, EmptyState, ErrorState, PageHeader, Spinner, fmtDateTime } from '@/components/ui';
import { get, patch } from '@/lib/api';

export default function FeedbackQueue() {
  const qc = useQueryClient();
  const [status, setStatus] = useState('OPEN');
  const q = useQuery({ queryKey: ['feedback', status], queryFn: () => get<any[]>(`/feedback${status ? `?status=${status}` : ''}`) });
  const upd = useMutation({ mutationFn: ({ id, s, note }: any) => patch(`/feedback/${id}`, { status: s, resolution_note: note }), onSuccess: () => qc.invalidateQueries({ queryKey: ['feedback'] }) });
  return (
    <div>
      <PageHeader title="Feedback & reported issues" subtitle="Reports of wrong answers, sources or citations, with a snapshot of the answer and source versions at the time. Reviewers resolve them here."
        actions={<select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status"><option value="">All</option>{['OPEN', 'IN_REVIEW', 'RESOLVED', 'DISMISSED'].map((s) => <option key={s}>{s}</option>)}</select>} />
      {q.isLoading && <Spinner />}
      {q.isError && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {upd.isError && <ErrorState error={upd.error} />}
      {q.data?.length === 0 && <EmptyState title="No reports">Use “Report issue” under any assistant answer.</EmptyState>}
      <div className="space-y-3">{q.data?.map((f) => (
        <div key={f.id} className="rounded-lg border border-surface-border bg-surface-elevated p-4 text-sm">
          <div className="flex flex-wrap items-center gap-2"><Badge tone="danger">{f.category.replace(/_/g, ' ').toLowerCase()}</Badge><Badge>{f.status}</Badge>
            {f.target?.key_point_id && <Badge tone="info">key point {f.target.key_point_id}</Badge>}<span className="text-xs text-text-muted">{fmtDateTime(f.created_at)}</span></div>
          <p className="mt-2">{f.reason}</p>
          {f.snapshot?.answer && (
            <details className="mt-2 text-xs"><summary className="cursor-pointer text-info">Snapshot of answer & sources</summary>
              <p className="mt-1">{f.snapshot.answer}</p>
              <ul className="ml-4 list-disc">{(f.snapshot.sources || []).map((s: any) => <li key={s.chunk_id}>[{s.n}] {s.title} {s.section ? `· ${s.section}` : ''} — version {s.version || '—'}, checked {fmtDateTime(s.last_checked)}</li>)}</ul>
            </details>
          )}
          {f.resolution_note && <p className="mt-2 text-xs text-ok">Resolution: {f.resolution_note}</p>}
          <div className="mt-2 flex gap-2 text-xs">
            {['IN_REVIEW', 'RESOLVED', 'DISMISSED'].filter((s) => s !== f.status).map((s) => (
              <button key={s} className="rounded border border-surface-border px-2 py-1 hover:bg-surface-muted"
                onClick={() => upd.mutate({ id: f.id, s, note: s === 'IN_REVIEW' ? null : window.prompt('Resolution note') || '' })}>Mark {s.replace('_', ' ').toLowerCase()}</button>
            ))}
          </div>
        </div>
      ))}</div>
    </div>
  );
}
