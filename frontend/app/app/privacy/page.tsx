'use client';

import { useQuery } from '@tanstack/react-query';
import { Card, ErrorState, PageHeader, Spinner } from '@/components/ui';
import { get } from '@/lib/api';

export default function Privacy() {
  const q = useQuery({ queryKey: ['privacy'], queryFn: () => get('/privacy') });
  if (q.isLoading) return <Spinner />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const d = q.data;
  const rows: [string, string][] = [
    ['Where data is stored', d.storage], ['Encryption', d.encryption], ['Access control', d.access_control],
    ['Sensitive / unpublished inputs', d.sensitive_input], ['Document uploads', d.upload_notice],
  ];
  return (
    <div className="space-y-4">
      <PageHeader title="Data handling & privacy" subtitle="What happens to innovation details, uploads and questions in this deployment." />
      <Card title="Language model (third-party exposure)">
        <p className="text-sm"><span className="font-semibold">Provider:</span> {d.llm.provider}</p>
        <p className="mt-1 text-sm">{d.llm.policy}</p>
        <p className="mt-1 text-xs text-text-secondary">{d.llm.self_hosted_option}</p>
      </Card>
      <Card title="Retention">
        <p className="text-sm">Policy for this workspace: <span className="font-semibold">{d.retention.policy}</span> — applies to {d.retention.applies_to}.</p>
        <p className="mt-1 text-xs text-text-secondary">{d.retention.enforcement}</p>
      </Card>
      {rows.map(([k, v]) => <Card key={k} title={k}><p className="text-sm">{v}</p></Card>)}
    </div>
  );
}
