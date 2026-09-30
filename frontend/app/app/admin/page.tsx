'use client';

import { useMutation, useQuery } from '@tanstack/react-query';
import { Button } from '@/components/ui';
import { post } from '@/lib/api';
import { Badge, Card, ErrorState, PageHeader, Spinner, Stat, TierBadge, fmtDate } from '@/components/ui';
import { get } from '@/lib/api';

function HealthRow({ label, q }: { label: string; q: any }) {
  const d = q.data || {};
  const ok = Object.values(d).includes('ok');
  return (
    <div className="flex items-start justify-between gap-2 border-b border-surface-border py-2 text-sm last:border-0">
      <span className="font-medium">{label}</span>
      {q.isLoading ? <Spinner /> : q.isError ? <Badge tone="danger">error</Badge> : (
        <span className="text-right text-xs"><Badge tone={ok ? 'ok' : d.llm === 'mock' ? 'warn' : 'danger'}>{ok ? 'ok' : d.llm === 'mock' ? 'extractive mode' : 'error'}</Badge>
          <div className="mt-1 text-text-muted">{Object.entries(d).filter(([k]) => !['database', 'vector', 'llm'].includes(k)).map(([k, v]) => `${k}: ${v}`).join(' · ')}</div></span>
      )}
    </div>
  );
}

export default function AdminHealth() {
  const ov = useQuery({ queryKey: ['admin-overview'], queryFn: () => get('/admin/overview') });
  const db = useQuery({ queryKey: ['h-db'], queryFn: () => get('/health/database') });
  const vec = useQuery({ queryKey: ['h-vec'], queryFn: () => get('/health/vector') });
  const llm = useQuery({ queryKey: ['h-llm'], queryFn: () => get('/health/llm') });
  const d = ov.data;
  const purge = useMutation({ mutationFn: (dry: boolean) => post(`/admin/retention/run?dry_run=${dry}`) });
  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Admin" title="System Health" subtitle="Live status of the database, vector index and language model, plus RAG and citation metrics from real usage." />
      <Card title="Components"><HealthRow label="PostgreSQL" q={db} /><HealthRow label="pgvector index" q={vec} /><HealthRow label="LLM provider" q={llm} /></Card>
      {ov.isError && <ErrorState error={ov.error} onRetry={() => ov.refetch()} />}
      {d && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
            {Object.entries(d.counts).map(([k, v]) => <Stat key={k} label={k.replace(/_/g, ' ')} value={v as number} />)}
          </div>
          <div className="grid gap-4 lg:grid-cols-3">
            <Card title="RAG metrics (last 200 answers)">
              <dl className="space-y-1 text-sm">
                <div className="flex justify-between"><dt>Answers sampled</dt><dd>{d.rag_metrics.answers_sampled}</dd></div>
                <div className="flex justify-between"><dt>Average latency</dt><dd>{d.rag_metrics.avg_latency_ms ?? '—'} ms</dd></div>
                <div className="flex justify-between"><dt>Abstention rate</dt><dd>{d.rag_metrics.abstention_rate ?? '—'}</dd></div>
              </dl>
            </Card>
            <Card title="Citation metrics">
              <dl className="space-y-1 text-sm">
                <div className="flex justify-between"><dt>Claims verified</dt><dd>{d.citation_metrics.claims_verified}</dd></div>
                {Object.entries(d.citation_metrics.by_status).map(([k, v]) => <div key={k} className="flex justify-between"><dt>{k.toLowerCase().replace('_', ' ')}</dt><dd>{v as number}</dd></div>)}
                <div className="flex justify-between font-semibold"><dt>Unsupported rate</dt><dd>{d.citation_metrics.unsupported_rate}</dd></div>
              </dl>
            </Card>
            <Card title="Ingestion jobs">
              <dl className="space-y-1 text-sm">
                <div className="flex justify-between"><dt>Total</dt><dd>{d.jobs.total}</dd></div>
                <div className="flex justify-between"><dt>Failed</dt><dd className={d.jobs.failed ? 'text-danger' : ''}>{d.jobs.failed}</dd></div>
              </dl>
            </Card>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Runtime & cost (measured)">
              <dl className="space-y-1 text-sm">
                <div className="flex justify-between"><dt>Queries sampled</dt><dd>{d.runtime.queries_sampled}</dd></div>
                <div className="flex justify-between"><dt>Latency p50 / p95</dt><dd>{d.runtime.latency_ms.p50 ?? '—'} / {d.runtime.latency_ms.p95 ?? '—'} ms</dd></div>
                <div className="flex justify-between"><dt>LLM calls per query</dt><dd>{d.runtime.llm_calls_per_query}</dd></div>
                <div className="flex justify-between"><dt>Avg cost per query</dt><dd>${d.runtime.avg_cost_per_query_usd}</dd></div>
                <div className="flex justify-between"><dt>{d.runtime.projection_10k_users.assumption}</dt><dd>${d.runtime.projection_10k_users.monthly_llm_cost_usd}/month LLM</dd></div>
              </dl>
              <p className="mt-2 text-[11px] text-text-muted">Price assumptions: ${d.runtime.cost_assumptions.input_per_million_usd}/M input, ${d.runtime.cost_assumptions.output_per_million_usd}/M output tokens (provider: {d.runtime.cost_assumptions.provider}).</p>
            </Card>
            <Card title="Where compute runs">
              <dl className="space-y-1 text-xs">{Object.entries(d.runtime.runtime).map(([k, v]) => <div key={k}><dt className="inline font-semibold">{k}: </dt><dd className="inline">{v as string}</dd></div>)}</dl>
            </Card>
          </div>
          <Card title="Retention policy enforcement" actions={<><Button size="sm" variant="secondary" onClick={() => purge.mutate(true)} loading={purge.isPending}>Dry run</Button><Button size="sm" variant="danger" onClick={() => window.confirm('Delete conversations and uploads older than each workspace retention policy?') && purge.mutate(false)}>Apply</Button></>}>
            {!purge.data && <p className="text-sm text-text-muted">Deletes conversations and workspace uploads older than each workspace's retention policy. Audit logs are kept.</p>}
            {purge.data && <ul className="space-y-1 text-xs">{(purge.data as any).workspaces.map((w: any) => <li key={w.workspace}>{(purge.data as any).dry_run ? 'Would delete' : 'Deleted'} {w.conversations} conversations, {w.uploaded_documents} uploads — {w.workspace} ({w.policy})</li>)}</ul>}
          </Card>
          <Card title="Sources">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-text-secondary"><tr><th className="py-1">Source</th><th>Tier</th><th>Jurisdiction</th><th>Last checked</th><th>Status</th><th className="text-right">Documents</th></tr></thead>
              <tbody>{d.sources.map((s: any) => (
                <tr key={s.id} className="border-t border-surface-border"><td className="py-1.5">{s.name}</td><td><TierBadge tier={s.tier} /></td><td>{s.jurisdiction}</td><td className="text-xs">{fmtDate(s.last_checked)}</td>
                  <td>{s.active ? <Badge tone="ok">active</Badge> : <Badge tone="danger">inactive</Badge>}</td><td className="text-right tabular-nums">{s.documents}</td></tr>
              ))}</tbody>
            </table>
          </Card>
        </>
      )}
    </div>
  );
}
