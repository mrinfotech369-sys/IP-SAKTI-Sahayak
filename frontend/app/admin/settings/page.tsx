'use client';

import { useQuery } from '@tanstack/react-query';
import { Badge, Card, ErrorState, Notice, PageHeader, Spinner } from '@/components/ui';
import { get } from '@/lib/api';

function Rows({ obj }: { obj: Record<string, any> }) {
  return (
    <dl className="grid grid-cols-1 gap-x-4 gap-y-1.5 text-sm sm:grid-cols-2">
      {Object.entries(obj).map(([k, v]) => (
        <div key={k} className="flex justify-between gap-2 border-b border-surface-border py-1 sm:border-0 sm:py-0">
          <dt className="text-text-muted">{k.replace(/_/g, ' ')}</dt>
          <dd className="text-right font-medium">{typeof v === 'boolean' ? <Badge tone={v ? 'ok' : 'neutral'}>{String(v)}</Badge> : String(v)}</dd>
        </div>
      ))}
    </dl>
  );
}

export default function AdminSettings() {
  const q = useQuery({ queryKey: ['admin-settings'], queryFn: () => get('/admin/settings') });
  const d: any = q.data;
  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Admin console" title="Configuration" subtitle="Effective server configuration. Secrets are masked; nothing here can be edited from the browser." />
      {q.isLoading && <Spinner />}
      {q.isError && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {d && (
        <>
          <Notice tone="info">{d.how_to_change}</Notice>
          <Card title="Environment"><Rows obj={{ environment: d.environment }} /></Card>
          <Card title="Language model">
            <Rows obj={{ provider: d.llm.provider, model: d.llm.model, base_url: d.llm.base_url, api_key: d.llm.api_key, temperature: d.llm.temperature, max_tokens: d.llm.max_tokens, timeout_s: d.llm.timeout_s }} />
            <p className="mt-2 text-xs text-text-secondary">{d.llm.data_handling}</p>
          </Card>
          <Card title="Embeddings"><Rows obj={d.embeddings} /></Card>
          <Card title="Retrieval"><Rows obj={d.retrieval} /></Card>
          <Card title="Rate limits (per minute)"><Rows obj={d.rate_limits_per_min} /></Card>
          <Card title="Sessions"><Rows obj={d.sessions} /></Card>
          <Card title="Uploads"><Rows obj={d.uploads} /></Card>
          <Card title="Cost assumptions (USD per million tokens)"><Rows obj={d.cost_assumptions_usd_per_million} /></Card>
        </>
      )}
    </div>
  );
}
