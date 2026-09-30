'use client';

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { EmptyState, ErrorState, PageHeader, Spinner, fmtDateTime } from '@/components/ui';
import { get } from '@/lib/api';

export default function Reports() {
  const q = useQuery({ queryKey: ['reports'], queryFn: () => get<any[]>('/reports') });
  return (
    <div>
      <PageHeader title="Evidence Reports" subtitle="Generated from an innovation's Escalation & Report tab. Export as Markdown or print to PDF." />
      {q.isLoading && <Spinner />}
      {q.isError && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.data?.length === 0 && <EmptyState title="No reports yet">Open an innovation → Escalation & Report → Generate evidence report.</EmptyState>}
      <ul className="divide-y divide-surface-border rounded-lg border border-surface-border bg-surface-elevated">
        {q.data?.map((r) => (
          <li key={r.id}><Link href={`/app/reports/${r.id}`} className="flex justify-between px-4 py-3 text-sm hover:bg-surface-muted"><span className="font-medium">{r.title}</span><span className="text-xs text-text-muted">{fmtDateTime(r.created_at)}</span></Link></li>
        ))}
      </ul>
    </div>
  );
}
