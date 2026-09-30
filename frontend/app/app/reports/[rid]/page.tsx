'use client';

import { useQuery } from '@tanstack/react-query';
import { Download, Printer } from 'lucide-react';
import { useParams } from 'next/navigation';
import { Markdown } from '@/components/markdown';
import { Button, ErrorState, Spinner, fmtDateTime } from '@/components/ui';
import { BackLink } from '@/components/back';
import { api, get } from '@/lib/api';

export default function ReportView() {
  const { rid } = useParams<{ rid: string }>();
  const q = useQuery({ queryKey: ['report', rid], queryFn: () => get(`/reports/${rid}`) });
  async function download() {
    const md = await api<string>(`/reports/${rid}/markdown`, { raw: true });
    const url = URL.createObjectURL(new Blob([md], { type: 'text/markdown' }));
    const a = Object.assign(document.createElement('a'), { href: url, download: `${q.data.title.replace(/[^\w]+/g, '-')}.md` });
    a.click();
    URL.revokeObjectURL(url);
  }
  if (q.isLoading) return <Spinner label="Loading report…" />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  return (
    <div>
      <div className="no-print mb-4 flex flex-wrap items-center justify-between gap-2">
        <div className="flex gap-4"><BackLink href={`/app/innovations/${q.data.innovation_id}/review`}>Back to innovation</BackLink><BackLink href="/app/reports">All reports</BackLink></div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={download}><Download className="h-4 w-4" /> Export Markdown</Button>
          <Button variant="secondary" onClick={() => window.print()}><Printer className="h-4 w-4" /> Print / Save as PDF</Button>
        </div>
      </div>
      <article className="rounded-lg border border-surface-border bg-white p-8">
        <p className="mb-4 text-xs text-text-muted">Generated {fmtDateTime(q.data.created_at)} · report {q.data.id}</p>
        <Markdown source={q.data.markdown} />
      </article>
    </div>
  );
}
